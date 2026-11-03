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


def test_spike_stream_sends_protocol_events_in_order():
    with client.stream("GET", "/api/spike/stream") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        events = [line.removeprefix("event: ") for line in response.iter_lines()
                  if line.startswith("event: ")]
    assert events[0] == "meta"
    assert events[-2:] == ["usage", "done"]
    assert set(events[1:-2]) == {"token"}
