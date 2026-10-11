from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_feed_requires_token(monkeypatch):
    monkeypatch.setattr(settings, "rss_feed_token", "geheim")
    client = TestClient(app)
    assert client.get("/feed/fout.xml").status_code == 404
    response = client.get("/feed/geheim.xml")
    assert response.status_code == 200
    assert "<rss" in response.text


def test_feed_disabled_without_token(monkeypatch):
    monkeypatch.setattr(settings, "rss_feed_token", "")
    assert TestClient(app).get("/feed/.xml").status_code == 404
