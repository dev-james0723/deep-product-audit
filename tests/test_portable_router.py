"""Portability requirements, kept identical before and after the router fix."""
import os
import pathlib
import subprocess
import tempfile
import unittest

from impact_router import route


class PortableRouterTests(unittest.TestCase):
    def test_arbitrary_explicit_graph_is_revision_qualified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            repo = root / "project with spaces"
            repo.mkdir()
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
            for args in (("init", "-q"), ("config", "user.email", "fixture@example.invalid"),
                         ("config", "user.name", "fixture"), ("config", "commit.gpgsign", "false"),
                         ("config", "core.hooksPath", os.devnull)):
                subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)
            (repo / "source.txt").write_text("fixture\n", encoding="utf-8")
            for args in (("add", "source.txt"), ("commit", "-qm", "fixture")):
                subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)
            guard = root / "guard.py"
            guard.write_text("import json,pathlib,subprocess,sys\n"
                             "r=pathlib.Path(sys.argv[sys.argv.index('--repo')+1]).resolve()\n"
                             "g=sys.argv[sys.argv.index('--graph')+1]\n"
                             "h=subprocess.check_output(['git','-C',str(r),'rev-parse','HEAD'],text=True).strip()\n"
                             "print(json.dumps(dict(should_query_graph=True,status='ready',repository=str(r),graph=g,head=h,indexed_commit=h)))\n",
                             encoding="utf-8")
            result = route(repo, "sample-team-module", guard)
            self.assertTrue(result["should_query_graph"], result)
            self.assertTrue(result["graph_checked"])
            self.assertEqual(result["graph"], "sample-team-module")


if __name__ == "__main__":
    unittest.main()
