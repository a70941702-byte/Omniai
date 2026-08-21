"""Model Registry - versioned record of every model with rollback support.

States: candidate -> (adopted) current; the best 'current' ever seen is also
flagged best_historical. Old models are archived, never deleted, so rollback
is always possible. Every transition is audit-logged.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ..config import CHECKPOINTS_DIR
from ..database import db
from ..security import audit
from .adapters import adapters_catalog, describe_model_adapter
from .neural_core import NeuralCore

_JSON_FIELDS = ("intent_labels", "config", "metrics", "resource_usage", "training_config")


def _decode_model_row(row: Optional[dict]) -> Optional[dict]:
    if not row:
        return row
    out = dict(row)
    for key in _JSON_FIELDS:
        if out.get(key) and isinstance(out[key], str):
            try:
                out[key] = json.loads(out[key])
            except Exception:
                pass
    out["adapter_info"] = describe_model_adapter(out)
    return out


def _overall_score(row: Optional[dict]) -> float:
    if not row:
        return 0.0
    row = _decode_model_row(row)
    metrics = row.get("metrics") or {}
    if isinstance(metrics, dict):
        if isinstance(metrics.get("overall"), (int, float)):
            return float(metrics["overall"])
    score = row.get("evaluation_score")
    return float(score or 0.0)


def register_model(
    intent_labels: list[str],
    config: dict,
    parent_id: Optional[str],
    checkpoint_path: Optional[str],
    metrics: Optional[dict] = None,
    status: str = "candidate",
    model_type: str = "neuralcore",
    base_model: str | None = None,
    adapter: str | None = None,
    quantization: str | None = None,
    training_dataset: str | None = None,
) -> str:
    model_id = db.new_id()
    version = 1
    if parent_id:
        parent = db.query_one("SELECT version FROM models WHERE id=?", (parent_id,))
        version = (parent["version"] + 1) if parent else 1
    else:
        row = db.query_one("SELECT MAX(version) AS v FROM models")
        version = (row["v"] or 0) + 1
    now = db.now()
    db.execute(
        "INSERT INTO models(id, version, parent_id, intent_labels, config, status, metrics, resource_usage, checkpoint_path, created_at, model_type, base_model, adapter, quantization, training_dataset, training_config, evaluation_score) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            model_id,
            version,
            parent_id,
            json.dumps(intent_labels, ensure_ascii=False),
            json.dumps(config),
            status,
            json.dumps(metrics or {}),
            json.dumps({}),
            checkpoint_path,
            now,
            model_type,
            base_model,
            adapter,
            quantization,
            training_dataset,
            json.dumps(config),
            (metrics or {}).get("overall"),
        ),
    )
    db.execute(
        "INSERT INTO model_artifacts(id, model_id, base_model, adapter, quantization, dataset_version, training_config, evaluation, parent_model, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            db.new_id(),
            model_id,
            base_model,
            adapter,
            quantization,
            training_dataset,
            json.dumps(config),
            json.dumps(metrics or {}),
            parent_id,
            now,
        ),
    )
    audit.log(
        "system",
        "model_registered",
        {"model_id": model_id, "version": version, "parent": parent_id, "status": status, "model_type": model_type},
    )
    return model_id


def save_checkpoint(model: NeuralCore, model_id: str) -> str:
    path = CHECKPOINTS_DIR / f"{model_id}.pt"
    model.save(path)
    db.execute("UPDATE models SET checkpoint_path=? WHERE id=?", (str(path), model_id))
    return str(path)


def load_model(model_id: str) -> NeuralCore:
    row = db.query_one("SELECT checkpoint_path FROM models WHERE id=?", (model_id,))
    if not row or not row["checkpoint_path"]:
        raise ValueError(f"model {model_id} has no checkpoint")
    return NeuralCore.load(Path(row["checkpoint_path"]))


def get_model(model_id: str) -> Optional[dict]:
    return _decode_model_row(db.query_one("SELECT * FROM models WHERE id=?", (model_id,)))


def list_models(status: Optional[str] = None) -> list[dict]:
    if status:
        rows = db.query("SELECT * FROM models WHERE status=? ORDER BY created_at DESC", (status,))
    else:
        rows = db.query("SELECT * FROM models ORDER BY created_at DESC")
    return [_decode_model_row(r) for r in rows]


def get_current_model() -> Optional[dict]:
    return _decode_model_row(db.query_one("SELECT * FROM models WHERE status='current' ORDER BY created_at DESC LIMIT 1"))


def get_best_historical() -> Optional[dict]:
    return _decode_model_row(db.query_one("SELECT * FROM models WHERE status='best_historical' ORDER BY created_at DESC LIMIT 1"))


def get_model_details(model_id: str) -> Optional[dict]:
    row = get_model(model_id)
    if not row:
        return None
    artifacts = db.query(
        "SELECT * FROM model_artifacts WHERE model_id=? ORDER BY created_at DESC", (model_id,)
    )
    for art in artifacts:
        for key in ("training_config", "evaluation"):
            if art.get(key) and isinstance(art[key], str):
                try:
                    art[key] = json.loads(art[key])
                except Exception:
                    pass
    row["lineage"] = lineage(model_id)
    row["artifacts"] = artifacts
    row["derived_from_current"] = bool(row.get("parent_id") == (get_current_model() or {}).get("id"))
    return row


def list_model_adapters() -> list[dict]:
    return adapters_catalog()


def _set_status(model_id: str, status: str) -> None:
    approved_at = db.now() if status in ("current", "best_historical") else None
    if approved_at is not None:
        db.execute("UPDATE models SET status=?, approved_at=? WHERE id=?", (status, approved_at, model_id))
    else:
        db.execute("UPDATE models SET status=? WHERE id=?", (status, model_id))
    audit.log("system", "model_status_changed", {"model_id": model_id, "status": status})


def mark_rejected(model_id: str) -> None:
    _set_status(model_id, "rejected")


def adopt_model(candidate_id: str, actor: str = "owner") -> dict:
    """Promote candidate to current. Previous current -> archived; the better
    of (previous best_historical, previous current) stays best_historical
    based on overall benchmark score. Fully reversible via rollback()."""
    candidate = get_model(candidate_id)
    if not candidate:
        raise ValueError("candidate not found")
    prev_current = get_current_model()
    prev_best = get_best_historical()

    if prev_current:
        _set_status(prev_current["id"], "archived")
    candidates = [m for m in (prev_best, prev_current) if m]
    if candidates:
        best = max(candidates, key=_overall_score)
        if prev_best:
            _set_status(prev_best["id"], "archived")
        _set_status(best["id"], "best_historical")
    _set_status(candidate_id, "current")
    db.execute("UPDATE model_artifacts SET approved_at=? WHERE model_id=?", (db.now(), candidate_id))
    audit.log(actor, "model_adopted", {"model_id": candidate_id, "previous_current": prev_current["id"] if prev_current else None})
    return get_model(candidate_id)


def rollback(to_model_id: Optional[str] = None, actor: str = "owner") -> dict:
    """Roll back to a specific model, or to best_historical by default."""
    target = get_model(to_model_id) if to_model_id else get_best_historical()
    if not target:
        raise ValueError("no rollback target available")
    current = get_current_model()
    if current:
        _set_status(current["id"], "archived")
    _set_status(target["id"], "current")
    db.execute("UPDATE model_artifacts SET approved_at=? WHERE model_id=?", (db.now(), target["id"]))
    audit.log(actor, "rollback", {"to": target["id"], "from": current["id"] if current else None})
    return get_model(target["id"])


def lineage(model_id: str) -> list[dict]:
    """Walk the parent chain to produce the model's ancestry."""
    chain = []
    cur = get_model(model_id)
    while cur:
        chain.append(
            {
                "id": cur["id"],
                "version": cur["version"],
                "status": cur["status"],
                "model_type": cur.get("model_type"),
                "adapter": cur.get("adapter_info", {}).get("key"),
            }
        )
        cur = get_model(cur["parent_id"]) if cur.get("parent_id") else None
    return chain
