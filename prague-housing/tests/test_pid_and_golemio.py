from __future__ import annotations

from prague_housing.transit.geo import haversine_m
from prague_housing.transit.golemio import headways_from_board
from prague_housing.transit.pid_stops import PidStopIndex


PID_PAYLOAD = {
    "stopGroups": [
        {
            "name": "Anděl",
            "avgLat": 50.0714,
            "avgLon": 14.4036,
            "stops": [
                {
                    "id": "U104Z1P",
                    "lat": 50.0714,
                    "lon": 14.4036,
                    "lines": [{"name": "B"}, {"name": "9"}],
                },
                {
                    "id": "U104Z2P",
                    "lat": 50.0715,
                    "lon": 14.4037,
                    "lines": [{"name": "B"}],
                },
            ],
        },
        {
            "name": "Florenc",
            "avgLat": 50.0903,
            "avgLon": 14.4392,
            "stops": [{"id": "U107Z1P", "lat": 50.0903, "lon": 14.4392, "lines": [{"name": "C"}]}],
        },
    ]
}

BOARD = {
    "departures": [
        {
            "route": {"short_name": "B"},
            "departure_timestamp": {"predicted": "2026-09-21T09:00:00+02:00"},
        },
        {
            "route": {"short_name": "B"},
            "departure_timestamp": {"predicted": "2026-09-21T09:04:00+02:00"},
        },
        {
            "route": {"short_name": "B"},
            "departure_timestamp": {"predicted": "2026-09-21T09:08:00+02:00"},
        },
        {
            "route": {"short_name": "9"},
            "departure_timestamp": {"scheduled": "2026-09-21T09:00:00+02:00"},
        },
        {
            "route": {"short_name": "9"},
            "departure_timestamp": {"scheduled": "2026-09-21T09:08:00+02:00"},
        },
    ]
}


def test_haversine_and_nearest_unique_names():
    # ~1.1 km between Anděl and a nearby point should still be within 800m for Anděl itself
    index = PidStopIndex.from_payload(PID_PAYLOAD)
    nearby = index.nearby(50.0714, 14.4036, radius_m=500, limit=3)
    assert nearby[0][0].name == "Anděl"
    assert nearby[0][1] == 0
    names = [stop.name for stop, _ in nearby]
    assert names.count("Anděl") == 1
    assert haversine_m(50.0714, 14.4036, 50.0903, 14.4392) > 2000


def test_golemio_headways():
    lines = {item.line: item for item in headways_from_board(BOARD)}
    assert lines["B"].interval_seconds == 240
    assert lines["B"].service_class == "frequent"
    assert lines["B"].note == "every 4 min"
    assert lines["9"].interval_seconds == 480
    assert lines["9"].service_class == "regular"
