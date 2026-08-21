"""REST API (v1). The Android app and the Owner Dashboard talk to this.

Auth model:
- /auth/login exchanges the owner token for a session (same token; Android
  stores it).
- Owner-gated endpoints (controls, approvals, rollback, backups, sandbox
  policy) require `Authorization: Bearer <token>`.
- Chat/read endpoints work with the same token (single-user system).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import StreamingResponse, PlainTextResponse
from pydantic import BaseModel

from ..agents.self_improvement import self_improvement
from ..approval.system import approval_system
from ..backup.manager import backup_manager
from ..database import db
from ..evaluation.engine import evaluation_engine
from ..knowledge.base import knowledge_base
from ..memory.store import memory_store
from ..models_core import registry
from ..orchestrator.core import orchestrator
from ..sandbox.runner import sandbox
from ..security import audit
from ..security.auth import require_owner, verify_owner_token
from ..security.sessions import create as create_session, revoke as revoke_session, revoke_device as revoke_device_sessions, get as get_session
from ..security.policy import allowed, kill_switch_active, validate_control_changes
from ..security.rate_limit import login_rate_limiter
from ..tools.gateway import gateway
from ..llm.engine import llm_engine, GenerationConfig
from ..workers.gpu_worker import gpu_worker
from ..observability.metrics import snapshot

router = APIRouter()


# ------------------------- auth ---------------------------------------------
class LoginIn(BaseModel):
    token: str
    device_id: Optional[str] = None

@router.post("/auth/login")
def login(body: LoginIn, request: Request):
    ip = request.client.host if request.client else "unknown"
    rl_key = f"login:{ip}"
    if not login_rate_limiter.allowed(rl_key):
        audit.log("system", "login_rate_limited", {"ip": ip})
        raise HTTPException(429, "too many login attempts")
    if not verify_owner_token(body.token):
        login_rate_limiter.record(rl_key)
        audit.log("system", "login_failed", {"ip": ip, "device_id": body.device_id})
        raise HTTPException(403, "invalid token")
    login_rate_limiter.clear(rl_key)
    session = create_session(
        body.device_id,
        user_agent=request.headers.get("user-agent"),
        ip=ip,
    )
    audit.log("owner", "login", {"session_created": True, "device_id": body.device_id})
    return {"ok": True, "token": session, "expires_in": db.get_controls().get("session_ttl_s", 86400)}

@router.get("/auth/devices")
def devices(_=Depends(require_owner)):
    rows = db.query("SELECT id,device_id,created_at,expires_at,revoked,last_seen_at,user_agent,last_ip FROM sessions ORDER BY created_at DESC")
    now = db.now()
    for r in rows:
        r["active_now"] = bool(not r.get("revoked") and float(r.get("expires_at") or 0) > now)
    return rows

@router.post("/auth/devices/{device_id}/revoke")
def revoke_device(device_id: str, _=Depends(require_owner)):
    revoke_device_sessions(device_id)
    audit.log("owner","device_revoked",{"device_id":device_id})
    return {"ok":True}

@router.post("/auth/logout")
def logout(authorization: str = Header(default=""), _=Depends(require_owner)):
    token = authorization.replace("Bearer ", "", 1).strip() if authorization.startswith("Bearer ") else ""
    if token:
        revoke_session(token)
    return {"ok": True}

@router.get("/auth/me")
def auth_me(authorization: str = Header(default=""), _=Depends(require_owner)):
    token = authorization.replace("Bearer ", "", 1).strip() if authorization.startswith("Bearer ") else ""
    session = get_session(token)
    return {
        "owner_token": verify_owner_token(token),
        "session": session,
        "controls": {
            "session_ttl_s": db.get_controls().get("session_ttl_s", 86400),
            "session_idle_timeout_s": db.get_controls().get("session_idle_timeout_s", 43200),
            "max_sessions_per_device": db.get_controls().get("max_sessions_per_device", 3),
        },
    }


# ------------------------- chat ----------------------------------------------
class ChatIn(BaseModel):
    conversation_id: Optional[str] = None
    text: str
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 512

@router.post("/chat")
def chat(body: ChatIn, _=Depends(require_owner)):
    cid = body.conversation_id
    if not cid:
        cid = db.new_id()
        db.execute("INSERT INTO conversations(id, title, created_at, updated_at)"
                   " VALUES(?,?,?,?)", (cid, body.text[:60], db.now(), db.now()))
    elif not db.query_one("SELECT id FROM conversations WHERE id=?", (cid,)):
        raise HTTPException(404, "conversation not found")
    return {"conversation_id": cid, **orchestrator.chat(cid, body.text, body.system_prompt)}

@router.post("/chat/stream")
def chat_stream(body: ChatIn, _=Depends(require_owner)):
    if not llm_engine.loaded:
        raise HTTPException(409, "no real LLM loaded; use /models/llm/load first")
    cid=body.conversation_id
    if not cid:
        cid=db.new_id(); db.execute("INSERT INTO conversations(id,title,created_at,updated_at) VALUES(?,?,?,?)",(cid,body.text[:60],db.now(),db.now()))
    rows=db.query("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT 30",(cid,))[::-1]
    messages=rows+[{'role':'user','content':body.text}]
    if body.system_prompt: messages=[{'role':'system','content':body.system_prompt}]+messages
    cfg=GenerationConfig(body.temperature,body.top_p,body.max_tokens)
    def gen():
        chunks=[]
        for token in llm_engine.stream(messages,cfg): chunks.append(token); yield token
        answer=''.join(chunks)
        db.execute("INSERT INTO messages(id,conversation_id,role,content,model_id,created_at) VALUES(?,?,?,?,?,?)",(db.new_id(),cid,'user',body.text,None,db.now()))
        db.execute("INSERT INTO messages(id,conversation_id,role,content,model_id,created_at) VALUES(?,?,?,?,?,?)",(db.new_id(),cid,'assistant',answer,'llm',db.now()))
    return StreamingResponse(gen(),media_type='text/plain',headers={'X-Conversation-ID':cid})

@router.get("/conversations")
def list_conversations(_=Depends(require_owner)):
    return db.query("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT 100")

@router.get("/conversations/{cid}/messages")
def get_messages(cid: str, _=Depends(require_owner)):
    return db.query("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at", (cid,))

@router.get("/conversations/search/{q}")
def search_messages(q: str, _=Depends(require_owner)):
    return db.query("SELECT * FROM messages WHERE content LIKE ? ORDER BY created_at DESC LIMIT 50",
                    (f"%{q}%",))

@router.delete("/conversations/{cid}")
def delete_conversation(cid: str, _=Depends(require_owner)):
    db.execute("DELETE FROM conversations WHERE id=?", (cid,))
    audit.log("owner", "conversation_deleted", {"id": cid})
    return {"ok": True}


# ------------------------- memory ---------------------------------------------
class MemoryIn(BaseModel):
    text: str
    kind: str = "semantic"
    importance: float = 0.6
    pinned: bool = False

@router.post("/memory")
def add_memory(body: MemoryIn, _=Depends(require_owner)):
    if body.kind not in ("episodic", "semantic", "short_term"):
        raise HTTPException(400, "invalid kind")
    mid = memory_store.remember(body.text, body.kind, body.importance, body.pinned)
    return {"id": mid}

@router.get("/memory")
def list_memory(kind: Optional[str] = None, _=Depends(require_owner)):
    return memory_store.list_memories(kind)

@router.post("/memory/{mid}/pin")
def pin_memory(mid: str, pinned: bool = True, _=Depends(require_owner)):
    memory_store.pin(mid, pinned)
    return {"ok": True}

@router.delete("/memory/{mid}")
def delete_memory(mid: str, _=Depends(require_owner)):
    memory_store.forget(mid)
    return {"ok": True}


# ------------------------- knowledge base --------------------------------------
class KBIn(BaseModel):
    documents: list[str]

@router.post("/kb/ingest")
def kb_ingest(body: KBIn, _=Depends(require_owner)):
    return knowledge_base.ingest(body.documents, source="owner")

@router.get("/kb/search")
def kb_search(q: str, _=Depends(require_owner)):
    return knowledge_base.retrieve(q)


# ------------------------- models -----------------------------------------------
@router.get("/models")
def list_models(status: Optional[str] = None, _=Depends(require_owner)):
    return registry.list_models(status=status)

@router.get("/models/adapters")
def model_adapters(_=Depends(require_owner)):
    return registry.list_model_adapters()

@router.get("/models/current")
def current_model(_=Depends(require_owner)):
    return registry.get_current_model()

@router.get("/models/{mid}")
def get_model(mid: str, _=Depends(require_owner)):
    m = registry.get_model_details(mid)
    if not m:
        raise HTTPException(404, "model not found")
    return m

@router.post("/models/llm/load")
def load_llm(model_ref: str, quantization: Optional[str] = None, _=Depends(require_owner)):
    if not db.get_controls().get("server_enabled", False) and not db.get_controls().get("gpu_enabled", False) and model_ref.endswith('.gguf'):
        # GGUF is still allowed on CPU; this branch intentionally does not block it.
        pass
    try: return llm_engine.load(model_ref, quantization)
    except RuntimeError as e: raise HTTPException(400, str(e))

@router.post("/models/llm/unload")
def unload_llm(_=Depends(require_owner)):
    llm_engine.unload(); return {"loaded": False}

@router.get("/worker/status")
def worker_status(_=Depends(require_owner)):
    return {"gpu":gpu_worker.detect(),"jobs":list(gpu_worker.jobs.values())[-100:]}

@router.post("/worker/start")
def worker_start(_=Depends(require_owner)):
    if not db.get_controls().get("server_enabled",False): raise HTTPException(403,"server disabled")
    gpu_worker.start(); return {"started":True,"gpu":gpu_worker.detect()}

@router.get("/models/runtime")
def runtime_model(_=Depends(require_owner)):
    return {"loaded":llm_engine.loaded,"device":llm_engine.device,"backend":llm_engine._backend}

@router.get("/models/{mid}/lineage")
def model_lineage(mid: str, _=Depends(require_owner)):
    return registry.lineage(mid)

@router.post("/models/rollback")
def rollback(to_model_id: Optional[str] = None, _=Depends(require_owner)):
    try:
        return registry.rollback(to_model_id, actor="owner")
    except ValueError as e:
        raise HTTPException(400, str(e))


# ------------------------- training ----------------------------------------------
class TrainCycleIn(BaseModel):
    extra_samples: list[dict] = []

@router.post("/training/cycle")
def run_cycle(body: TrainCycleIn, _=Depends(require_owner)):
    return orchestrator.run_cycle(extra_samples=body.extra_samples)

@router.post("/training/start")
def start_training(interval_s: int = 30, _=Depends(require_owner)):
    if not db.get_controls().get("training_enabled", True): raise HTTPException(403,"training disabled")
    started = orchestrator.start_background(interval_s)
    return {"started": started}

@router.post("/training/stop")
def stop_training(_=Depends(require_owner)):
    orchestrator.stop_background()
    return {"stopped": True}

@router.get("/training/cycles")
def list_cycles(_=Depends(require_owner)):
    rows = db.query("SELECT * FROM training_cycles ORDER BY cycle_no DESC LIMIT 50")
    for r in rows:
        if r.get("report"):
            import json
            r["report"] = json.loads(r["report"])
    return rows


# ------------------------- evaluation ---------------------------------------------
@router.get("/evaluation/runs")
def eval_runs(model_id: Optional[str] = None, _=Depends(require_owner)):
    if model_id:
        return db.query("SELECT * FROM eval_runs WHERE model_id=? ORDER BY created_at DESC", (model_id,))
    return db.query("SELECT * FROM eval_runs ORDER BY created_at DESC LIMIT 100")


# ------------------------- approvals -------------------------------------------------
class DecisionIn(BaseModel):
    decision: str   # approved | rejected | more_tests
    note: str = ""

@router.get("/approvals")
def list_approvals(status: Optional[str] = None, _=Depends(require_owner)):
    return approval_system.list(status)

@router.post("/approvals/{aid}/decide")
def decide(aid: str, body: DecisionIn, _=Depends(require_owner)):
    try:
        return approval_system.decide(aid, body.decision, body.note, actor="owner")
    except (ValueError, PermissionError) as e:
        raise HTTPException(400, str(e))

@router.post("/approvals/{aid}/execute")
def execute(aid: str, _=Depends(require_owner)):
    try:
        return approval_system.execute_if_approved(aid)
    except (ValueError, PermissionError) as e:
        raise HTTPException(400, str(e))


# ------------------------- owner controls ---------------------------------------------
class ControlsIn(BaseModel):
    values: dict

@router.get("/controls")
def get_controls(_=Depends(require_owner)):
    return db.get_controls()

@router.post("/controls")
def set_controls(body: ControlsIn, _=Depends(require_owner)):
    # Core-rule changes (e.g. disabling training) take effect immediately but
    # are audit-logged; the AI can never reach this endpoint (owner-only dep).
    try:
        validated = validate_control_changes(body.values)
        for k, v in validated.items():
            db.set_control(k, v)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    audit.log("owner", "controls_updated", validated)
    return db.get_controls()


# ------------------------- self-improvement ---------------------------------------------
@router.post("/improve/analyze")
def improve_analyze(_=Depends(require_owner)):
    return {"findings": self_improvement.analyze_source()}

@router.post("/improve/propose")
def improve_propose(_=Depends(require_owner)):
    return {"proposals": self_improvement.propose_fixes()}

@router.get("/improve/proposals")
def improve_list(_=Depends(require_owner)):
    rows = db.query("SELECT * FROM improvement_proposals ORDER BY created_at DESC LIMIT 50")
    return rows


# ------------------------- sandbox --------------------------------------------------------
class SandboxIn(BaseModel):
    code: str
    files: dict[str, str] = {}

@router.post("/sandbox/run")
def sandbox_run(body: SandboxIn, _=Depends(require_owner)):
    if not db.get_controls().get("python_enabled", True): raise HTTPException(403,"python execution disabled")
    return sandbox.run_python(body.code, body.files)


# ------------------------- backups -----------------------------------------------------------
@router.post("/backups")
def create_backup(note: str = "", _=Depends(require_owner)):
    return backup_manager.create(note)

@router.get("/backups")
def list_backups(_=Depends(require_owner)):
    return backup_manager.list()

@router.post("/backups/{bid}/restore")
def restore_backup(bid: str, _=Depends(require_owner)):
    try:
        return backup_manager.restore(bid, actor="owner")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/state-bundles/export")
def export_state_bundle(note: str = "", _=Depends(require_owner)):
    return backup_manager.export_state_bundle(note)

@router.get("/state-bundles")
def list_state_bundles(_=Depends(require_owner)):
    return backup_manager.list_state_bundles()

@router.get("/state-bundles/latest")
def latest_state_bundle(_=Depends(require_owner)):
    row = backup_manager.latest_state_bundle()
    if not row:
        raise HTTPException(404, "no state bundles yet")
    return row

@router.get("/state-bundles/latest/verify")
def verify_latest_state_bundle(_=Depends(require_owner)):
    row = backup_manager.latest_state_bundle()
    if not row:
        raise HTTPException(404, "no state bundles yet")
    return backup_manager.verify_state_bundle(row["id"])

@router.get("/state-bundles/last-emergency")
def last_emergency_bundle(_=Depends(require_owner)):
    row = backup_manager.latest_emergency_bundle()
    if not row:
        raise HTTPException(404, "no emergency bundle recorded")
    return row

@router.get("/state-bundles/last-emergency/verify")
def verify_last_emergency_bundle(_=Depends(require_owner)):
    row = backup_manager.latest_emergency_bundle()
    if not row:
        raise HTTPException(404, "no emergency bundle recorded")
    return backup_manager.verify_state_bundle(row["id"])

@router.post("/state-bundles/{bundle_id}/verify-and-import")
def verify_and_import_state_bundle(bundle_id: str, _=Depends(require_owner)):
    try:
        return backup_manager.import_state_bundle(bundle_id, apply=True, actor="owner")
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.get("/state-bundles/{bundle_id}/verify")
def verify_state_bundle(bundle_id: str, _=Depends(require_owner)):
    try:
        return backup_manager.verify_state_bundle(bundle_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.post("/state-bundles/{bundle_id}/import")
def import_state_bundle(bundle_id: str, apply: bool = False, _=Depends(require_owner)):
    try:
        return backup_manager.import_state_bundle(bundle_id, apply=apply, actor="owner")
    except ValueError as e:
        raise HTTPException(400, str(e))


# ------------------------- tools ---------------------------------------------------------------
class ToolIn(BaseModel):
    name: str
    arguments: dict = {}

@router.get("/tools")
def tools(_=Depends(require_owner)):
    return [{"name": n, "enabled": allowed(meta[1]), "approval": meta[3], "timeout_s": meta[2]} for n, meta in gateway.tools.items()]

@router.post("/tools/call")
def tool_call(body: ToolIn, _=Depends(require_owner)):
    try:
        return {"ok": True, "result": gateway.call(body.name, **body.arguments)}
    except (PermissionError, ValueError) as e:
        raise HTTPException(403, str(e))

@router.post("/kill-switch")
def kill_switch(enabled: bool, _=Depends(require_owner)):
    db.set_control("kill_switch", enabled)
    audit.log("owner", "kill_switch", {"enabled": enabled})
    return {"enabled": enabled}

@router.post("/emergency/stop")
def emergency_stop(reason: str = "owner emergency stop", export_bundle: bool = True, _=Depends(require_owner)):
    db.set_control("kill_switch", True)
    db.set_control("training_enabled", False)
    db.set_control("autonomous_cycles", False)
    db.set_control("last_emergency_stop_at", db.now())
    db.set_control("last_emergency_stop_reason", reason)
    orchestrator_info = orchestrator.emergency_halt(reason)
    worker_info = gpu_worker.shutdown(reason)
    llm_engine.unload()
    bundle = None
    if export_bundle:
        bundle = backup_manager.export_state_bundle(f"emergency-stop: {reason}")
        db.set_control("last_emergency_bundle_id", bundle["id"])
    audit.log("owner", "emergency_stop", {"reason": reason, "bundle_id": bundle["id"] if bundle else None})
    return {
        "stopped": True,
        "kill_switch": True,
        "reason": reason,
        "bundle": bundle,
        "orchestrator": orchestrator_info,
        "worker": worker_info,
        "runtime": {"loaded": llm_engine.loaded, "device": llm_engine.device},
    }

@router.post("/emergency/resume")
def emergency_resume(_=Depends(require_owner)):
    db.set_control("kill_switch", False)
    audit.log("owner", "emergency_resume", {})
    return {
        "resumed": True,
        "kill_switch": False,
        "note": "Kill switch cleared. Training remains disabled until you re-enable it manually.",
    }

@router.get("/emergency/status")
def emergency_status(_=Depends(require_owner)):
    controls = db.get_controls()
    jobs = list(gpu_worker.jobs.values())[-100:]
    latest_bundle = controls.get("last_emergency_bundle_id")
    bundle_verification = None
    if latest_bundle:
        try:
            bundle_verification = backup_manager.verify_state_bundle(latest_bundle)
        except Exception as e:
            bundle_verification = {"id": latest_bundle, "ok": False, "problems": [str(e)]}
    return {
        "kill_switch": bool(controls.get("kill_switch", False)),
        "last_emergency_stop_at": controls.get("last_emergency_stop_at"),
        "last_emergency_stop_reason": controls.get("last_emergency_stop_reason"),
        "last_emergency_bundle_id": latest_bundle,
        "training_thread_alive": bool(orchestrator._thread and orchestrator._thread.is_alive()),
        "runtime_loaded": llm_engine.loaded,
        "jobs": {
            "total": len(jobs),
            "queued": sum(1 for j in jobs if j.get("status") == "queued"),
            "running": sum(1 for j in jobs if j.get("status") == "running"),
            "cancelled": sum(1 for j in jobs if j.get("status") == "cancelled"),
            "failed": sum(1 for j in jobs if j.get("status") == "failed"),
        },
        "bundle_verification": bundle_verification,
    }

@router.get("/metrics")
def metrics(_=Depends(require_owner)):
    data = snapshot()
    data["sessions"] = {
        "total": db.query_one("SELECT COUNT(*) c FROM sessions")["c"],
        "active": db.query_one("SELECT COUNT(*) c FROM sessions WHERE revoked=0 AND expires_at>?", (db.now(),))["c"],
    }
    return data

@router.get("/metrics/prometheus")
def metrics_prometheus(_=Depends(require_owner)):
    data = snapshot()
    total = int(data.get("counters", {}).get("http_requests_total", 0))
    avg = float(data.get("latency_avg_s", 0.0))
    p95 = float(data.get("latency_p95_s", 0.0))
    max_latency = float(data.get("latency_max_s", 0.0))
    active_sessions = db.query_one("SELECT COUNT(*) c FROM sessions WHERE revoked=0 AND expires_at>?", (db.now(),))["c"]
    lines = [
        "# HELP omniai_http_requests_total Total HTTP requests observed",
        "# TYPE omniai_http_requests_total counter",
        f"omniai_http_requests_total {total}",
        "# HELP omniai_http_latency_avg_seconds Average request latency in seconds",
        "# TYPE omniai_http_latency_avg_seconds gauge",
        f"omniai_http_latency_avg_seconds {avg}",
        "# HELP omniai_http_latency_p95_seconds P95 request latency in seconds",
        "# TYPE omniai_http_latency_p95_seconds gauge",
        f"omniai_http_latency_p95_seconds {p95}",
        "# HELP omniai_http_latency_max_seconds Max request latency in seconds",
        "# TYPE omniai_http_latency_max_seconds gauge",
        f"omniai_http_latency_max_seconds {max_latency}",
        "# HELP omniai_active_sessions Active authenticated sessions",
        "# TYPE omniai_active_sessions gauge",
        f"omniai_active_sessions {active_sessions}",
    ]
    for key, value in sorted((data.get("routes") or {}).items()):
        method, path, status = key.split(" ", 2)
        safe_path = path.replace('\\', '\\\\').replace('"', '\\"')
        lines.append(f'omniai_http_route_requests_total{{method="{method}",path="{safe_path}",status="{status}"}} {int(value)}')
    lines.append("")
    payload = "\n".join(lines)
    return PlainTextResponse(payload, media_type="text/plain; version=0.0.4")

@router.get("/schema")
def schema(_=Depends(require_owner)):
    return db.schema_info()

# ------------------------- status / audit -------------------------------------------------------
@router.get("/status")
def status(_=Depends(require_owner)):
    controls = db.get_controls()
    current = registry.get_current_model()
    last_cycle = db.query_one("SELECT * FROM training_cycles ORDER BY cycle_no DESC LIMIT 1")
    counts = {
        "models": db.query_one("SELECT COUNT(*) c FROM models")["c"],
        "memories": db.query_one("SELECT COUNT(*) c FROM memory")["c"],
        "datasets": db.query_one("SELECT COUNT(*) c FROM datasets")["c"],
        "cycles": db.query_one("SELECT COUNT(*) c FROM training_cycles")["c"],
        "pending_approvals": db.query_one("SELECT COUNT(*) c FROM approvals WHERE status='pending'")["c"],
        "backups": db.query_one("SELECT COUNT(*) c FROM backups")["c"],
        "state_bundles": db.query_one("SELECT COUNT(*) c FROM state_bundles")["c"],
    }
    latest_bundle_id = controls.get("last_emergency_bundle_id")
    emergency_bundle = None
    if latest_bundle_id:
        try:
            emergency_bundle = backup_manager.verify_state_bundle(latest_bundle_id)
        except Exception as e:
            emergency_bundle = {"id": latest_bundle_id, "ok": False, "problems": [str(e)]}
    return {
        "app": "OmniAI",
        "training_thread_alive": bool(orchestrator._thread and orchestrator._thread.is_alive()),
        "current_model": current["id"] if current else None,
        "current_model_version": current["version"] if current else None,
        "last_cycle": last_cycle,
        "controls": controls,
        "counts": counts,
        "schema": db.schema_info(),
        "runtime_loaded": llm_engine.loaded,
        "sessions": {
            "total": db.query_one("SELECT COUNT(*) c FROM sessions")["c"],
            "active": db.query_one("SELECT COUNT(*) c FROM sessions WHERE revoked=0 AND expires_at>?", (db.now(),))["c"],
        },
        "emergency": {
            "kill_switch": bool(controls.get("kill_switch", False)),
            "last_reason": controls.get("last_emergency_stop_reason"),
            "last_bundle_id": latest_bundle_id,
            "bundle_verification": emergency_bundle,
        },
    }

@router.get("/audit")
def get_audit(limit: int = 100, _=Depends(require_owner)):
    return {"entries": audit.tail(limit), "chain": audit.verify_chain()}
