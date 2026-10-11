import json
from datetime import UTC, datetime

from app.services import notifications


def test_challenge_notification_posts_competition_details(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(notifications, "urlopen", fake_urlopen)
    deadline = datetime(2026, 11, 13, 23, 59, tzinfo=UTC)

    notifications.send_challenge_notification(
        webhook_url="https://example.invalid/hooks/test",
        challenge_id=17,
        challenger_name="Jules",
        challenger_rank=8,
        challenged_name="Yasmine",
        challenged_rank=5,
        deadline_at=deadline,
    )

    request = captured["request"]
    assert captured["timeout"] == 5
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data) == {
        "event": "challenge.created",
        "challenge_id": 17,
        "challenger": {"name": "Jules", "rank": 8},
        "challenged": {"name": "Yasmine", "rank": 5},
        "deadline_at": deadline.isoformat(),
        "text": "Jules (#8) daagt Yasmine (#5) uit.",
    }
