from __future__ import annotations

import queue
import threading
import time
import uuid

from ..database import db
from ..security import audit


class GPUWorker:
    def __init__(self, max_concurrent=1):
        self.max_concurrent = max_concurrent
        self._init_runtime()

    def _init_runtime(self):
        self.q = queue.Queue()
        self.jobs = {}
        self.stop = threading.Event()
        self.threads = []

    def detect(self):
        try:
            import torch
            return {
                "available": torch.cuda.is_available(),
                "count": torch.cuda.device_count(),
                "vram_mb": int(torch.cuda.get_device_properties(0).total_memory / 1048576)
                if torch.cuda.is_available() else 0,
            }
        except Exception as e:
            return {"available": False, "count": 0, "vram_mb": 0, "error": str(e)}

    def start(self):
        alive = [t for t in self.threads if t.is_alive()]
        self.threads = alive
        if self.threads:
            return
        self.stop.clear()
        for _ in range(self.max_concurrent):
            t = threading.Thread(target=self._loop, daemon=True)
            t.start()
            self.threads.append(t)
        audit.log("gpu_worker", "started", {"threads": len(self.threads)})

    def submit(self, kind, payload):
        if db.get_controls().get("kill_switch"):
            raise PermissionError("kill switch active")
        jid = uuid.uuid4().hex[:16]
        self.jobs[jid] = {"id": jid, "kind": kind, "status": "queued", "created_at": time.time()}
        self.q.put((jid, kind, payload))
        return self.jobs[jid]

    def cancel(self, jid):
        if jid in self.jobs:
            self.jobs[jid]["cancelled"] = True
            self.jobs[jid]["status"] = self.jobs[jid].get("status") or "cancelled"
            return True
        return False

    def cancel_all(self, reason: str = "owner stop") -> dict:
        changed = 0
        now = time.time()
        for job in self.jobs.values():
            if job.get("status") in ("queued", "running"):
                job["cancelled"] = True
                job["status"] = "cancelled"
                job["error"] = reason
                job["finished_at"] = now
                changed += 1
        audit.log("gpu_worker", "cancel_all", {"count": changed, "reason": reason})
        return {"cancelled": changed}

    def _loop(self):
        while not self.stop.is_set():
            try:
                jid, kind, payload = self.q.get(timeout=.2)
            except queue.Empty:
                continue
            job = self.jobs[jid]
            if job.get("cancelled"):
                job["status"] = "cancelled"
                job["finished_at"] = time.time()
                self.q.task_done()
                continue
            job["status"] = "running"
            try:
                if job.get("cancelled") or db.get_controls().get("kill_switch"):
                    raise RuntimeError("cancelled")
                if kind == "inference":
                    from ..llm.engine import llm_engine, GenerationConfig
                    if not llm_engine.loaded:
                        raise RuntimeError("no model loaded")
                    job["result"] = llm_engine.generate(payload["messages"], GenerationConfig(**payload.get("config", {})))
                elif kind == "training":
                    from ..training.trainer import trainer
                    job["result"] = trainer.train_candidate(**payload)
                else:
                    raise ValueError("unknown job kind")
                job["status"] = "completed"
            except Exception as e:
                if job.get("cancelled"):
                    job["status"] = "cancelled"
                else:
                    job["status"] = "failed"
                job["error"] = str(e)
            job["finished_at"] = time.time()
            audit.log("gpu_worker", "job_finished", job)
            self.q.task_done()

    def shutdown(self, reason: str = "owner stop"):
        self.cancel_all(reason)
        self.stop.set()
        for t in list(self.threads):
            t.join(timeout=1)
        self.threads = []
        while True:
            try:
                self.q.get_nowait()
                self.q.task_done()
            except queue.Empty:
                break
        self.stop.clear()
        audit.log("gpu_worker", "shutdown", {"reason": reason})
        return {"stopped": True, "reason": reason}


gpu_worker = GPUWorker()
