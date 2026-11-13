from datetime import datetime

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_border_schedule_is_rendered_on_login_page(monkeypatch):
    start = datetime.fromisoformat("2026-11-13T13:30:00+01:00")
    end = datetime.fromisoformat("2026-11-13T16:30:00+01:00")
    monkeypatch.setattr(settings, "finale_qualification_start", start)
    monkeypatch.setattr(settings, "finale_qualification_end", end)
    response = TestClient(app).get("/login")
    assert response.status_code == 200
    assert f'data-start="{start.isoformat()}"' in response.text
    assert f'data-end="{end.isoformat()}"' in response.text
    assert 'src="/static/finale-border.js?v=1"' in response.text
