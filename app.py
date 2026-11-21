import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from assertions import assertion_passes, validate_json_path
import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

DB = os.getenv("DATABASE_PATH", "sentinelapi.db")
MIN_INTERVAL = int(os.getenv("CHECK_INTERVAL_MIN_SECONDS", "60"))
MAX_TIMEOUT = int(os.getenv("CHECK_TIMEOUT_MAX_SECONDS", "20"))
LOCKS: dict[str, asyncio.Lock] = {}
CASE_LOCKS: dict[str, asyncio.Lock] = {}
MAX_ASSERTION_RESPONSE_BYTES = 262144
MAX_CASES_PER_MONITOR = 25
CASE_SEMAPHORE = asyncio.Semaphore(10)


class ResponseLimitError(Exception):
    pass


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
        CREATE TABLE IF NOT EXISTS test_cases(id TEXT PRIMARY KEY,monitor_id TEXT NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,name TEXT NOT NULL,url TEXT NOT NULL,expected_status INTEGER NOT NULL,timeout_seconds INTEGER NOT NULL,latency_threshold_ms INTEGER,assertions_json TEXT NOT NULL DEFAULT '[]',is_active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_test_cases_monitor ON test_cases(monitor_id,is_active);
        CREATE TABLE IF NOT EXISTS test_case_results(id TEXT PRIMARY KEY,test_case_id TEXT NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,checked_at TEXT NOT NULL,outcome TEXT NOT NULL,http_status INTEGER,latency_ms REAL,error_type TEXT,error_message TEXT,assertions_passed INTEGER NOT NULL DEFAULT 0,assertions_total INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS idx_case_results_case_time ON test_case_results(test_case_id,checked_at DESC);
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


class JsonAssertion(BaseModel):
    path: str = Field(min_length=1, max_length=200)
    operator: Literal["equals", "not_equals", "contains", "gt", "gte", "lt", "lte", "exists", "not_exists"]
    value: Any = None

    @field_validator("path")
    @classmethod
    def valid_path(cls, value):
        return validate_json_path(value)


class TestCaseInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=2048)
    expected_status: int = Field(default=200, ge=100, le=599)
    timeout_seconds: int = Field(default=5, ge=1, le=MAX_TIMEOUT)
    latency_threshold_ms: int | None = Field(default=None, ge=1, le=120000)
    assertions: list[JsonAssertion] = Field(default_factory=list, max_length=20)
    is_active: bool = True

    @field_validator("url")
    @classmethod
    def valid_target(cls, value):
        safe_url(value)
        return value


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


def owned_test_case(case_id, uid):
    with db() as c:
        row = c.execute("SELECT tc.* FROM test_cases tc JOIN monitors m ON m.id=tc.monitor_id WHERE tc.id=? AND m.owner_id=?", (case_id, uid)).fetchone()
    if not row:
        raise HTTPException(404, "Test case not found")
    result = dict(row)
    result["assertions"] = json.loads(result.pop("assertions_json"))
    return result


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
            async with CASE_SEMAPHORE:
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


async def run_test_case(test_case):
    case_id = test_case["id"]
    lock = CASE_LOCKS.setdefault(case_id, asyncio.Lock())
    if lock.locked():
        raise HTTPException(429, "This test case is already running")
    async with lock:
        checked, status = now(), None
        started = time.perf_counter()
        outcome, error_type, error_message = "ERROR", None, None
        passed, total = 0, len(test_case["assertions"])
        try:
            safe_url(test_case["url"])
            async with CASE_SEMAPHORE:
                async with httpx.AsyncClient(timeout=test_case["timeout_seconds"], follow_redirects=False, headers={"User-Agent": "SentinelAPI/1.0"}) as client:
                    async with client.stream("GET", test_case["url"]) as response:
                        status = response.status_code
                        if status != test_case["expected_status"]:
                            outcome, error_type = "DOWN", "HTTP_STATUS"
                            error_message = f"Expected HTTP {test_case['expected_status']}, received {status}"
                        else:
                            assertions = test_case["assertions"]
                            if assertions:
                                body = bytearray()
                                async for chunk in response.aiter_bytes():
                                    body.extend(chunk)
                                    if len(body) > MAX_ASSERTION_RESPONSE_BYTES:
                                        raise ResponseLimitError("Response exceeded the 256 KiB assertion limit")
                                try:
                                    document = json.loads(body)
                                except (json.JSONDecodeError, UnicodeDecodeError):
                                    outcome, error_type, error_message = "VALIDATION_FAILED", "INVALID_JSON", "Response body is not valid JSON"
                                else:
                                    failed = []
                                    for assertion in assertions:
                                        if assertion_passes(document, assertion):
                                            passed += 1
                                        else:
                                            failed.append(f"{assertion['path']} {assertion['operator']}")
                                    if failed:
                                        outcome, error_type = "VALIDATION_FAILED", "ASSERTION_FAILED"
                                        error_message = "Failed assertions: " + ", ".join(failed)
                                    else:
                                        outcome = "UP"
                            else:
                                outcome = "UP"
        except httpx.TimeoutException:
            outcome, error_type, error_message = "TIMEOUT", "TIMEOUT", "Request timed out"
        except httpx.HTTPError as error:
            outcome, error_type, error_message = "ERROR", type(error).__name__, "Connection or TLS error"
        except ResponseLimitError as error:
            outcome, error_type, error_message = "VALIDATION_FAILED", "RESPONSE_TOO_LARGE", str(error)
        except ValueError as error:
            outcome, error_type, error_message = "ERROR", "UNSAFE_TARGET", str(error)
        latency = round((time.perf_counter() - started) * 1000, 2)
        if outcome == "UP" and test_case["latency_threshold_ms"] and latency > test_case["latency_threshold_ms"]:
            outcome = "DEGRADED"
        if error_message:
            error_message = error_message[:240]
        with db() as c:
            c.execute("INSERT INTO test_case_results(id,test_case_id,checked_at,outcome,http_status,latency_ms,error_type,error_message,assertions_passed,assertions_total) VALUES(?,?,?,?,?,?,?,?,?,?)", (str(uuid4()), case_id, checked, outcome, status, latency, error_type, error_message, passed, total))
            evaluate_case_incident(c, test_case, outcome, status, latency, error_message, checked)
        return {"test_case_id": case_id, "checked_at": checked, "outcome": outcome, "http_status": status, "latency_ms": latency, "error_type": error_type, "error_message": error_message, "assertions_passed": passed, "assertions_total": total}


def evaluate_case_incident(c, test_case, outcome, status, latency, error, stamp):
    case_id = test_case["id"]
    fingerprint = case_id + ":test-case"
    recent = c.execute("SELECT outcome FROM test_case_results WHERE test_case_id=? ORDER BY checked_at DESC LIMIT 2", (case_id,)).fetchall()
    bad = {"DOWN", "TIMEOUT", "ERROR", "VALIDATION_FAILED"}
    if len(recent) == 2 and all(row["outcome"] in bad for row in recent):
        severity = "CRITICAL" if outcome in {"DOWN", "TIMEOUT", "ERROR"} else "WARNING"
        summary = f"Two consecutive test-case runs failed. Latest outcome: {outcome}; HTTP status: {status}; latency: {latency} ms; error: {error or 'assertions did not pass'}."
        existing = c.execute("SELECT id FROM incidents WHERE fingerprint=? AND status IN ('OPEN','ACKNOWLEDGED')", (fingerprint,)).fetchone()
        if existing:
            c.execute("UPDATE incidents SET updated_at=?,summary=?,severity=? WHERE id=?", (stamp, summary, severity, existing["id"]))
        else:
            c.execute("INSERT INTO incidents(id,monitor_id,status,severity,title,summary,fingerprint,opened_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (str(uuid4()), test_case["monitor_id"], "OPEN", severity, f"Test case failing: {test_case['name']}", summary, fingerprint, stamp, stamp))
    elif len(recent) == 2 and all(row["outcome"] in {"UP", "DEGRADED"} for row in recent):
        c.execute("UPDATE incidents SET status='RESOLVED',updated_at=?,resolved_at=? WHERE fingerprint=? AND status IN ('OPEN','ACKNOWLEDGED')", (stamp, stamp, fingerprint))


async def run_monitor_suite(monitor):
    monitor_result = await perform_check(monitor)
    with db() as c:
        cases = [dict(row) for row in c.execute("SELECT * FROM test_cases WHERE monitor_id=? AND is_active=1", (monitor["id"],)).fetchall()]
    for case in cases:
        case["assertions"] = json.loads(case.pop("assertions_json"))
    results = await asyncio.gather(*(run_test_case(case) for case in cases), return_exceptions=True)
    case_results = []
    for case, result in zip(cases, results):
        if isinstance(result, Exception):
            message = result.detail if isinstance(result, HTTPException) else str(result)
            case_results.append({"test_case_id": case["id"], "error": str(message)[:240]})
        else:
            case_results.append(result)
    return {**monitor_result, "test_cases": case_results}


def evaluate_incident(c, monitor, outcome, status, latency, error, stamp):
    mid = monitor["id"]
    fp = mid + ":availability"
    bad = outcome in ("DOWN", "TIMEOUT", "ERROR")
    if bad:
        recent = c.execute("SELECT outcome FROM results WHERE monitor_id=? ORDER BY checked_at DESC LIMIT 2", (mid,)).fetchall()
        if len(recent) == 2 and all(x["outcome"] in ("DOWN", "TIMEOUT", "ERROR") for x in recent):
            summary = f"Two consecutive checks failed. Latest outcome: {outcome}; HTTP status: {status}; error: {error or 'none'}."
            existing = c.execute("SELECT id FROM incidents WHERE fingerprint=? AND status IN ('OPEN','ACKNOWLEDGED')", (fp,)).fetchone()
            if existing:
                c.execute("UPDATE incidents SET updated_at=?,summary=? WHERE id=?", (stamp, summary, existing["id"]))
            else:
                c.execute("INSERT INTO incidents(id,monitor_id,status,severity,title,summary,fingerprint,opened_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (str(uuid4()), mid, "OPEN", "CRITICAL", "Monitor unavailable", summary, fp, stamp, stamp))
    else:
        c.execute("UPDATE incidents SET status='RESOLVED',updated_at=?,resolved_at=? WHERE fingerprint=? AND status IN ('OPEN','ACKNOWLEDGED')", (stamp, stamp, fp))


@app.post("/api/v1/monitors/{mid}/check")
async def check_now(mid: str, uid=Depends(current_user)):
    return await run_monitor_suite(owned_monitor(mid, uid))


@app.get("/api/v1/monitors/{mid}/test-cases")
def list_test_cases(mid: str, uid=Depends(current_user)):
    owned_monitor(mid, uid)
    with db() as c:
        rows = c.execute("SELECT tc.*,(SELECT json_object('outcome',cr.outcome,'latency_ms',cr.latency_ms,'checked_at',cr.checked_at,'assertions_passed',cr.assertions_passed,'assertions_total',cr.assertions_total) FROM test_case_results cr WHERE cr.test_case_id=tc.id ORDER BY cr.checked_at DESC,cr.id DESC LIMIT 1) AS latest_result FROM test_cases tc WHERE tc.monitor_id=? ORDER BY tc.created_at", (mid,)).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["assertions"] = json.loads(item.pop("assertions_json"))
        item["latest_result"] = json.loads(item["latest_result"]) if item["latest_result"] else None
        items.append(item)
    return {"items": items}


@app.post("/api/v1/monitors/{mid}/test-cases", status_code=201)
def create_test_case(mid: str, data: TestCaseInput, uid=Depends(current_user)):
    owned_monitor(mid, uid)
    with db() as c:
        count = c.execute("SELECT COUNT(*) FROM test_cases WHERE monitor_id=?", (mid,)).fetchone()[0]
        if count >= MAX_CASES_PER_MONITOR:
            raise HTTPException(422, f"A monitor can have at most {MAX_CASES_PER_MONITOR} test cases")
        case_id = str(uuid4())
        assertions = json.dumps([item.model_dump() for item in data.assertions], ensure_ascii=False)
        c.execute("INSERT INTO test_cases(id,monitor_id,name,url,expected_status,timeout_seconds,latency_threshold_ms,assertions_json,is_active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (case_id, mid, data.name, data.url, data.expected_status, data.timeout_seconds, data.latency_threshold_ms, assertions, int(data.is_active), now()))
    return owned_test_case(case_id, uid)


@app.patch("/api/v1/test-cases/{case_id}")
def update_test_case(case_id: str, data: TestCaseInput, uid=Depends(current_user)):
    owned_test_case(case_id, uid)
    assertions = json.dumps([item.model_dump() for item in data.assertions], ensure_ascii=False)
    with db() as c:
        c.execute("UPDATE test_cases SET name=?,url=?,expected_status=?,timeout_seconds=?,latency_threshold_ms=?,assertions_json=?,is_active=? WHERE id=?", (data.name, data.url, data.expected_status, data.timeout_seconds, data.latency_threshold_ms, assertions, int(data.is_active), case_id))
    return owned_test_case(case_id, uid)


@app.delete("/api/v1/test-cases/{case_id}", status_code=204)
def delete_test_case(case_id: str, uid=Depends(current_user)):
    owned_test_case(case_id, uid)
    with db() as c:
        c.execute("DELETE FROM test_cases WHERE id=?", (case_id,))
    return Response(status_code=204)


@app.post("/api/v1/test-cases/{case_id}/run")
async def run_test_case_now(case_id: str, uid=Depends(current_user)):
    return await run_test_case(owned_test_case(case_id, uid))


@app.get("/api/v1/test-cases/{case_id}/results")
def test_case_history(case_id: str, limit: int = 100, uid=Depends(current_user)):
    owned_test_case(case_id, uid)
    with db() as c:
        rows = c.execute("SELECT * FROM test_case_results WHERE test_case_id=? ORDER BY checked_at DESC LIMIT ?", (case_id, min(max(limit, 1), 500))).fetchall()
    return {"items": [dict(row) for row in rows]}


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
                    asyncio.create_task(run_monitor_suite(m))
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
        active_cases = c.execute("SELECT COUNT(*) FROM test_cases WHERE is_active=1").fetchone()[0]
        case_outcomes = c.execute("SELECT r.outcome,COUNT(*) n FROM test_case_results r JOIN test_cases tc ON tc.id=r.test_case_id GROUP BY r.outcome").fetchall()
        latency = c.execute("SELECT AVG(latency_ms) avg_ms,MAX(latency_ms) max_ms FROM results").fetchone()
    lines = [f'sentinelapi_monitors{{state="{r["last_status"] or "UNKNOWN"}"}} {r["n"]}' for r in counts]
    lines.append(f"sentinelapi_checks_total {checks}")
    lines.extend(f'sentinelapi_check_results_total{{outcome="{r["outcome"]}"}} {r["n"]}' for r in outcomes)
    lines.extend(f'sentinelapi_test_case_results_total{{outcome="{r["outcome"]}"}} {r["n"]}' for r in case_outcomes)
    lines.extend([f"sentinelapi_active_test_cases {active_cases}", f"sentinelapi_open_incidents {incidents}", f"sentinelapi_check_latency_avg_ms {latency['avg_ms'] or 0}", f"sentinelapi_check_latency_max_ms {latency['max_ms'] or 0}"])
    body = "\n".join(lines)
    return Response(body + "\n", media_type="text/plain; version=0.0.4")


@app.get("/", response_class=HTMLResponse)
def dashboard_detail_ui():
    page = Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")
    return HTMLResponse(page)
