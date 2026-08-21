from __future__ import annotations

import hashlib
import secrets
import time
from typing import Optional

from ..database import db


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> float:
    return time.time()


def _controls() -> dict:
    return db.get_controls()


def cleanup_expired_sessions() -> int:
    now = _now()
    cur = db.execute(
        "UPDATE sessions SET revoked=1 WHERE revoked=0 AND (expires_at<=? OR (last_seen_at IS NOT NULL AND last_seen_at + ? <= ?))",
        (now, int(_controls().get("session_idle_timeout_s", 43200)), now),
    )
    return int(cur.rowcount or 0)


def _trim_device_sessions(device_id: Optional[str]) -> None:
    if not device_id:
        return
    max_sessions = int(_controls().get("max_sessions_per_device", 3))
    rows = db.query(
        "SELECT id FROM sessions WHERE device_id=? AND revoked=0 ORDER BY created_at DESC",
        (device_id,),
    )
    for row in rows[max_sessions:]:
        db.execute("UPDATE sessions SET revoked=1 WHERE id=?", (row["id"],))


def create(device_id: str | None = None, user_agent: str | None = None, ip: str | None = None) -> str:
    cleanup_expired_sessions()
    token = secrets.token_urlsafe(48)
    now = _now()
    ttl = int(_controls().get("session_ttl_s", 86400))
    db.execute(
        "INSERT INTO sessions(id,token_hash,role,device_id,created_at,expires_at,revoked,last_seen_at,user_agent,last_ip) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (db.new_id(), _hash(token), "owner", device_id, now, now + ttl, 0, now, user_agent, ip),
    )
    _trim_device_sessions(device_id)
    return token


def verify(token: str, touch: bool = True, ip: str | None = None) -> bool:
    if not token:
        return False
    cleanup_expired_sessions()
    row = db.query_one("SELECT * FROM sessions WHERE token_hash=?", (_hash(token),))
    if not row or row["revoked"]:
        return False
    now = _now()
    if float(row["expires_at"] or 0) <= now:
        db.execute("UPDATE sessions SET revoked=1 WHERE id=?", (row["id"],))
        return False
    idle_timeout = int(_controls().get("session_idle_timeout_s", 43200))
    last_seen = float(row.get("last_seen_at") or row.get("created_at") or 0)
    if last_seen + idle_timeout <= now:
        db.execute("UPDATE sessions SET revoked=1 WHERE id=?", (row["id"],))
        return False
    if touch:
        db.execute("UPDATE sessions SET last_seen_at=?, last_ip=COALESCE(?, last_ip) WHERE id=?", (now, ip, row["id"]))
    return True


def revoke(token: str) -> None:
    db.execute("UPDATE sessions SET revoked=1 WHERE token_hash=?", (_hash(token),))


def revoke_device(device_id: str) -> None:
    db.execute("UPDATE sessions SET revoked=1 WHERE device_id=?", (device_id,))


def get(token: str) -> Optional[dict]:
    if not token:
        return None
    cleanup_expired_sessions()
    row = db.query_one(
        "SELECT id, role, device_id, created_at, expires_at, revoked, last_seen_at, user_agent, last_ip FROM sessions WHERE token_hash=?",
        (_hash(token),),
    )
    if not row:
        return None
    row["active_now"] = bool(not row["revoked"] and float(row["expires_at"] or 0) > _now())
    return row
