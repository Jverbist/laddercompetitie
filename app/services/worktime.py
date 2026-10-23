from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Brussels")
PAUSE_START_WEEKDAY, PAUSE_START_HOUR = 4, 18  # Friday 18:00
PAUSE_END_HOUR = 8  # Monday 08:00


def _pause_windows(start: datetime, end: datetime):
    """Yield (pause_start, pause_end) in UTC for every weekend pause that may touch [start, end]."""
    local_day = start.astimezone(LOCAL_TZ).date() - timedelta(days=7)
    local_day += timedelta(days=(PAUSE_START_WEEKDAY - local_day.weekday()) % 7)
    while True:
        pause_start = datetime(local_day.year, local_day.month, local_day.day, PAUSE_START_HOUR, tzinfo=LOCAL_TZ)
        monday = local_day + timedelta(days=3)
        pause_end = datetime(monday.year, monday.month, monday.day, PAUSE_END_HOUR, tzinfo=LOCAL_TZ)
        if pause_start.astimezone(UTC) > end:
            return
        yield pause_start.astimezone(UTC), pause_end.astimezone(UTC)
        local_day += timedelta(days=7)


def add_working_time(start: datetime, duration: timedelta) -> datetime:
    """Add duration to start while the clock is stopped from Friday 18:00 to Monday 08:00 (Brussels)."""
    cursor, remaining = start.astimezone(UTC), duration
    for pause_start, pause_end in _pause_windows(cursor, cursor + duration + timedelta(days=400)):
        if pause_end <= cursor:
            continue
        if cursor >= pause_start:
            cursor = pause_end
            continue
        available = pause_start - cursor
        if remaining <= available:
            break
        remaining -= available
        cursor = pause_end
    return (cursor + remaining).astimezone(start.tzinfo)


def working_seconds_between(start: datetime, end: datetime) -> int:
    """Seconds between start and end that are not inside a weekend pause."""
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    if end <= start:
        return 0
    total = end - start
    for pause_start, pause_end in _pause_windows(start, end):
        overlap = min(end, pause_end) - max(start, pause_start)
        if overlap > timedelta(0):
            total -= overlap
    return int(total.total_seconds())


def is_paused(moment: datetime) -> bool:
    moment = moment.astimezone(UTC)
    return any(start <= moment < end for start, end in _pause_windows(moment, moment))
