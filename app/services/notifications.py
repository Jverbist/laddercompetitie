import json
import logging
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def send_challenge_notification(
    *,
    webhook_url: str,
    challenge_id: int,
    challenger_name: str,
    challenger_rank: int,
    challenged_name: str,
    challenged_rank: int,
    deadline_at: datetime,
) -> None:
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "Nieuwe ladderuitdaging",
                            "weight": "Bolder",
                            "size": "Medium",
                        },
                        {
                            "type": "TextBlock",
                            "text": (
                                f"{challenger_name} (#{challenger_rank}) daagt "
                                f"{challenged_name} (#{challenged_rank}) uit."
                            ),
                            "wrap": True,
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Uitdaging", "value": str(challenge_id)},
                                {"title": "Deadline", "value": deadline_at.isoformat()},
                            ],
                        },
                    ],
                },
            }
        ],
    }
    request = Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5):
            pass
    except HTTPError as exc:
        logger.error("Teams challenge notification failed with HTTP status %s.", exc.code)
    except (URLError, TimeoutError):
        logger.error("Teams challenge notification could not be delivered.")
