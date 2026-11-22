#!/usr/bin/env python3
"""Opt-in revision-qualified graph routing; never auto-index or upload."""
import argparse
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import threading

MAX_CAPTURE_BYTES = 65536


def _stop_owned(process):
    """Terminate only the new process group owned by this bounded invocation."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass

def run(argv, cwd=None, timeout=4):
    process = None
    try:
        process = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   stdin=subprocess.DEVNULL, bufsize=0,
                                   start_new_session=(os.name == "posix"),
                                   env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        buffers = [bytearray(), bytearray()]
        lock, exceeded = threading.Lock(), threading.Event()

        def drain(pipe, index):
            try:
                while True:
                    block = pipe.read(4096)
                    if not block:
                        break
                    with lock:
                        remaining = MAX_CAPTURE_BYTES - sum(map(len, buffers))
                        buffers[index].extend(block[:remaining])
                        if len(block) > remaining:
                            exceeded.set()
                    if exceeded.is_set():
                        _stop_owned(process)
                        break
            finally:
                pipe.close()

        readers = [threading.Thread(target=drain, args=(pipe, i), daemon=True)
                   for i, pipe in enumerate((process.stdout, process.stderr))]
        for reader in readers:
            reader.start()
        error = None
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            error = "TimeoutExpired"
            _stop_owned(process)
            process.wait(timeout=2)
        for reader in readers:
            reader.join(timeout=1)
        if any(reader.is_alive() for reader in readers):
            _stop_owned(process)
            for reader in readers:
                reader.join(timeout=1)
            error = "pipe_cleanup_unverified"
        if exceeded.is_set():
            return -1, "", "output_limit_exceeded"
        if error:
            return -1, "", error
        return (process.returncode, bytes(buffers[0]).decode("utf-8", "replace").strip()[:8192],
                bytes(buffers[1]).decode("utf-8", "replace").strip()[:600])
    except (OSError, subprocess.SubprocessError) as exc:
        if process is not None:
            _stop_owned(process)
            try:
                process.wait(timeout=2)
            except subprocess.SubprocessError:
                pass
        return -1, "", type(exc).__name__

def route(repo, graph, guard):
    repo=pathlib.Path(repo).resolve()
    ret,root,_=run(["git","rev-parse","--show-toplevel"],cwd=repo)
    if ret: raise ValueError("Not a Git repository")
    root=pathlib.Path(root).resolve()
    revcode,rev,_=run(["git","rev-parse","HEAD"],cwd=root)
    if revcode:raise ValueError("Cannot read HEAD")
    dirtycode,dirty,_=run(["git","status","--porcelain","--untracked-files=normal"],cwd=root)
    if dirtycode:raise ValueError("Cannot read status")
    base={"schema_version":1,"repo":str(root),"graph":graph,"head":rev,
          "working_tree_clean":not bool(dirty),"graph_checked":False,
          "should_query_graph":False,"execution":"read_only_no_graph_query",
          "action":"targeted_source_inspection",
          "why":"No valid matching graph observed", "warnings":[],
          "recommended_commands":["git diff --name-only","rg -n -- <exact-symbol> <scoped-paths>"]}
    if dirty:
        base.update(why="Uncommitted/untracked work can make the graph stale",
                    warnings=["Do not discard or reset the worktree. Inspect changes directly."])
        return base
    if graph in (None, "", "other"):
        base.update(why="No graph explicitly selected")
        return base
    if not isinstance(graph, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", graph):
        raise ValueError("Graph identifier must contain 1..80 safe identifier characters")
    guard_path=pathlib.Path(guard).expanduser().resolve() if guard else None
    if not guard_path or not guard_path.is_file():
        base.update(why="Graphify guard not available")
        return base
    ret,out,err=run([sys.executable,str(guard_path),"--repo",str(root),"--graph",graph],cwd=root,timeout=7)
    base["graph_checked"]=True
    if ret:
        base.update(why="Graphify guard rejected graph/revision",warnings=[err[:200]] if err else [])
        return base
    try:
        info=json.loads(out)
    except ValueError:
        base.update(why="Graphify guard returned non-JSON output")
        return base
    if not isinstance(info,dict):
        base.update(why="Graphify guard returned non-object output")
        return base
    expected = (info.get("should_query_graph") is True and
                info.get("status") in ("ready","ready_remapped") and
                info.get("repository")==str(root) and
                info.get("graph")==graph and
                info.get("head")==rev and info.get("indexed_commit")==rev)
    if not expected:
        base.update(why="Graphify guard did not corroborate exact repository, graph and commit")
        return base
    revcode,after_rev,_=run(["git","rev-parse","HEAD"],cwd=root)
    statuscode,after_status,_=run(["git","status","--porcelain","--untracked-files=normal"],cwd=root)
    if revcode or statuscode or after_rev!=rev or after_status:
        base.update(why="Repository revision/worktree changed during graph guard check")
        return base
    base.update(should_query_graph=True,action="narrow_graph_query_then_verify_source",
                why="Graphify guard accepted exact repository/revision and state recheck",
                recommended_commands=["Graphify query with 800-1200 token budget and matching graph",
                                      "Verify source lines and tests at current HEAD"])
    return base

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo",type=pathlib.Path,required=True)
    p.add_argument("--graph",default=None,help="Explicit graph identifier; omitted means source inspection")
    p.add_argument("--guard",type=pathlib.Path,help="Explicit authorized Python guard; never auto-discovered or installed")
    p.add_argument("--out",type=pathlib.Path)
    a=p.parse_args()
    try:
        result=route(a.repo,a.graph,a.guard)
        data=json.dumps(result,indent=2)+"\n"
        if a.out:
            with a.out.open("x") as out:out.write(data)
        else:print(data,end="")
        return 0
    except (ValueError,OSError) as exc:
        print("impact_router: "+str(exc),file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())
