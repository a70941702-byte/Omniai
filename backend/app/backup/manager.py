"""Backup, state bundles, and rollback utilities.

Backups snapshot the DB + checkpoints into a timestamped directory.
State bundles add a structured manifest so a whole OmniAI state can be verified,
ported, and restored later. The AI cannot delete backups/bundles (no delete API
is exposed).
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from ..config import BACKUPS_DIR, CHECKPOINTS_DIR, DB_PATH
from ..database import db
from ..security import audit


class BackupManager:
    def create(self, note: str = "") -> dict:
        bid = db.new_id()
        dest = BACKUPS_DIR / f"backup_{int(time.time())}_{bid}"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DB_PATH, dest / "omniai.db")
        ckpt_dest = dest / "checkpoints"
        shutil.copytree(CHECKPOINTS_DIR, ckpt_dest, dirs_exist_ok=True)
        db.execute(
            "INSERT INTO backups(id, path, note, created_at) VALUES(?,?,?,?)",
            (bid, str(dest), note, db.now()),
        )
        audit.log("system", "backup_created", {"id": bid, "note": note})
        return {"id": bid, "path": str(dest), "note": note}

    def list(self) -> list[dict]:
        return db.query("SELECT * FROM backups ORDER BY created_at DESC")

    def restore(self, backup_id: str, actor: str = "owner") -> dict:
        """Restore DB from a backup. Owner-only (called via API with owner auth).
        Restarts are required to reload state; we copy the file back."""
        row = db.query_one("SELECT * FROM backups WHERE id=?", (backup_id,))
        if not row:
            raise ValueError("backup not found")
        src = Path(row["path"]) / "omniai.db"
        if not src.exists():
            raise ValueError("backup file missing")
        shutil.copy2(src, DB_PATH)
        audit.log(actor, "backup_restored", {"id": backup_id})
        return {"restored": backup_id, "note": "restart the server to load restored state"}

    # ---- state bundles ----------------------------------------------------
    def _counts(self) -> dict[str, int]:
        return {
            "models": db.query_one("SELECT COUNT(*) c FROM models")["c"],
            "memories": db.query_one("SELECT COUNT(*) c FROM memory")["c"],
            "datasets": db.query_one("SELECT COUNT(*) c FROM datasets")["c"],
            "cycles": db.query_one("SELECT COUNT(*) c FROM training_cycles")["c"],
            "approvals": db.query_one("SELECT COUNT(*) c FROM approvals")["c"],
            "backups": db.query_one("SELECT COUNT(*) c FROM backups")["c"],
        }

    def _checkpoint_inventory(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if not CHECKPOINTS_DIR.exists():
            return items
        for p in sorted(CHECKPOINTS_DIR.rglob("*")):
            if p.is_file():
                items.append(
                    {
                        "path": str(p.relative_to(CHECKPOINTS_DIR)),
                        "size": p.stat().st_size,
                    }
                )
        return items

    def _build_state_manifest(self, bundle_id: str, note: str) -> dict[str, Any]:
        from ..models_core import registry
        from ..memory.store import memory_store

        models = registry.list_models()
        current = registry.get_current_model()
        schema = db.schema_info()
        manifest = {
            "bundle_id": bundle_id,
            "note": note,
            "created_at": db.now(),
            "schema": schema,
            "audit_chain": audit.verify_chain(),
            "controls": db.get_controls(),
            "counts": self._counts(),
            "current_model": {
                "id": current["id"] if current else None,
                "version": current["version"] if current else None,
                "adapter": (current.get("adapter_info") or {}).get("key") if current else None,
            },
            "models": models,
            "memory_snapshot": memory_store.list_memories(limit=1000),
            "checkpoint_inventory": self._checkpoint_inventory(),
        }
        return manifest

    def export_state_bundle(self, note: str = "") -> dict:
        bundle_id = db.new_id()
        dest = BACKUPS_DIR / f"state_bundle_{int(time.time())}_{bundle_id}"
        dest.mkdir(parents=True, exist_ok=True)

        shutil.copy2(DB_PATH, dest / "omniai.db")
        ckpt_dest = dest / "checkpoints"
        shutil.copytree(CHECKPOINTS_DIR, ckpt_dest, dirs_exist_ok=True)
        manifest = self._build_state_manifest(bundle_id, note)
        manifest_path = dest / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

        db.execute(
            "INSERT INTO state_bundles(id, path, note, manifest_path, status, created_at) VALUES(?,?,?,?,?,?)",
            (bundle_id, str(dest), note, str(manifest_path), "exported", db.now()),
        )
        audit.log(
            "owner",
            "state_bundle_exported",
            {"id": bundle_id, "note": note, "models": manifest["counts"]["models"], "memories": manifest["counts"]["memories"]},
        )
        return {
            "id": bundle_id,
            "path": str(dest),
            "manifest_path": str(manifest_path),
            "note": note,
            "schema_version": manifest["schema"]["current_version"],
        }

    def list_state_bundles(self) -> list[dict]:
        return db.query("SELECT * FROM state_bundles ORDER BY created_at DESC")

    def latest_state_bundle(self) -> dict | None:
        return db.query_one("SELECT * FROM state_bundles ORDER BY created_at DESC LIMIT 1")

    def latest_emergency_bundle(self) -> dict | None:
        bundle_id = db.get_controls().get("last_emergency_bundle_id")
        if not bundle_id:
            return None
        return db.query_one("SELECT * FROM state_bundles WHERE id=?", (bundle_id,))

    def _get_bundle_row(self, bundle_id: str) -> dict:
        row = db.query_one("SELECT * FROM state_bundles WHERE id=?", (bundle_id,))
        if not row:
            raise ValueError("state bundle not found")
        return row

    def verify_state_bundle(self, bundle_id: str) -> dict:
        row = self._get_bundle_row(bundle_id)
        root = Path(row["path"])
        manifest_path = Path(row["manifest_path"])
        db_path = root / "omniai.db"
        checkpoints_path = root / "checkpoints"
        problems: list[str] = []
        manifest = None
        if not root.exists():
            problems.append("bundle directory missing")
        if not manifest_path.exists():
            problems.append("manifest missing")
        if not db_path.exists():
            problems.append("database snapshot missing")
        if not checkpoints_path.exists():
            problems.append("checkpoints directory missing")
        if not problems:
            try:
                manifest = json.loads(manifest_path.read_text())
            except Exception as e:
                problems.append(f"manifest unreadable: {e}")
        schema = (manifest or {}).get("schema") or {}
        chain = (manifest or {}).get("audit_chain") or {}
        ok = not problems and schema.get("current_version") == schema.get("target_version") and chain.get("ok") is True
        result = {
            "id": bundle_id,
            "ok": ok,
            "problems": problems,
            "schema": schema,
            "audit_chain": chain,
            "counts": (manifest or {}).get("counts") or {},
            "path": str(root),
        }
        audit.log("owner", "state_bundle_verified", {"id": bundle_id, "ok": ok, "problems": problems})
        return result

    def import_state_bundle(self, bundle_id: str, apply: bool = False, actor: str = "owner") -> dict:
        verification = self.verify_state_bundle(bundle_id)
        if not verification["ok"]:
            raise ValueError("state bundle failed verification")
        row = self._get_bundle_row(bundle_id)
        if not apply:
            return {
                "importable": True,
                "applied": False,
                "id": bundle_id,
                "note": "verification passed; re-run with apply=true to restore DB and checkpoints",
                "schema": verification["schema"],
                "counts": verification["counts"],
            }
        root = Path(row["path"])
        shutil.copy2(root / "omniai.db", DB_PATH)
        shutil.copytree(root / "checkpoints", CHECKPOINTS_DIR, dirs_exist_ok=True)
        db.execute("UPDATE state_bundles SET status=? WHERE id=?", ("imported", bundle_id))
        audit.log(actor, "state_bundle_imported", {"id": bundle_id, "applied": True})
        return {
            "importable": True,
            "applied": True,
            "id": bundle_id,
            "note": "bundle restored; restart the server to load imported state safely",
        }


backup_manager = BackupManager()
