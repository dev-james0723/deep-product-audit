import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from impact_router import route

class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="impact-router-")
        self.addCleanup(self.temp.cleanup)
        self.dir=pathlib.Path(self.temp.name)
        self.repo=self.dir/"repo"
        self.repo.mkdir()
        def git(*args):
            env=dict(os.environ,GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM="1",
                     GIT_OPTIONAL_LOCKS="0")
            result=subprocess.run(["git",*args],cwd=self.repo,check=True,capture_output=True,env=env)
        git("init","-q")
        git("config","user.email","fixture@example.invalid")
        git("config","user.name","fixture")
        git("config","commit.gpgsign","false")
        git("config","core.hooksPath",os.devnull)
        (self.repo/"sample.py").write_text("value=1\n")
        git("add","sample.py")
        git("commit","-qm","fixture")
        self.guard=self.dir/"fake-guard.py"
        self.guard.write_text("""
import json,subprocess,sys,pathlib
repo=pathlib.Path(sys.argv[sys.argv.index('--repo')+1]).resolve()
graph=sys.argv[sys.argv.index('--graph')+1]
head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
print(json.dumps({'should_query_graph':True,'status':'ready','repository':str(repo),'graph':graph,'head':head,'indexed_commit':head}))
""")
    def test_other_repos_fallback(self):
        x=route(self.repo,"other",self.guard)
        self.assertFalse(x["should_query_graph"])
        self.assertTrue(x["working_tree_clean"])
    def test_dirty_repos_fallback(self):
        (self.repo/"sample.py").write_text("value=2\n")
        x=route(self.repo,"example-graph-a",self.guard)
        self.assertFalse(x["working_tree_clean"])
        self.assertFalse(x["should_query_graph"])
    def test_guard_approves_exact_repo(self):
        x=route(self.repo,"example-graph-b",self.guard)
        self.assertTrue(x["should_query_graph"])
        self.assertTrue(x["graph_checked"])
    def test_guard_cannot_approve_dirty(self):
        (self.repo/"new.tmp").write_text("x")
        x=route(self.repo,"example-graph-b",self.guard)
        self.assertFalse(x["should_query_graph"])
    def test_guard_cannot_approve_wrong_snapshot(self):
        self.guard.write_text("import json;print(json.dumps({'should_query_graph':True,'status':'ready','repository':'other','graph':'example-graph-b','head':'0'*40,'indexed_commit':'0'*40}))\n")
        x=route(self.repo,"example-graph-b",self.guard)
        self.assertFalse(x["should_query_graph"])
    def test_relative_guard_resolution(self):
        x=route(self.repo,"example-graph-b",str(self.guard))
        self.assertTrue(x["should_query_graph"])
if __name__=="__main__":unittest.main()
