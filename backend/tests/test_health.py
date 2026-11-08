"""/api/health, and the warming the page asks for when it loads (spike S2)."""

from fastapi.testclient import TestClient

from portfolio_agent.main import app
from portfolio_agent.retrieval import embedder

client = TestClient(app)


def test_plain_health_does_not_load_the_model(monkeypatch):
    def fail():
        raise AssertionError("loaded the model")

    monkeypatch.setattr(embedder, "from_env", fail)
    body = client.get("/api/health").json()
    assert "embedder" not in body


def test_warm_loads_the_model_and_says_so(monkeypatch):
    calls = []
    monkeypatch.setattr(embedder, "from_env", lambda: calls.append(1) or object())
    body = client.get("/api/health", params={"warm": 1}).json()
    assert calls == [1]
    assert body["embedder"]["ready"] is True


def test_warm_without_model_files_is_not_ready(monkeypatch):
    monkeypatch.setattr(embedder, "from_env", lambda: None)
    assert client.get("/api/health?warm=1").json()["embedder"]["ready"] is False


def test_a_model_that_fails_to_load_is_reported_not_raised(monkeypatch):
    def broken():
        raise embedder.ModelFilesError("tokenizer.json is missing")

    monkeypatch.setattr(embedder, "from_env", broken)
    response = client.get("/api/health?warm=1")
    assert response.status_code == 200
    assert response.json()["embedder"] == {"ready": False, "error": "ModelFilesError"}
