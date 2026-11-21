import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, HttpUrl, field_validator

DB = os.getenv("DATABASE_PATH", "sentinelapi.db")
MIN_INTERVAL = int(os.getenv("CHECK_INTERVAL_MIN_SECONDS", "60"))
MAX_TIMEOUT = int(os.getenv("CHECK_TIMEOUT_MAX_SECONDS", "20"))
LOCKS: dict[str, asyncio.Lock] = {}


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def db():
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS monitors(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,name TEXT NOT NULL,url TEXT NOT NULL,interval_seconds INTEGER NOT NULL,timeout_seconds INTEGER NOT NULL,expected_status INTEGER NOT NULL,latency_threshold_ms INTEGER,is_active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,last_checked_at TEXT,last_status TEXT,last_latency_ms REAL);
        CREATE INDEX IF NOT EXISTS idx_monitors_owner ON monitors(owner_id);
        CREATE TABLE IF NOT EXISTS results(id TEXT PRIMARY KEY,monitor_id TEXT NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,checked_at TEXT NOT NULL,outcome TEXT NOT NULL,http_status INTEGER,latency_ms REAL,error_type TEXT,error_message TEXT);
        CREATE INDEX IF NOT EXISTS idx_results_monitor_time ON results(monitor_id,checked_at DESC);
        CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY,monitor_id TEXT NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,status TEXT NOT NULL,severity TEXT NOT NULL,title TEXT NOT NULL,summary TEXT NOT NULL,fingerprint TEXT NOT NULL,opened_at TEXT NOT NULL,updated_at TEXT NOT NULL,resolved_at TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_open_incident ON incidents(fingerprint) WHERE status='OPEN';
        """)


def hash_password(pw):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 310000)
    return salt.hex() + ":" + digest.hex()


def verify_password(pw, saved):
    salt, expected = saved.split(":", 1)
    actual = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 310000).hex()
    return hmac.compare_digest(actual, expected)


def safe_url(url):
    u = urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
        raise ValueError("URL must be HTTP(S), include a hostname, and contain no credentials")
    if u.port and not (1 <= u.port <= 65535):
        raise ValueError("Invalid URL port")
    try:
        addresses = {ipaddress.ip_address(u.hostname)}
    except ValueError:
        try:
            addresses = {ipaddress.ip_address(v[4][0]) for v in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), type=socket.SOCK_STREAM)}
        except OSError:
            raise ValueError("Hostname could not be resolved")
    if not addresses or any(not a.is_global for a in addresses):
        raise ValueError("Private, local, reserved, or metadata destinations are not allowed")
    return u


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)


class MonitorInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=2048)
    interval_seconds: int = Field(default=60, ge=MIN_INTERVAL, le=86400)
    timeout_seconds: int = Field(default=5, ge=1, le=MAX_TIMEOUT)
    expected_status: int = Field(default=200, ge=100, le=599)
    latency_threshold_ms: int | None = Field(default=None, ge=1, le=120000)
    is_active: bool = True

    @field_validator("url")
    @classmethod
    def valid_target(cls, v):
        safe_url(v)
        return v


@asynccontextmanager
async def lifespan(app):
    init_db()
    task = asyncio.create_task(scheduler())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="SentinelAPI", version="1.0.0", lifespan=lifespan)


def current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    with db() as c:
        row = c.execute("SELECT user_id FROM sessions WHERE token=?", (authorization[7:],)).fetchone()
    if not row:
        raise HTTPException(401, "Invalid session")
    return row["user_id"]


def owned_monitor(mid, uid):
    with db() as c:
        row = c.execute("SELECT * FROM monitors WHERE id=? AND owner_id=?", (mid, uid)).fetchone()
    if not row:
        raise HTTPException(404, "Monitor not found")
    return dict(row)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        with db() as c:
            c.execute("SELECT 1")
        return {"status": "ready", "database": "ok"}
    except sqlite3.Error:
        raise HTTPException(503, "Database unavailable")


@app.post("/api/v1/auth/register", status_code=201)
def register(data: Credentials):
    email = data.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Enter a valid email")
    try:
        with db() as c:
            c.execute("INSERT INTO users VALUES(?,?,?,?)", (str(uuid4()), email, hash_password(data.password), now()))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Email already registered")
    return {"created": True}


@app.post("/api/v1/auth/login")
def login(data: Credentials):
    with db() as c:
        user = c.execute("SELECT * FROM users WHERE email=?", (data.email.strip().lower(),)).fetchone()
        if not user or not verify_password(data.password, user["password_hash"]):
            raise HTTPException(401, "Invalid email or password")
        token = secrets.token_urlsafe(32)
        c.execute("INSERT INTO sessions VALUES(?,?,?)", (token, user["id"], now()))
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/v1/monitors")
def list_monitors(uid=Depends(current_user)):
    with db() as c:
        rows = c.execute("SELECT * FROM monitors WHERE owner_id=? ORDER BY created_at DESC", (uid,)).fetchall()
        incidents = c.execute("SELECT COUNT(*) n FROM incidents i JOIN monitors m ON i.monitor_id=m.id WHERE m.owner_id=? AND i.status='OPEN'", (uid,)).fetchone()["n"]
    return {"items": [dict(x) for x in rows], "open_incidents": incidents}


@app.post("/api/v1/monitors", status_code=201)
def create_monitor(data: MonitorInput, uid=Depends(current_user)):
    mid = str(uuid4())
    with db() as c:
        c.execute("INSERT INTO monitors(id,owner_id,name,url,interval_seconds,timeout_seconds,expected_status,latency_threshold_ms,is_active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (mid, uid, data.name, data.url, data.interval_seconds, data.timeout_seconds, data.expected_status, data.latency_threshold_ms, int(data.is_active), now()))
    return owned_monitor(mid, uid)


@app.get("/api/v1/monitors/{mid}")
def get_monitor(mid: str, uid=Depends(current_user)):
    return owned_monitor(mid, uid)


@app.patch("/api/v1/monitors/{mid}")
def update_monitor(mid: str, data: MonitorInput, uid=Depends(current_user)):
    owned_monitor(mid, uid)
    with db() as c:
        c.execute("UPDATE monitors SET name=?,url=?,interval_seconds=?,timeout_seconds=?,expected_status=?,latency_threshold_ms=?,is_active=? WHERE id=? AND owner_id=?", (data.name, data.url, data.interval_seconds, data.timeout_seconds, data.expected_status, data.latency_threshold_ms, int(data.is_active), mid, uid))
    return owned_monitor(mid, uid)


@app.delete("/api/v1/monitors/{mid}", status_code=204)
def delete_monitor(mid: str, uid=Depends(current_user)):
    owned_monitor(mid, uid)
    with db() as c:
        c.execute("DELETE FROM monitors WHERE id=? AND owner_id=?", (mid, uid))
    return Response(status_code=204)


async def perform_check(m):
    mid = m["id"]
    lock = LOCKS.setdefault(mid, asyncio.Lock())
    if lock.locked():
        raise HTTPException(429, "A check is already running")
    async with lock:
        checked = now()
        status = None
        error_type = error_message = None
        started = time.perf_counter()
        outcome = "ERROR"
        try:
            safe_url(m["url"])
            async with httpx.AsyncClient(timeout=m["timeout_seconds"], follow_redirects=False, headers={"User-Agent": "SentinelAPI/1.0"}) as client:
                async with client.stream("GET", m["url"]) as response:
                    status = response.status_code
                    if status == m["expected_status"]:
                        outcome = "UP"
                    else:
                        outcome, error_type, error_message = "DOWN", "HTTP_STATUS", f"Expected {m['expected_status']}, received {status}"
        except httpx.TimeoutException:
            outcome, error_type, error_message = "TIMEOUT", "TIMEOUT", "Request timed out"
        except httpx.HTTPError as e:
            outcome, error_type, error_message = "ERROR", type(e).__name__, "Connection or TLS error"
        except ValueError as e:
            outcome, error_type, error_message = "ERROR", "UNSAFE_TARGET", str(e)
        latency = round((time.perf_counter() - started) * 1000, 2)
        if outcome == "UP" and m["latency_threshold_ms"] and latency > m["latency_threshold_ms"]:
            outcome = "DEGRADED"
        if error_message:
            error_message = error_message[:240]
        with db() as c:
            c.execute("INSERT INTO results VALUES(?,?,?,?,?,?,?,?)", (str(uuid4()), mid, checked, outcome, status, latency, error_type, error_message))
            c.execute("UPDATE monitors SET last_checked_at=?,last_status=?,last_latency_ms=? WHERE id=?", (checked, outcome, latency, mid))
            evaluate_incident(c, m, outcome, status, latency, error_message, checked)
        return {"monitor_id": mid, "checked_at": checked, "outcome": outcome, "http_status": status, "latency_ms": latency, "error_type": error_type, "error_message": error_message}


def evaluate_incident(c, monitor, outcome, status, latency, error, stamp):
    mid = monitor["id"]
    fp = mid + ":availability"
    bad = outcome in ("DOWN", "TIMEOUT", "ERROR")
    if bad:
        recent = c.execute("SELECT outcome FROM results WHERE monitor_id=? ORDER BY checked_at DESC LIMIT 2", (mid,)).fetchall()
        if len(recent) == 2 and all(x["outcome"] in ("DOWN", "TIMEOUT", "ERROR") for x in recent):
            summary = f"Two consecutive checks failed. Latest outcome: {outcome}; HTTP status: {status}; error: {error or 'none'}."
            c.execute("INSERT INTO incidents(id,monitor_id,status,severity,title,summary,fingerprint,opened_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(fingerprint) WHERE status='OPEN' DO UPDATE SET updated_at=excluded.updated_at,summary=excluded.summary", (str(uuid4()), mid, "OPEN", "CRITICAL", "Monitor unavailable", summary, fp, stamp, stamp))
    else:
        c.execute("UPDATE incidents SET status='RESOLVED',updated_at=?,resolved_at=? WHERE fingerprint=? AND status='OPEN'", (stamp, stamp, fp))


@app.post("/api/v1/monitors/{mid}/check")
async def check_now(mid: str, uid=Depends(current_user)):
    return await perform_check(owned_monitor(mid, uid))


@app.get("/api/v1/monitors/{mid}/results")
def results(mid: str, limit: int = 100, uid=Depends(current_user)):
    owned_monitor(mid, uid)
    with db() as c:
        rows = c.execute("SELECT * FROM results WHERE monitor_id=? ORDER BY checked_at DESC LIMIT ?", (mid, min(max(limit, 1), 500))).fetchall()
    return {"items": [dict(x) for x in rows]}


@app.get("/api/v1/incidents")
def incidents(uid=Depends(current_user)):
    with db() as c:
        rows = c.execute("SELECT i.* FROM incidents i JOIN monitors m ON i.monitor_id=m.id WHERE m.owner_id=? ORDER BY i.opened_at DESC", (uid,)).fetchall()
    return {"items": [dict(x) for x in rows]}


@app.get("/api/v1/incidents/{iid}")
def incident_detail(iid: str, uid=Depends(current_user)):
    with db() as c:
        row = c.execute("SELECT i.* FROM incidents i JOIN monitors m ON i.monitor_id=m.id WHERE i.id=? AND m.owner_id=?", (iid, uid)).fetchone()
    if not row:
        raise HTTPException(404, "Incident not found")
    return dict(row)


@app.post("/api/v1/incidents/{iid}/acknowledge")
def acknowledge(iid: str, uid=Depends(current_user)):
    with db() as c:
        cur = c.execute("UPDATE incidents SET status='ACKNOWLEDGED',updated_at=? WHERE id=? AND status='OPEN' AND monitor_id IN (SELECT id FROM monitors WHERE owner_id=?)", (now(), iid, uid))
    if not cur.rowcount:
        raise HTTPException(404, "Open incident not found")
    return {"acknowledged": True}


@app.post("/api/v1/incidents/{iid}/resolve")
def resolve_incident(iid: str, uid=Depends(current_user)):
    stamp = now()
    with db() as c:
        cur = c.execute("UPDATE incidents SET status='RESOLVED',updated_at=?,resolved_at=? WHERE id=? AND status IN ('OPEN','ACKNOWLEDGED') AND monitor_id IN (SELECT id FROM monitors WHERE owner_id=?)", (stamp, stamp, iid, uid))
    if not cur.rowcount:
        raise HTTPException(404, "Incident not found")
    return {"resolved": True}


async def scheduler():
    while True:
        try:
            with db() as c:
                monitors = c.execute("SELECT * FROM monitors WHERE is_active=1").fetchall()
            current = time.time()
            for row in monitors:
                m = dict(row)
                last = m["last_checked_at"]
                due = not last or (current - datetime.fromisoformat(last).timestamp() >= m["interval_seconds"])
                if due and not LOCKS.get(m["id"], asyncio.Lock()).locked():
                    asyncio.create_task(perform_check(m))
        except Exception:
            pass
        await asyncio.sleep(5)


@app.get("/metrics", response_class=Response)
def metrics():
    with db() as c:
        counts = c.execute("SELECT last_status,COUNT(*) n FROM monitors GROUP BY last_status").fetchall()
        checks = c.execute("SELECT COUNT(*) FROM results").fetchone()[0]
        incidents = c.execute("SELECT COUNT(*) FROM incidents WHERE status='OPEN'").fetchone()[0]
        outcomes = c.execute("SELECT outcome,COUNT(*) n FROM results GROUP BY outcome").fetchall()
        latency = c.execute("SELECT AVG(latency_ms) avg_ms,MAX(latency_ms) max_ms FROM results").fetchone()
    lines = [f'sentinelapi_monitors{{state="{r["last_status"] or "UNKNOWN"}"}} {r["n"]}' for r in counts]
    lines.append(f"sentinelapi_checks_total {checks}")
    lines.extend(f'sentinelapi_check_results_total{{outcome="{r["outcome"]}"}} {r["n"]}' for r in outcomes)
    lines.extend([f"sentinelapi_open_incidents {incidents}", f"sentinelapi_check_latency_avg_ms {latency['avg_ms'] or 0}", f"sentinelapi_check_latency_max_ms {latency['max_ms'] or 0}"])
    body = "\n".join(lines)
    return Response(body + "\n", media_type="text/plain; version=0.0.4")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse("""<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>SentinelAPI</title><style>body{font:16px system-ui;background:#0b1220;color:#e5edf8;max-width:1050px;margin:40px auto;padding:0 20px}input,button{padding:10px;margin:4px;border-radius:8px;border:1px solid #334155;background:#111c30;color:inherit}button{background:#2563eb;cursor:pointer}section{background:#111c30;padding:18px;border-radius:12px;margin:14px 0}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:10px;border-bottom:1px solid #334155}.muted{color:#9aabc2}</style></head><body><h1>SentinelAPI</h1><p class='muted'>API availability monitoring</p><section><h2>Sign in / Register</h2><input id='email' placeholder='Email'><input id='password' type='password' placeholder='Password'><button onclick='auth("login")'>Sign in</button><button onclick='auth("register")'>Create account</button><span id='msg'></span></section><section id='main' hidden><h2>Add monitor</h2><input id='name' placeholder='Name'><input id='url' placeholder='https://example.com/health'><button onclick='add()'>Add monitor</button><h2>Monitors</h2><table><thead><tr><th>Name</th><th>Endpoint</th><th>Status</th><th>Latency</th><th>Actions</th></tr></thead><tbody id='rows'></tbody></table><h2>Incidents</h2><div id='incidents'></div></section><script>let token=localStorage.token;const req=async(path,method='GET',data)=>{let r=await fetch('/api/v1'+path,{method,headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},body:data?JSON.stringify(data):undefined});let d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||r.status);return d};async function auth(mode){try{if(mode==='register')await req('/auth/register','POST',{email:email.value,password:password.value});let d=await req('/auth/login','POST',{email:email.value,password:password.value});token=d.access_token;localStorage.token=token;main.hidden=false;msg.textContent='Signed in';load()}catch(e){msg.textContent=e.message}}async function add(){try{await req('/monitors','POST',{name:name.value,url:url.value});load()}catch(e){alert(e.message)}}async function check(id){try{await req('/monitors/'+id+'/check','POST');load()}catch(e){alert(e.message)}}async function load(){if(!token)return;try{let d=await req('/monitors');rows.innerHTML=d.items.map(m=>`<tr><td>${esc(m.name)}</td><td>${esc(m.url.split('?')[0])}</td><td>${m.last_status||'UNKNOWN'}</td><td>${m.last_latency_ms??'—'} ms</td><td><button onclick="check('${m.id}')">Check now</button></td></tr>`).join('');let i=await req('/incidents');incidents.innerHTML=i.items.map(x=>`<p>${esc(x.title)} — ${esc(x.summary)} (${x.status})</p>`).join('')||'No incidents'}catch(e){msg.textContent=e.message}}function esc(s){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}if(token){main.hidden=false;load()}</script></body></html>""")
