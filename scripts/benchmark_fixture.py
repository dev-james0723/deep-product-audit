#!/usr/bin/env python3
"""Generate and self-check an isolated HTTP/SQLite audit benchmark fixture.

Benchmark answer keys and corrected source remain outside the agent-facing target.
This helper tests the fixture and its oracles, NOT an agent's detection skill.
"""
import argparse
import ast
import contextlib
import csv
import importlib.util
import io
import json
import pathlib
import sqlite3
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request

TARGET_SOURCE = r'''
#!/usr/bin/env python3
"""Synthetic, local-only application for assessing an audit process. No real users or integrations."""
import argparse
import csv
import io
import json
import sqlite3
import threading
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

CURRENT_MODE = "__MODE__"

class Demo:
    def __init__(self, db):
        self.db_path=str(db)
        self.lock=threading.RLock()
        self.connection=sqlite3.connect(self.db_path,check_same_thread=False)
        self.connection.execute("CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, owner TEXT, content TEXT)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, idem TEXT, sku TEXT)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS settings(owner TEXT PRIMARY KEY, theme TEXT)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS ops(id TEXT PRIMARY KEY, state TEXT)")
        self.connection.execute("INSERT OR IGNORE INTO notes VALUES (1,'user-a','private-note-a')")
        self.connection.execute("INSERT OR IGNORE INTO notes VALUES (2,'user-b','private-note-b')")
        self.connection.execute("INSERT OR IGNORE INTO ops VALUES ('op-1','active')")
        self.connection.commit()
        self.volatile={}
        self.cache={}
    def make_handler(self):
        app=self
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(3)
            def log_message(self,*_):pass
            def user(self):return self.headers.get("X-Fixture-User","")
            def write(self,code,obj,content_type="application/json"):
                payload=obj.encode("utf-8") if isinstance(obj,str) else json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type",content_type)
                self.send_header("Content-Length",str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def read_body(self):
                length=int(self.headers.get("Content-Length","0"))
                if length>4096:return None
                try:return json.loads(self.rfile.read(length))
                except Exception:return None
            def do_GET(self):
                url=urllib.parse.urlparse(self.path)
                if url.path=="/health":return self.write(200,{"status":"ok"})
                if url.path=="/v1/catalog":return self.write(200,{"products":["fixture-item"]})
                if url.path=="/version":return self.write(200,{"version":"fixture-v1"})
                if url.path.startswith("/v1/notes/"):
                    try:note_id=int(url.path.split("/")[-1])
                    except ValueError:return self.write(400,{"error":"invalid_id"})
                    with app.lock:
                        found=app.connection.execute("SELECT owner,content FROM notes WHERE id=?",(note_id,)).fetchone()
                    if not found:return self.write(404,{"error":"missing"})
                    if CURRENT_MODE=="fixed" and (not self.user() or found[0]!=self.user()):
                        return self.write(403,{"error":"forbidden"})
                    return self.write(200,{"owner":found[0],"content":found[1]})
                if url.path=="/v1/settings":
                    with app.lock:
                        if CURRENT_MODE=="fixed":
                            row=app.connection.execute("SELECT theme FROM settings WHERE owner=?",(self.user(),)).fetchone()
                            value=row[0] if row else "light"
                        else:value=app.volatile.get(self.user(),"light")
                    return self.write(200,{"theme":value})
                if url.path=="/v1/welcome":
                    user=self.user()
                    if not user:return self.write(400,{"error":"missing_user"})
                    with app.lock:
                        key=user if CURRENT_MODE=="fixed" else "global"
                        if key not in app.cache:app.cache[key]="Welcome "+user
                        result=app.cache[key]
                    return self.write(200,{"message":result})
                if url.path=="/v1/export":
                    cell=urllib.parse.parse_qs(url.query).get("cell",[""])[0]
                    if CURRENT_MODE=="fixed" and cell.startswith(("=","+","-","@")):cell="'"+cell
                    output=io.StringIO()
                    writer=csv.writer(output)
                    writer.writerow(["value"])
                    writer.writerow([cell])
                    return self.write(200,output.getvalue(),"text/csv")
                if url.path=="/v1/ops/op-1":
                    with app.lock:state=app.connection.execute("SELECT state FROM ops WHERE id='op-1'").fetchone()[0]
                    return self.write(200,{"state":state})
                return self.write(404,{"error":"not_found"})
            def do_POST(self):
                if self.path not in ("/v1/orders","/v1/settings","/v1/cancel"):
                    return self.write(404,{"error":"not_found"})
                payload=self.read_body()
                if not isinstance(payload,dict):return self.write(400,{"error":"bad_json"})
                if self.path=="/v1/orders":
                    if not isinstance(payload.get("qty"),int) or not (1<=payload["qty"]<=100):
                        return self.write(400,{"error":"invalid_qty"})
                    if not isinstance(payload.get("sku"),str) or not payload["sku"]:
                        return self.write(400,{"error":"invalid_sku"})
                    key=self.headers.get("Idempotency-Key","")
                    if not key:return self.write(400,{"error":"missing_idem_key"})
                    with app.lock:
                        if CURRENT_MODE=="fixed":
                            found=app.connection.execute("SELECT id FROM orders WHERE idem=?",(key,)).fetchone()
                            if found:return self.write(200,{"order_id":found[0],"replayed":True})
                        row=app.connection.execute("INSERT INTO orders(idem,sku) VALUES (?,?)",(key,payload["sku"]))
                        app.connection.commit()
                    return self.write(201,{"order_id":row.lastrowid,"replayed":False})
                if self.path=="/v1/settings":
                    if payload.get("theme") not in ("light","dark") or not self.user():
                        return self.write(400,{"error":"invalid"})
                    with app.lock:
                        if CURRENT_MODE=="fixed":
                            app.connection.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET theme=excluded.theme",(self.user(),payload["theme"]))
                            app.connection.commit()
                        else:app.volatile[self.user()]=payload["theme"]
                    return self.write(200,{"saved":True})
                if self.path=="/v1/cancel":
                    if payload.get("operation_id")!="op-1":return self.write(404,{"error":"unknown_op"})
                    with app.lock:
                        if CURRENT_MODE=="fixed":
                            app.connection.execute("UPDATE ops SET state='cancelled' WHERE id='op-1'")
                            app.connection.commit()
                    return self.write(200,{"status":"cancelled"})
        return Handler

def start(mode,db):
    global CURRENT_MODE
    CURRENT_MODE=mode
    demo=Demo(db)
    server=ThreadingHTTPServer(("127.0.0.1",0),demo.make_handler())
    server.daemon_threads=False
    server.block_on_close=True
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    return server,thread,demo

def stop(server,thread,demo):
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    if thread.is_alive():raise RuntimeError("Owned server thread did not stop")
    demo.connection.close()

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--db",required=True)
    parser.add_argument("--port",type=int,default=8123)
    a=parser.parse_args()
    demo=Demo(a.db)
    server=ThreadingHTTPServer(("127.0.0.1",a.port),demo.make_handler())
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();demo.connection.close()
'''

BUG_CASES=[
    ("B01","Direct note URL enforces owner identity"),
    ("B02","Replay of an accepted order has only one durable effect"),
    ("B03","Saved settings survive a fresh app/server instance"),
    ("B04","Exported CSV cannot inject executable formula cells"),
    ("B05","Cancellation updates durable operation state"),
    ("B06","Personalized cache cannot leak across identities"),
]
CLEAN_CASES=[
    ("C01","Health endpoint works"),("C02","Public catalog works"),
    ("C03","Version identifies app"),("C04","Unknown endpoint is 404"),
    ("C05","Invalid order quantity is rejected"),
    ("C06","Owner can read their own private note"),
]

def make_buggy_target(source):
    """Compile only vulnerable branches into agent-visible source; no corrected branch or mode switch."""
    class EliminateFixedCode(ast.NodeTransformer):
        @staticmethod
        def is_fixed(expr):
            if isinstance(expr,ast.Compare) and isinstance(expr.left,ast.Name) and expr.left.id=="CURRENT_MODE" and len(expr.ops)==1 and isinstance(expr.ops[0],ast.Eq) and len(expr.comparators)==1 and isinstance(expr.comparators[0],ast.Constant) and expr.comparators[0].value=="fixed":
                return True
            if isinstance(expr,ast.BoolOp) and isinstance(expr.op,ast.And):
                return any(EliminateFixedCode.is_fixed(part) for part in expr.values)
            return False
        def visit_If(self,node):
            if self.is_fixed(node.test):
                result=[]
                for part in node.orelse:
                    got=self.visit(part)
                    if isinstance(got,list):result.extend(got)
                    elif got is not None:result.append(got)
                return result if result else [ast.Pass()]
            return self.generic_visit(node)
        def visit_IfExp(self,node):
            if self.is_fixed(node.test):return self.visit(node.orelse)
            return self.generic_visit(node)
        def visit_FunctionDef(self,node):
            node=self.generic_visit(node)
            if node.name=="start":
                # The target cannot switch to the corrected reference implementation.
                guard=ast.parse("if mode != 'buggy': raise ValueError('Only buggy fixture mode is shipped')").body[0]
                node.body=[guard]+[n for n in node.body if not isinstance(n,ast.Global) and not (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="CURRENT_MODE" for t in n.targets))]
            return node
    tree=EliminateFixedCode().visit(ast.parse(source.replace("__MODE__","buggy")))
    ast.fix_missing_locations(tree)
    code=ast.unparse(tree)+"\n"
    assert "ON CONFLICT" not in code and "CURRENT_MODE ==" not in code and "if CURRENT_MODE" not in code
    assert "replayed" in code and "volatile" in code and "app.cache" in code
    return code

def build(target_dir,grader_dir):
    target_dir=pathlib.Path(target_dir).resolve()
    grader_dir=pathlib.Path(grader_dir).resolve()
    if target_dir==grader_dir or target_dir in grader_dir.parents or grader_dir in target_dir.parents:
        raise ValueError("Agent target and grader folders must be separate trees")
    if target_dir.exists() or grader_dir.exists():
        raise ValueError("Refusing to overwrite an existing folder")
    target_dir.mkdir(parents=True)
    grader_dir.mkdir(parents=True)
    (target_dir/"service.py").write_text(make_buggy_target(TARGET_SOURCE))
    (target_dir/"PRODUCT-BRIEF.md").write_text(
        "# Synthetic product audit brief\n\n"
        "This is a localhost-only test service with fictional users. No real accounts, secrets or network integrations.\n"
        "Run service.py with --db <temporary-sqlite-file> and --port <unused-local-port>.\n"
        "The fixture supports X-Fixture-User user-a/user-b headers. Treat them as artificial identities, not production authentication.\n\n"
        "Business requirements: users may only access their own notes; retrying a successful order cannot create another order; "
        "saved settings and cancellation are durable; personalized pages cannot leak across users; "
        "CSV exports must preserve values without spreadsheet formula execution. "
        "Health, catalog, version, invalid input and missing-route behavior should remain correct.\n"
        "Use temporary databases. Reproduce defects and repair only in the owned fixture.\n")
    (grader_dir/"service_fixed.py").write_text(TARGET_SOURCE.replace("__MODE__","fixed"))
    (grader_dir/"grading_manifest.json").write_text(json.dumps(
        {"schema_version":1,"kind":"grading_only","seeded_defects":[{"id":a,"invariant":b} for a,b in BUG_CASES],
         "clean_controls":[{"id":a,"invariant":b} for a,b in CLEAN_CASES],
         "notice":"Do not expose to audit agent. Known-case fixture; not a general product benchmark."},indent=2)+"\n")
    return {"target_dir":str(target_dir),"grader_dir":str(grader_dir),
            "bug_specifications":len(BUG_CASES),"clean_specifications":len(CLEAN_CASES)}

def load_service(path):
    import sys
    import uuid
    module_name="fixture_"+uuid.uuid4().hex
    spec=importlib.util.spec_from_file_location(module_name,str(path))
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect)

def request(port,path,method="GET",body=None,headers=None):
    url="http://127.0.0.1:"+str(port)+path
    data=None if body is None else json.dumps(body).encode()
    all_headers={"Content-Type":"application/json"}
    all_headers.update(headers or {})
    req=urllib.request.Request(url, data=data,method=method,headers=all_headers)
    try:
        with OPENER.open(req,timeout=3) as res:
            return res.status,res.read().decode()
    except urllib.error.HTTPError as e:
        try:return e.code,e.read().decode()
        finally:e.close()

def verify_one(module,db,mode):
    server,thread,demo=module.start(mode,str(db))
    port=server.server_port
    checks={}
    def decoded(response,expected_status,expected_body=None):
        status,body=response
        try:obj=json.loads(body)
        except ValueError:return False
        return status==expected_status and (expected_body is None or obj==expected_body)
    try:
        checks["C01"]=decoded(request(port,"/health"),200,{"status":"ok"})
        checks["C02"]=decoded(request(port,"/v1/catalog"),200,{"products":["fixture-item"]})
        checks["C03"]=decoded(request(port,"/version"),200,{"version":"fixture-v1"})
        checks["C04"]=decoded(request(port,"/unsupported"),404,{"error":"not_found"})
        checks["C05"]=decoded(request(port,"/v1/orders","POST",{"sku":"test","qty":0},
                                       {"Idempotency-Key":"i-invalid"}),400,{"error":"invalid_qty"})
        checks["C06"]=decoded(request(port,"/v1/notes/1",headers={"X-Fixture-User":"user-a"}),
                                       200,{"owner":"user-a","content":"private-note-a"})
        checks["B01"]=decoded(request(port,"/v1/notes/2",headers={"X-Fixture-User":"user-a"}),
                                       403,{"error":"forbidden"})
        order={"sku":"fixture-item","qty":1}
        first=request(port,"/v1/orders","POST",order,{"Idempotency-Key":"order-key-1"})
        replay=request(port,"/v1/orders","POST",order,{"Idempotency-Key":"order-key-1"})
        try:
            created=json.loads(first[1]);replayed=json.loads(replay[1])
            same_order=first[0]==201 and replay[0]==200 and type(created.get("order_id")) is int and created.get("replayed") is False and replayed=={"order_id":created["order_id"],"replayed":True}
        except (ValueError,TypeError,KeyError,AttributeError):same_order=False
        with contextlib.closing(sqlite3.connect(db)) as con:
            row=con.execute("SELECT COUNT(*) FROM orders WHERE idem='order-key-1'").fetchone()[0]
        checks["B02"]=bool(same_order and row==1)
        export=request(port,"/v1/export?"+urllib.parse.urlencode({"cell":"=HYPERLINK(1,1)"}))
        parsed=list(csv.reader(io.StringIO(export[1]))) if export[0]==200 else []
        checks["B04"]=export[0]==200 and parsed==[["value"],["'=HYPERLINK(1,1)"]]
        cancel=request(port,"/v1/cancel","POST",{"operation_id":"op-1"})
        with contextlib.closing(sqlite3.connect(db)) as con:
            row=con.execute("SELECT state FROM ops WHERE id='op-1'").fetchone()[0]
        checks["B05"]=decoded(cancel,200,{"status":"cancelled"}) and row=="cancelled" and decoded(request(port,"/v1/ops/op-1"),200,{"state":"cancelled"})
        first_welcome=request(port,"/v1/welcome",headers={"X-Fixture-User":"user-a"})
        second_welcome=request(port,"/v1/welcome",headers={"X-Fixture-User":"user-b"})
        checks["B06"]=decoded(first_welcome,200,{"message":"Welcome user-a"}) and decoded(second_welcome,200,{"message":"Welcome user-b"})
        set_response=request(port,"/v1/settings","POST",{"theme":"dark"},{"X-Fixture-User":"user-a"})
        setting_write_ok=decoded(set_response,200,{"saved":True})
    finally:
        module.stop(server,thread,demo)
    # Fresh server instance with the same durable SQLite file.
    newserver,newthread,newdemo=module.start(mode,str(db))
    try:
        checks["B03"]=setting_write_ok and decoded(request(newserver.server_port,"/v1/settings",headers={"X-Fixture-User":"user-a"}),200,{"theme":"dark"})
    finally:
        module.stop(newserver,newthread,newdemo)
    return checks

def self_check():
    with tempfile.TemporaryDirectory(prefix="audit-benchmark-") as tmp:
        root=pathlib.Path(tmp)
        build(root/"agent-target",root/"grading-only")
        buggy=load_service(root/"agent-target/service.py")
        fixed=load_service(root/"grading-only/service_fixed.py")
        a=verify_one(buggy,root/"buggy.sqlite","buggy")
        b=verify_one(fixed,root/"fixed.sqlite","fixed")
        fail_b=[cid for cid,_ in BUG_CASES if a[cid] is False]
        fail_c=[cid for cid,_ in CLEAN_CASES if a[cid] is False]
        fail_fixed=[cid for cid,_ in BUG_CASES+CLEAN_CASES if b[cid] is False]
        result={"schema_version":1,"kind":"known_bug_fixture_selfcheck",
                "buggy_detected_defects":fail_b,"buggy_clean_controls_failed":fail_c,
                "corrected_failed_checks":fail_fixed,"buggy_case_count":len(BUG_CASES),
                "clean_case_count":len(CLEAN_CASES),
                "fixture_validation_passed":len(fail_b)==len(BUG_CASES) and not fail_c and not fail_fixed,
                "agent_run_executed":False,"product_accepted":False,
                "scope":"Local synthetic HTTP/SQLite service, no external product, no actual audit-agent comparison"}
        return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--target-dir",type=pathlib.Path)
    p.add_argument("--grader-dir",type=pathlib.Path)
    p.add_argument("--out",type=pathlib.Path)
    a=p.parse_args()
    try:
        if a.self_test:result=self_check()
        else:
            if not a.target_dir or not a.grader_dir:
                p.error("both --target-dir and --grader-dir required unless --self-test")
            result=build(a.target_dir,a.grader_dir)
        content=json.dumps(result,indent=2)+"\n"
        if a.out:
            with a.out.open("x") as f:f.write(content)
        else:print(content,end="")
        return 0 if not a.self_test or result["fixture_validation_passed"] else 1
    except (OSError,ValueError,KeyError,RuntimeError) as e:
        print("benchmark_fixture: "+str(e),file=__import__('sys').stderr)
        return 2
if __name__=="__main__":raise SystemExit(main())
