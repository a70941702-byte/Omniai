"""SQLite storage layer. One table per subsystem; all writes go through here
so the audit log can observe state changes. Thread-safe via a lock."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .config import DB_PATH
from .migrations import migration_manager


class Database:
    def __init__(self, path: Path = DB_PATH):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        with self._lock:
            migration_manager.migrate(self._conn)
            self._conn.commit()

    def schema_info(self) -> dict:
        with self._lock:
            return migration_manager.info(self._conn)

    def table_exists(self, table: str) -> bool:
        with self._lock:
            return migration_manager.table_exists(self._conn, table)

    def column_exists(self, table: str, column: str) -> bool:
        with self._lock:
            return migration_manager.column_exists(self._conn, table, column)

    # ---- generic helpers -------------------------------------------------
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def query_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # ---- controls ---------------------------------------------------------
    DEFAULT_CONTROLS = {
        "training_enabled": True,
        "learning_enabled": True,
        "internet_enabled": False,
        "external_models_enabled": False,
        "code_edit_enabled": True,
        "install_deps_enabled": False,
        "server_enabled": False,
        "cpu_limit_percent": 80,
        "ram_limit_mb": 2048,
        "gpu_enabled": False,
        "storage_limit_mb": 4096,
        "budget_credits": 1000,
        "budget_spent": 0,
        "autonomous_cycles": True,
        "python_enabled": True,
        "terminal_enabled": False,
        "web_enabled": False,
        "tools_enabled": True,
        "agent_approved_tools": False,
        "code_editing_enabled": True,
        "kill_switch": False,
        "last_emergency_stop_at": 0.0,
        "last_emergency_stop_reason": "",
        "last_emergency_bundle_id": "",
        "domain_allowlist": [],
        "domain_blocklist": [],
        "session_ttl_s": 86400,
        "session_idle_timeout_s": 43200,
        "max_sessions_per_device": 3,
        "approval_read": "LOW",
        "approval_analyze": "LOW",
        "approval_tests": "MEDIUM",
        "approval_patch": "MEDIUM",
        "approval_code_edit": "HIGH",
        "approval_dependency": "HIGH",
        "approval_training": "HIGH",
        "approval_internet": "CRITICAL",
        "approval_model_promote": "CRITICAL",
    }

    def get_controls(self) -> dict:
        rows = self.query("SELECT key, value FROM controls")
        controls = dict(self.DEFAULT_CONTROLS)
        for r in rows:
            try:
                controls[r["key"]] = json.loads(r["value"])
            except Exception:
                controls[r["key"]] = r["value"]
        return controls

    def set_control(self, key: str, value: Any) -> None:
        if key not in self.DEFAULT_CONTROLS:
            raise KeyError(f"unknown control: {key}")
        self.execute(
            "INSERT INTO controls(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
        aliases = {"code_edit_enabled": "code_editing_enabled", "code_editing_enabled": "code_edit_enabled"}
        if key in aliases:
            self.execute(
                "INSERT INTO controls(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (aliases[key], json.dumps(value)),
            )

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:16]

    @staticmethod
    def now() -> float:
        return time.time()


db = Database()
