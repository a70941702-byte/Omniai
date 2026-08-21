import threading, time


def test_session_login_and_revoke(client):
    r = client.post('/api/v1/auth/login', json={'token': 'test-owner-token', 'device_id': 'pixel-a'})
    assert r.status_code == 200
    token = r.json()['token']
    assert token != 'test-owner-token'
    assert client.get('/api/v1/status', headers={'Authorization': 'Bearer ' + token}).status_code == 200
    me = client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + token})
    assert me.status_code == 200 and me.json()['session']['device_id'] == 'pixel-a'
    client.post('/api/v1/auth/logout', headers={'Authorization': 'Bearer ' + token})
    assert client.get('/api/v1/status', headers={'Authorization': 'Bearer ' + token}).status_code == 403


def test_owner_controls_are_enforced(client):
    H = {'Authorization': 'Bearer test-owner-token'}
    client.post('/api/v1/controls', json={'values': {'python_enabled': False, 'training_enabled': False, 'web_enabled': False}}, headers=H)
    assert client.post('/api/v1/sandbox/run', json={'code': 'print(1)'}, headers=H).status_code == 403
    assert client.post('/api/v1/training/start', headers=H).status_code == 403
    client.post('/api/v1/controls', json={'values': {'python_enabled': True, 'training_enabled': True}}, headers=H)


def test_tool_gateway_never_bypasses_policy():
    from app.tools.gateway import gateway
    from app.database import db
    db.set_control('python_enabled', False)
    try:
        try:
            gateway.call('python', code='print(1)')
        except PermissionError:
            pass
        else:
            assert False
    finally:
        db.set_control('python_enabled', True)


def test_llm_engine_is_separate_from_neural_core():
    from app.llm.engine import llm_engine
    from app.models_core.neural_core import NeuralCore
    assert hasattr(llm_engine, 'load') and hasattr(llm_engine, 'stream')
    assert isinstance(NeuralCore(num_outputs=2), NeuralCore)


def test_session_idle_timeout_and_device_limit(client):
    from app.database import db
    from app.security.sessions import get as get_session

    H = {'Authorization': 'Bearer test-owner-token'}
    client.post('/api/v1/controls', json={'values': {'session_idle_timeout_s': 60, 'max_sessions_per_device': 2}}, headers=H)
    r1 = client.post('/api/v1/auth/login', json={'token': 'test-owner-token', 'device_id': 'device-z'})
    r2 = client.post('/api/v1/auth/login', json={'token': 'test-owner-token', 'device_id': 'device-z'})
    r3 = client.post('/api/v1/auth/login', json={'token': 'test-owner-token', 'device_id': 'device-z'})
    t1, t2, t3 = r1.json()['token'], r2.json()['token'], r3.json()['token']
    assert client.get('/api/v1/status', headers={'Authorization': 'Bearer ' + t1}).status_code == 403
    assert client.get('/api/v1/status', headers={'Authorization': 'Bearer ' + t2}).status_code == 200
    assert client.get('/api/v1/status', headers={'Authorization': 'Bearer ' + t3}).status_code == 200

    db.set_control('session_idle_timeout_s', 1)
    sess = get_session(t2)
    db.execute("UPDATE sessions SET last_seen_at=? WHERE id=?", (time.time() - 120, sess['id']))
    assert client.get('/api/v1/status', headers={'Authorization': 'Bearer ' + t2}).status_code == 403


def test_login_rate_limit(client):
    from app.security.rate_limit import login_rate_limiter

    login_rate_limiter.clear()
    try:
        for _ in range(5):
            r = client.post('/api/v1/auth/login', json={'token': 'wrong-token', 'device_id': 'attacker'})
            assert r.status_code == 403
        blocked = client.post('/api/v1/auth/login', json={'token': 'wrong-token', 'device_id': 'attacker'})
        assert blocked.status_code == 429
    finally:
        login_rate_limiter.clear()


def test_metrics_prometheus_and_devices(client):
    login = client.post('/api/v1/auth/login', json={'token': 'test-owner-token', 'device_id': 'pixel-metrics'})
    token = login.json()['token']
    H = {'Authorization': 'Bearer ' + token}
    devices = client.get('/api/v1/auth/devices', headers=H)
    assert devices.status_code == 200
    assert any(d['device_id'] == 'pixel-metrics' for d in devices.json())
    metrics = client.get('/api/v1/metrics/prometheus', headers=H)
    assert metrics.status_code == 200
    body = metrics.text
    assert 'omniai_http_requests_total' in body
    assert 'omniai_active_sessions' in body
    assert 'omniai_http_latency_p95_seconds' in body
    assert 'omniai_http_route_requests_total' in body


def test_kill_switch_stops_running_sandbox():
    from app.sandbox.runner import sandbox
    from app.database import db
    db.set_control('kill_switch', False)
    out = {}
    def run():
        out.update(sandbox.run_python('import time; time.sleep(30)'))
    t = threading.Thread(target=run)
    t.start()
    time.sleep(.3)
    db.set_control('kill_switch', True)
    t.join(5)
    db.set_control('kill_switch', False)
    assert out.get('exit_code') != 0 and 'kill switch' in out.get('stderr', '').lower()
