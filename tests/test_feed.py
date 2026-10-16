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


def test_registration_qr_is_public_png():
    response = TestClient(app).get("/register/qr.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_local_animation_assets_are_served():
    client = TestClient(app)
    assert client.get("/static/app-motion.js").status_code == 200
    library = client.get("/static/vendor/anime.umd.min.js")
    assert library.status_code == 200
    assert library.headers["content-type"].startswith("text/javascript")
