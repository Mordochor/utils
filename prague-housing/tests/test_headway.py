from __future__ import annotations

from datetime import datetime, timedelta

from prague_housing.transit.headway import (
    classify_headway,
    format_headway,
    headway_from_datetimes,
    worst_service_class,
)


def test_headway_median_and_labels():
    start = datetime(2026, 9, 21, 9, 0, 0)
    times = [start + timedelta(minutes=offset) for offset in (0, 4, 8, 13)]
    interval = headway_from_datetimes(times)
    assert interval == 4 * 60
    assert classify_headway(interval) == "frequent"
    assert format_headway(interval) == "every 4 min"
    assert classify_headway(10 * 60) == "regular"
    assert classify_headway(20 * 60) == "sparse"
    assert classify_headway(None) == "unknown"
    assert format_headway(None) == "unknown interval"
    assert worst_service_class(["frequent", "sparse"]) == "sparse"
    assert headway_from_datetimes([start]) is None
