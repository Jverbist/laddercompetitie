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
        "event": "challenge.created",
        "challenge_id": challenge_id,
        "challenger": {"name": challenger_name, "rank": challenger_rank},
        "challenged": {"name": challenged_name, "rank": challenged_rank},
        "deadline_at": deadline_at.isoformat(),
        "text": (
            f"{challenger_name} (#{challenger_rank}) daagt "
            f"{challenged_name} (#{challenged_rank}) uit."
        ),
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
