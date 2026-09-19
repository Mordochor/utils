from __future__ import annotations

from pathlib import Path

import pytest

from prague_housing.config import parse_config


@pytest.fixture
def sample_config(tmp_path: Path):
    return parse_config(
        {
            "filters": {
                "deal": "rent",
                "property_types": ["flat", "house"],
                "price_min_czk": 15000,
                "price_max_czk": 30000,
                "min_area_m2": 50,
                "max_pages_per_source": 3,
                "first_run": "report_all",
            },
            "destinations": [
                {
                    "id": "andel",
                    "name": "Anděl",
                    "lat": 50.0714,
                    "lon": 14.4036,
                    "arrive_by": "09:00",
                    "max_duration_min": 40,
                }
            ],
            "sources": {"sreality": {"enabled": False, "pause_s": 0}, "file": {"enabled": False}},
            "transit": {
                "walk_radius_m": 800,
                "nearby_stop_limit": 3,
                "departure_limit": 10,
                "request_pause_s": 0,
                "pid_stops_cache": str(tmp_path / "pid_stops.json"),
            },
            "storage": {"sqlite_path": str(tmp_path / "listings.db")},
        },
        base_dir=tmp_path,
    )
