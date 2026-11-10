from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Brussels")
PAUSE_START_WEEKDAY, PAUSE_START_HOUR = 4, 18  # Friday 18:00
PAUSE_END_HOUR = 8  # Monday 08:00
HOLIDAYS = (date(2026, 11, 11),)


def _pause_windows(start: datetime, end: datetime):
    """Yield merged weekend and holiday pauses in UTC that may touch [start, end]."""
    windows = []
    for holiday in HOLIDAYS:
        holiday_start = datetime.combine(holiday, time.min, tzinfo=LOCAL_TZ).astimezone(UTC)
        holiday_end = datetime.combine(holiday + timedelta(days=1), time.min, tzinfo=LOCAL_TZ).astimezone(UTC)
        if holiday_start <= end and holiday_end >= start:
            windows.append((holiday_start, holiday_end))
    local_day = start.astimezone(LOCAL_TZ).date() - timedelta(days=7)
    local_day += timedelta(days=(PAUSE_START_WEEKDAY - local_day.weekday()) % 7)
    while True:
        pause_start = datetime(local_day.year, local_day.month, local_day.day, PAUSE_START_HOUR, tzinfo=LOCAL_TZ)
        monday = local_day + timedelta(days=3)
        pause_end = datetime(monday.year, monday.month, monday.day, PAUSE_END_HOUR, tzinfo=LOCAL_TZ)
        if pause_start.astimezone(UTC) > end:
            break
        windows.append((pause_start.astimezone(UTC), pause_end.astimezone(UTC)))
        local_day += timedelta(days=7)
    merged = []
    for pause_start, pause_end in sorted(windows):
        if merged and pause_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], pause_end))
        else:
            merged.append((pause_start, pause_end))
    yield from merged


def add_working_time(start: datetime, duration: timedelta) -> datetime:
    """Add duration while excluding weekend and holiday pauses (Brussels)."""
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
    """Seconds between start and end outside weekend and holiday pauses."""
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


def paused_until(moment: datetime) -> datetime | None:
    instant = moment.astimezone(UTC)
    return next((end.astimezone(LOCAL_TZ) for start, end in _pause_windows(instant, instant)
                 if start <= instant < end), None)
