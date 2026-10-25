import os, re, secrets, sqlite3, hashlib, time
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import logic

ROOT = Path(__file__).parent
UP = ROOT / "uploads"; UP.mkdir(exist_ok=True)
DB = ROOT / "dbrait.db"
app = FastAPI(title="DBRAIT Repository")

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(8)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000).hex()

def check_pw(pw, stored):
    return secrets.compare_digest(hash_pw(pw, stored.split("$")[0]), stored)

def init():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, name TEXT, role TEXT, pw TEXT);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER, created REAL);
    CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY, sem INT, code TEXT UNIQUE, name TEXT, l INT, t INT, p INT);
    CREATE TABLE IF NOT EXISTS papers(id INTEGER PRIMARY KEY, course_id INT REFERENCES courses(id), title TEXT, category TEXT,
        year INT, session TEXT, attempt TEXT, filename TEXT, orig TEXT, uploader INT REFERENCES users(id), hidden INT DEFAULT 0, at REAL);
    CREATE TABLE IF NOT EXISTS attendance(user_id INT, course_id INT, attended INT DEFAULT 0, total INT DEFAULT 0,
        medical INT DEFAULT 0, activity INT DEFAULT 0, PRIMARY KEY(user_id, course_id));
    CREATE TABLE IF NOT EXISTS grades(user_id INT, comp TEXT, grade TEXT, PRIMARY KEY(user_id, comp));
    """)
    if not c.execute("SELECT 1 FROM courses").fetchone():
        c.executemany("INSERT INTO courses(sem,code,name,l,t,p) VALUES(?,?,?,?,?,?)", logic.CURRICULUM)
    if not c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        pw = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(8)
        c.execute("INSERT INTO users(username,name,role,pw) VALUES('admin','Admin','admin',?)", (hash_pw(pw),))
        print(f"\n*** First run: admin login -> username: admin  password: {pw}\n")
    c.commit(); c.close()
init()

def me(req, required=True):
    tok = req.cookies.get("sid")
    c = db()
    r = c.execute("SELECT u.id,u.username,u.name,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?", (tok,)).fetchone() if tok else None
    c.close()
    if required and not r: raise HTTPException(401, "Please log in.")
    return dict(r) if r else None

def start_session(res, uid):
    tok = secrets.token_urlsafe(24); c = db()
    c.execute("INSERT INTO sessions VALUES(?,?,?)", (tok, uid, time.time())); c.commit(); c.close()
    res.set_cookie("sid", tok, httponly=True, samesite="lax", max_age=60*60*24*14)

class Cred(BaseModel):
    username: str; password: str; name: str = ""

@app.post("/api/register")
def register(b: Cred, res: Response):
    u = b.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,30}", u): raise HTTPException(400, "Username: 3-30 letters, digits, . _ -")
    if len(b.password) < 8: raise HTTPException(400, "Password needs at least 8 characters.")
    c = db()
    try: cur = c.execute("INSERT INTO users(username,name,role,pw) VALUES(?,?,?,?)", (u, b.name.strip() or u, "student", hash_pw(b.password)))
    except sqlite3.IntegrityError: raise HTTPException(400, "That username is taken.")
    c.commit(); start_session(res, cur.lastrowid); c.close(); return {"ok": True}

@app.post("/api/login")
def login(b: Cred, res: Response):
    c = db(); r = c.execute("SELECT * FROM users WHERE username=?", (b.username.strip().lower(),)).fetchone(); c.close()
    if not r or not check_pw(b.password, r["pw"]): raise HTTPException(401, "Wrong username or password.")
    start_session(res, r["id"]); return {"ok": True}

@app.post("/api/logout")
def logout(req: Request, res: Response):
    c = db(); c.execute("DELETE FROM sessions WHERE token=?", (req.cookies.get("sid"),)); c.commit(); c.close()
    res.delete_cookie("sid"); return {"ok": True}

@app.get("/api/me")
def whoami(req: Request): return me(req, False)

@app.post("/api/admin/faculty")
def make_faculty(req: Request, b: Cred):
    if me(req)["role"] != "admin": raise HTTPException(403, "Admin only.")
    c = db(); n = c.execute("SELECT COUNT(*) FROM users WHERE role='faculty'").fetchone()[0] + 1
    uname, pw = f"FAC-{n:04d}", secrets.token_urlsafe(6)
    c.execute("INSERT INTO users(username,name,role,pw) VALUES(?,?,?,?)", (uname.lower(), b.name or uname, "faculty", hash_pw(pw)))
    c.commit(); c.close(); return {"username": uname.lower(), "password": pw}

@app.get("/api/courses")
def courses(sem: int = 0):
    c = db(); rows = c.execute("SELECT * FROM courses WHERE (?=0 OR sem=?) ORDER BY sem,code", (sem, sem)).fetchall(); c.close()
    return [dict(r) | {"components": logic.components(r["code"], r["l"], r["t"], r["p"])} for r in rows]

@app.get("/api/papers")
def papers(q: str = "", course_id: int = 0, sem: int = 0, category: str = "", attempt: str = ""):
    c = db()
    rows = c.execute("""SELECT p.*, c.code, c.name cname, c.sem, u.name uname FROM papers p JOIN courses c ON c.id=p.course_id
        JOIN users u ON u.id=p.uploader WHERE p.hidden=0 AND (?=0 OR p.course_id=?) AND (?=0 OR c.sem=?)
        AND (?='' OR p.category=?) AND (?='' OR p.attempt=?)
        AND (?='' OR p.title LIKE ? OR c.name LIKE ? OR c.code LIKE ? OR p.session LIKE ?) ORDER BY p.year DESC, p.at DESC""",
        (course_id, course_id, sem, sem, category, category, attempt, attempt, q, f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
    c.close(); return [dict(r) for r in rows]

ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
@app.post("/api/papers")
async def upload(req: Request, file: UploadFile = File(...), course_id: int = Form(...), title: str = Form(""),
                 category: str = Form("University End-Sem"), year: int = Form(...), session: str = Form(""), attempt: str = Form("1st Attempt (Regular)")):
    u = me(req); ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED: raise HTTPException(400, "Upload a PDF or an image (PNG, JPG, WEBP).")
    data = await file.read()
    if len(data) > 25 * 1024 * 1024: raise HTTPException(400, "File is over 25 MB.")
    name = secrets.token_hex(8) + ext; (UP / name).write_bytes(data)
    c = db(); co = c.execute("SELECT code,name FROM courses WHERE id=?", (course_id,)).fetchone()
    if not co: raise HTTPException(400, "Pick a course.")
    c.execute("INSERT INTO papers(course_id,title,category,year,session,attempt,filename,orig,uploader,at) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (course_id, title.strip() or f"{co['code']} {co['name']} {year}", category, year, session, attempt, name, file.filename, u["id"], time.time()))
    c.commit(); c.close(); return {"ok": True}

@app.delete("/api/papers/{pid}")
def remove(pid: int, req: Request):
    u = me(req); c = db(); p = c.execute("SELECT uploader FROM papers WHERE id=?", (pid,)).fetchone()
    if not p: raise HTTPException(404, "Not found.")
    if u["role"] != "admin" and p["uploader"] != u["id"]: raise HTTPException(403, "Only the uploader or admin can remove this.")
    c.execute("UPDATE papers SET hidden=1 WHERE id=?", (pid,)); c.commit(); c.close(); return {"ok": True}

@app.get("/files/{name}")
def get_file(name: str, req: Request):
    me(req)
    if not re.fullmatch(r"[a-f0-9]{16}\.\w+", name): raise HTTPException(404)
    return FileResponse(UP / name)

class Att(BaseModel):
    course_id: int; attended: int; total: int; medical: bool = False; activity: bool = False

@app.get("/api/attendance")
def get_att(req: Request, sem: int = 5):
    u = me(req); c = db()
    rows = c.execute("""SELECT c.id course_id,c.code,c.name,COALESCE(a.attended,0) attended,COALESCE(a.total,0) total,
        COALESCE(a.medical,0) medical,COALESCE(a.activity,0) activity FROM courses c LEFT JOIN attendance a ON a.course_id=c.id AND a.user_id=?
        WHERE c.sem=? AND (c.l+c.t>0 OR c.p>0) AND c.code NOT IN ('IKS306','CI208','ES215','SY114','IL107') ORDER BY c.code""", (u["id"], sem)).fetchall(); c.close()
    return [dict(r) | logic.attendance_status(r["attended"], r["total"], bool(r["medical"]), bool(r["activity"])) | {"delta": logic.classes_to_75(r["attended"], r["total"])} for r in rows]

@app.put("/api/attendance")
def put_att(b: Att, req: Request):
    u = me(req)
    if b.attended < 0 or b.total < b.attended: raise HTTPException(400, "Attended can't be more than total classes.")
    c = db(); c.execute("INSERT OR REPLACE INTO attendance VALUES(?,?,?,?,?,?)", (u["id"], b.course_id, b.attended, b.total, int(b.medical), int(b.activity)))
    c.commit(); c.close(); return {"ok": True}

class Grade(BaseModel):
    comp: str; grade: str

@app.put("/api/grades")
def put_grade(b: Grade, req: Request):
    u = me(req)
    if b.grade not in list(logic.GRADE_POINTS) + ["MP", ""]: raise HTTPException(400, "Unknown grade.")
    c = db()
    if b.grade == "": c.execute("DELETE FROM grades WHERE user_id=? AND comp=?", (u["id"], b.comp))
    else: c.execute("INSERT OR REPLACE INTO grades VALUES(?,?,?)", (u["id"], b.comp, b.grade))
    c.commit(); c.close(); return {"ok": True}

@app.get("/api/grades")
def get_grades(req: Request):
    u = me(req); c = db()
    g = {r["comp"]: r["grade"] for r in c.execute("SELECT comp,grade FROM grades WHERE user_id=?", (u["id"],))}
    cs = c.execute("SELECT * FROM courses ORDER BY sem,code").fetchall(); c.close()
    sems, all_rows = {}, []
    for r in cs:
        for comp in logic.components(r["code"], r["l"], r["t"], r["p"]):
            comp = comp | {"course": r["name"], "grade": g.get(comp["code"], "")}
            sems.setdefault(r["sem"], []).append(comp)
    out = []
    for s, comps in sems.items():
        rows = [(x["credits"], x["grade"]) for x in comps]; all_rows += rows
        out.append({"sem": s, "sgpa": logic.sgpa(rows), "comps": comps})
    return {"semesters": out, "cgpa": logic.sgpa(all_rows), "scale": logic.GRADE_POINTS}

@app.get("/")
def index(): return FileResponse(ROOT / "static" / "index.html")
