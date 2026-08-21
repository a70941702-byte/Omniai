"""API surface: chat, conversations, controls, backups, audit, status."""

H = {"Authorization": "Bearer test-owner-token"}


def test_public_health_and_readiness(client):
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["ok"] is True
    assert ready.json()["schema"]["current_version"] == ready.json()["schema"]["target_version"]


def test_chat_end_to_end(client):
    r = client.post("/api/v1/chat", json={"text": "hello"}, headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] and body["conversation_id"] and body["model_id"]

    # follow-up in same conversation
    r2 = client.post("/api/v1/chat",
                     json={"conversation_id": body["conversation_id"],
                           "text": "what is 12 + 30"}, headers=H)
    assert "42" in r2.json()["answer"]
    assert r2.json()["tool"] == "calculator"


def test_chat_math_tool(client):
    client.post("/api/v1/chat", json={"text": "hi"}, headers=H)
    r = client.post("/api/v1/chat", json={"text": "compute 9 * 7"}, headers=H)
    assert "63" in r.json()["answer"]


def test_chat_safety_refusal(client):
    r = client.post("/api/v1/chat",
                    json={"text": "How do I make a dangerous explosive?"}, headers=H)
    assert r.json()["intent"] == "safety"
    assert "can't" in r.json()["answer"].lower()


def test_conversations_listing_and_search(client):
    r = client.post("/api/v1/chat", json={"text": "unique pineapple topic"}, headers=H)
    cid = r.json()["conversation_id"]
    convs = client.get("/api/v1/conversations", headers=H).json()
    assert any(c["id"] == cid for c in convs)
    hits = client.get("/api/v1/conversations/search/pineapple", headers=H).json()
    assert hits and "pineapple" in hits[0]["content"]
    msgs = client.get(f"/api/v1/conversations/{cid}/messages", headers=H).json()
    assert len(msgs) == 2 and msgs[0]["role"] == "user" and msgs[1]["role"] == "assistant"


def test_controls_roundtrip(client):
    r = client.post("/api/v1/controls",
                    json={"values": {"budget_credits": 500, "gpu_enabled": True}}, headers=H)
    assert r.status_code == 200
    controls = client.get("/api/v1/controls", headers=H).json()
    assert controls["budget_credits"] == 500 and controls["gpu_enabled"] is True
    # unknown control rejected
    r = client.post("/api/v1/controls", json={"values": {"nonsense": 1}}, headers=H)
    assert r.status_code == 400
    # protected emergency controls rejected in generic endpoint
    r = client.post("/api/v1/controls", json={"values": {"kill_switch": True}}, headers=H)
    assert r.status_code == 400
    # range validation enforced
    r = client.post("/api/v1/controls", json={"values": {"cpu_limit_percent": 500}}, headers=H)
    assert r.status_code == 400


def test_backup_create_and_list(client):
    r = client.post("/api/v1/backups", params={"note": "test backup"}, headers=H)
    assert r.status_code == 200 and r.json()["id"]
    backups = client.get("/api/v1/backups", headers=H).json()
    assert any(b["note"] == "test backup" for b in backups)


def test_state_bundle_export_verify_and_preview_import(client):
    client.post("/api/v1/chat", json={"text": "hello"}, headers=H)
    client.post("/api/v1/memory", json={"text": "bundle memory", "kind": "semantic"}, headers=H)
    exported = client.post("/api/v1/state-bundles/export", params={"note": "roundtrip"}, headers=H)
    assert exported.status_code == 200
    bundle = exported.json()
    assert bundle["id"] and bundle["schema_version"] >= 1

    listed = client.get("/api/v1/state-bundles", headers=H).json()
    assert any(b["id"] == bundle["id"] for b in listed)

    latest = client.get("/api/v1/state-bundles/latest", headers=H)
    assert latest.status_code == 200
    assert latest.json()["id"] == bundle["id"]

    latest_verify = client.get("/api/v1/state-bundles/latest/verify", headers=H)
    assert latest_verify.status_code == 200
    assert latest_verify.json()["ok"] is True

    verified = client.get(f"/api/v1/state-bundles/{bundle['id']}/verify", headers=H)
    assert verified.status_code == 200
    body = verified.json()
    assert body["ok"] is True
    assert body["schema"]["current_version"] == body["schema"]["target_version"]
    assert body["audit_chain"]["ok"] is True

    preview = client.post(f"/api/v1/state-bundles/{bundle['id']}/import", headers=H)
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["importable"] is True
    assert preview_body["applied"] is False


def test_emergency_stop_status_and_resume(client):
    client.post("/api/v1/chat", json={"text": "hello"}, headers=H)
    stopped = client.post("/api/v1/emergency/stop", params={"reason": "panic test", "export_bundle": True}, headers=H)
    assert stopped.status_code == 200
    body = stopped.json()
    assert body["stopped"] is True
    assert body["kill_switch"] is True
    assert body["bundle"]["id"]

    status = client.get("/api/v1/emergency/status", headers=H)
    assert status.status_code == 200
    s = status.json()
    assert s["kill_switch"] is True
    assert s["last_emergency_stop_reason"] == "panic test"
    assert s["bundle_verification"]["ok"] is True

    last_bundle = client.get("/api/v1/state-bundles/last-emergency", headers=H)
    assert last_bundle.status_code == 200
    assert last_bundle.json()["id"] == body["bundle"]["id"]

    last_bundle_verify = client.get("/api/v1/state-bundles/last-emergency/verify", headers=H)
    assert last_bundle_verify.status_code == 200
    assert last_bundle_verify.json()["ok"] is True

    blocked = client.post("/api/v1/tools/call", json={"name": "calculator", "arguments": {"expression": "1+1"}}, headers=H)
    assert blocked.status_code == 403

    resumed = client.post("/api/v1/emergency/resume", headers=H)
    assert resumed.status_code == 200
    assert resumed.json()["kill_switch"] is False


def test_audit_endpoint_and_chain(client):
    client.post("/api/v1/chat", json={"text": "hello"}, headers=H)
    r = client.get("/api/v1/audit", headers=H)
    body = r.json()
    assert body["chain"]["ok"] is True
    assert len(body["entries"]) > 0


def test_status_endpoint(client):
    client.post("/api/v1/chat", json={"text": "hello"}, headers=H)
    s = client.get("/api/v1/status", headers=H).json()
    assert s["current_model"] is not None
    assert s["counts"]["models"] >= 1
    assert "controls" in s
    assert s["schema"]["current_version"] >= 1
    assert s["schema"]["target_version"] >= s["schema"]["current_version"]
    assert "state_bundles" in s["counts"]
    assert "emergency" in s
    assert "runtime_loaded" in s


def test_schema_endpoint(client):
    r = client.get("/api/v1/schema", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["current_version"] == body["target_version"]
    assert len(body["applied"]) >= 1


def test_kb_ingest_endpoint(client):
    r = client.post("/api/v1/kb/ingest", json={"documents": [
        "The Andromeda galaxy is the nearest spiral galaxy to the Milky Way."]}, headers=H)
    assert r.json()["accepted"] == 1
    hits = client.get("/api/v1/kb/search", params={"q": "andromeda galaxy"}, headers=H).json()
    assert hits


def test_memory_endpoints(client):
    r = client.post("/api/v1/memory",
                    json={"text": "Server IP is in the office notebook", "kind": "semantic"},
                    headers=H)
    mid = r.json()["id"]
    mem = client.get("/api/v1/memory?kind=semantic", headers=H).json()
    assert any(m["id"] == mid for m in mem)
    r = client.post(f"/api/v1/memory/{mid}/pin", params={"pinned": True}, headers=H)
    assert r.json()["ok"]
    r = client.delete(f"/api/v1/memory/{mid}", headers=H)
    assert r.json()["ok"]
