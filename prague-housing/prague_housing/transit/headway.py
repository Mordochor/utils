from __future__ import annotations

from datetime import datetime
from statistics import median


SERVICE_FREQUENT_S = 6 * 60
SERVICE_REGULAR_S = 12 * 60


def classify_headway(seconds: int | None) -> str:
    if seconds is None or seconds <= 0:
        return "unknown"
    if seconds <= SERVICE_FREQUENT_S:
        return "frequent"
    if seconds <= SERVICE_REGULAR_S:
        return "regular"
    return "sparse"


def format_headway(seconds: int | None) -> str:
    if seconds is None or seconds <= 0:
        return "unknown interval"
    if seconds < 90:
        return "every ~1 min"
    minutes = max(1, int(round(seconds / 60)))
    return f"every {minutes} min"


def headway_from_datetimes(times: list[datetime]) -> int | None:
    unique = sorted({_as_naive_utc(item) for item in times})
    if len(unique) < 2:
        return None
    deltas = [(later - earlier).total_seconds() for earlier, later in zip(unique, unique[1:])]
    positive = [delta for delta in deltas if delta > 0]
    if not positive:
        return None
    return int(round(median(positive)))


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)


def worst_service_class(classes: list[str]) -> str:
    rank = {"sparse": 3, "regular": 2, "frequent": 1, "unknown": 0}
    if not classes:
        return "unknown"
    return max(classes, key=lambda item: rank.get(item, 0))
