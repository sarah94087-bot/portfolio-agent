from fastapi.testclient import TestClient

from portfolio_agent.main import app

client = TestClient(app)


def test_health_without_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    body = client.get("/api/health").json()
    assert body["db"] == {"ok": None}
    assert body["agent_enabled"] is True
    assert "cold" in body and "instance_uptime_ms" in body


def test_health_reports_kill_switch(monkeypatch):
    monkeypatch.setenv("AGENT_ENABLED", "false")
    assert client.get("/api/health").json()["agent_enabled"] is False


def test_health_reports_unreachable_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    db = client.get("/api/health").json()["db"]
    assert db["ok"] is False
    assert "error" in db


def test_health_can_skip_the_database(monkeypatch):
    # The external monitor's check: an unreachable database is not even tried.
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    body = client.get("/api/health", params={"db": 0}).json()
    assert body["db"] == {"ok": None, "skipped": True}
    assert body["agent_enabled"] is True


def test_api_responses_carry_the_security_headers(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    headers = client.get("/api/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_the_m1_streaming_spike_is_gone():
    assert client.get("/api/spike/stream").status_code == 404
