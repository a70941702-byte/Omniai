from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


class MigrationManager:
    def ensure_meta(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at REAL NOT NULL
            )
            """
        )

    def table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return bool(row)

    def column_exists(self, conn: sqlite3.Connection, table: str, column: str) -> bool:
        try:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        except sqlite3.OperationalError:
            return False
        return any(r[1] == column for r in rows)

    def add_column_if_missing(self, conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
        if not self.column_exists(conn, table, column):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    def applied_versions(self, conn: sqlite3.Connection) -> set[int]:
        self.ensure_meta(conn)
        rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        return {int(r[0]) for r in rows}

    def current_version(self, conn: sqlite3.Connection) -> int:
        self.ensure_meta(conn)
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0] or 0)

    def info(self, conn: sqlite3.Connection) -> dict:
        self.ensure_meta(conn)
        rows = conn.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        return {
            "current_version": self.current_version(conn),
            "target_version": CURRENT_SCHEMA_VERSION,
            "applied": [
                {"version": int(r[0]), "name": r[1], "applied_at": float(r[2])}
                for r in rows
            ],
        }

    def migrate(self, conn: sqlite3.Connection) -> None:
        self.ensure_meta(conn)
        applied = self.applied_versions(conn)
        for migration in MIGRATIONS:
            if migration.version in applied:
                continue
            with conn:
                migration.apply(conn)
                conn.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at) VALUES(?,?,?)",
                    (migration.version, migration.name, time.time()),
                )


migration_manager = MigrationManager()


def _migration_1_base_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            prev_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            model_id TEXT,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS memory (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            text TEXT NOT NULL,
            text_hash TEXT,
            vector TEXT NOT NULL,
            importance REAL NOT NULL DEFAULT 0.5,
            pinned INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            last_access REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS datasets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version INTEGER NOT NULL,
            status TEXT NOT NULL,
            samples TEXT NOT NULL,
            quality_report TEXT,
            created_at REAL NOT NULL,
            UNIQUE(name, version)
        );
        CREATE TABLE IF NOT EXISTS models (
            id TEXT PRIMARY KEY,
            version INTEGER NOT NULL,
            parent_id TEXT,
            intent_labels TEXT,
            config TEXT,
            status TEXT NOT NULL,
            metrics TEXT,
            resource_usage TEXT,
            checkpoint_path TEXT,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS training_cycles (
            id TEXT PRIMARY KEY,
            cycle_no INTEGER NOT NULL,
            phase TEXT NOT NULL,
            status TEXT NOT NULL,
            base_model_id TEXT,
            candidate_model_id TEXT,
            report TEXT,
            created_at REAL NOT NULL,
            finished_at REAL
        );
        CREATE TABLE IF NOT EXISTS eval_runs (
            id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL,
            suite TEXT NOT NULL,
            score REAL NOT NULL,
            details TEXT,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            decision_note TEXT,
            created_at REAL NOT NULL,
            decided_at REAL
        );
        CREATE TABLE IF NOT EXISTS controls (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS improvement_proposals (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            analysis TEXT NOT NULL,
            patch TEXT,
            test_output TEXT,
            status TEXT NOT NULL DEFAULT 'proposed',
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS backups (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            note TEXT,
            created_at REAL NOT NULL
        );
        """
    )


def _migration_2_extended_runtime_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            token_hash TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL,
            device_id TEXT,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS tool_audit (
            id TEXT PRIMARY KEY,
            tool TEXT NOT NULL,
            actor TEXT NOT NULL,
            started_at REAL NOT NULL,
            finished_at REAL,
            ok INTEGER NOT NULL,
            detail TEXT
        );
        CREATE TABLE IF NOT EXISTS costs (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            metadata TEXT,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS model_artifacts (
            id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL,
            base_model TEXT,
            adapter TEXT,
            quantization TEXT,
            dataset_version TEXT,
            training_config TEXT,
            evaluation TEXT,
            parent_model TEXT,
            created_at REAL NOT NULL,
            approved_at REAL
        );
        CREATE TABLE IF NOT EXISTS training_samples (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            intent TEXT,
            source TEXT NOT NULL,
            timestamp REAL NOT NULL,
            quality_score REAL NOT NULL,
            confidence REAL NOT NULL,
            provenance TEXT,
            approval_status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rag_chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            source TEXT,
            embedding TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        """
    )
    for col, typ in (
        ("source", "TEXT"),
        ("confidence", "REAL"),
        ("expires_at", "REAL"),
        ("approved", "INTEGER"),
    ):
        migration_manager.add_column_if_missing(conn, "memory", col, typ)
    for col, typ in (
        ("model_type", "TEXT"),
        ("base_model", "TEXT"),
        ("adapter", "TEXT"),
        ("quantization", "TEXT"),
        ("training_dataset", "TEXT"),
        ("training_config", "TEXT"),
        ("evaluation_score", "REAL"),
        ("approved_at", "REAL"),
    ):
        migration_manager.add_column_if_missing(conn, "models", col, typ)
    conn.execute(
        "UPDATE memory SET source=COALESCE(source,'owner'), confidence=COALESCE(confidence,1.0), approved=COALESCE(approved,1)"
    )


def _migration_3_indexes_and_metadata(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_messages_conversation_created_at
            ON messages(conversation_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_kind_created_at
            ON memory(kind, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_models_status_created_at
            ON models(status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_training_cycles_cycle_no
            ON training_cycles(cycle_no DESC);
        CREATE INDEX IF NOT EXISTS idx_approvals_status_created_at
            ON approvals(status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_eval_runs_model_created_at
            ON eval_runs(model_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_rag_chunks_document_chunk
            ON rag_chunks(document_id, chunk_index);
        """
    )


def _migration_4_state_bundles(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS state_bundles (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            note TEXT,
            manifest_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'exported',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_state_bundles_created_at
            ON state_bundles(created_at DESC);
        """
    )


def _migration_5_session_hardening(conn: sqlite3.Connection) -> None:
    for col, typ in (
        ("last_seen_at", "REAL"),
        ("user_agent", "TEXT"),
        ("last_ip", "TEXT"),
    ):
        migration_manager.add_column_if_missing(conn, "sessions", col, typ)
    conn.execute("UPDATE sessions SET last_seen_at=COALESCE(last_seen_at, created_at)")
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
        CREATE INDEX IF NOT EXISTS idx_sessions_device_created ON sessions(device_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_sessions_revoked_expires ON sessions(revoked, expires_at DESC);
        """
    )


MIGRATIONS = [
    Migration(1, "base_schema", _migration_1_base_schema),
    Migration(2, "extended_runtime_schema", _migration_2_extended_runtime_schema),
    Migration(3, "indexes_and_metadata", _migration_3_indexes_and_metadata),
    Migration(4, "state_bundles", _migration_4_state_bundles),
    Migration(5, "session_hardening", _migration_5_session_hardening),
]
CURRENT_SCHEMA_VERSION = MIGRATIONS[-1].version
