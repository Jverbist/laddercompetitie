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

        def getcode(self):
            return 202

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
        challenger_email="jules@example.com",
        challenged_email="yasmine@example.com",
    )

    request = captured["request"]
    assert captured["timeout"] == 5
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data) == {
        "type": "message",
        "challenge_id": 17,
        "challenger_name": "Jules",
        "challenger_email": "jules@example.com",
        "challenged_name": "Yasmine",
        "challenged_email": "yasmine@example.com",
        "deadline_at": deadline.isoformat(),
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "msteams": {
                        "entities": [
                            {
                                "type": "mention",
                                "text": "<at>Yasmine</at>",
                                "mentioned": {"id": "yasmine@example.com", "name": "Yasmine"},
                            }
                        ]
                    },
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "Nieuwe ladderuitdaging",
                            "weight": "Bolder",
                            "size": "Medium",
                        },
                        {
                            "type": "TextBlock",
                            "text": "Jules (#8) daagt <at>Yasmine</at> (#5) uit.",
                            "wrap": True,
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Uitdaging", "value": "17"},
                                {"title": "Deadline", "value": deadline.isoformat()},
                            ],
                        },
                    ],
                },
            }
        ],
    }
