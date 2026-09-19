from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from prague_housing.config import Destination
from prague_housing.models import Listing
from prague_housing.transit.google import arrival_unix, parse_google_route
from prague_housing.transit.otp import parse_otp_plan

DEST = Destination(
    id="andel",
    name="Anděl",
    lat=50.0714,
    lon=14.4036,
    arrive_by="09:00",
    max_duration_min=40,
)


def test_arrival_unix_rolls_to_next_day():
    now = datetime(2026, 9, 21, 10, 0, tzinfo=ZoneInfo("Europe/Prague"))
    ts = arrival_unix("09:00", now=now)
    assert ts is not None
    rolled = datetime.fromtimestamp(ts, tz=ZoneInfo("Europe/Prague"))
    assert rolled.day == 22
    assert rolled.hour == 9


def test_parse_google_route_duration_and_headway():
    payload = {
        "status": "OK",
        "routes": [
            {
                "legs": [
                    {
                        "duration": {"value": 1500},
                        "steps": [
                            {
                                "travel_mode": "WALKING",
                                "duration": {"value": 240},
                            },
                            {
                                "travel_mode": "TRANSIT",
                                "duration": {"value": 720},
                                "transit_details": {
                                    "headway": 240,
                                    "departure_stop": {"name": "I.P. Pavlova"},
                                    "arrival_stop": {"name": "Anděl"},
                                    "line": {
                                        "short_name": "C",
                                        "vehicle": {"type": "SUBWAY"},
                                    },
                                },
                            },
                            {
                                "travel_mode": "WALKING",
                                "duration": {"value": 180},
                            },
                        ],
                    }
                ]
            }
        ],
    }
    journey = parse_google_route(payload, DEST)
    assert journey is not None
    assert journey.duration_s == 1500
    assert journey.walk_s == 420
    assert journey.transfers == 0
    assert journey.service_class == "frequent"
    assert "C (every 4 min)" in journey.summary
    assert journey.legs[1].line == "C"


def test_parse_otp_plan():
    payload = {
        "plan": {
            "itineraries": [
                {
                    "duration": 1320,
                    "walkTime": 300,
                    "transfers": 1,
                    "legs": [
                        {"mode": "WALK", "duration": 180, "from": {"name": "home"}},
                        {
                            "mode": "TRAM",
                            "routeShortName": "22",
                            "duration": 600,
                            "headway": 480,
                            "from": {"name": "Národní"},
                            "to": {"name": "Anděl"},
                        },
                    ],
                }
            ]
        }
    }
    journey = parse_otp_plan(payload, DEST)
    assert journey is not None
    assert journey.provider == "otp"
    assert journey.duration_s == 1320
    assert journey.transfers == 1
    assert journey.service_class == "regular"
    assert "22 (every 8 min)" in journey.summary


def test_empty_routes():
    assert parse_google_route({"routes": []}, DEST) is None
    listing = Listing(
        source="x",
        source_id="1",
        title="t",
        url="u",
        price_czk=1,
        area_m2=50,
        property_type="flat",
        deal="rent",
        locality="",
        lat=None,
        lon=None,
    )
    assert listing.lat is None
