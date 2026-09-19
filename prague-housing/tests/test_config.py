from __future__ import annotations

import os
from pathlib import Path

from prague_housing.config import load_config, parse_config


def test_parse_rejects_bad_deal():
    try:
        parse_config(
            {
                "filters": {"deal": "swap"},
                "destinations": [{"id": "a", "lat": 1, "lon": 2}],
            }
        )
    except ValueError as exc:
        assert "deal" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_env_interpolation(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "secret-key")
    path = tmp_path / "cfg.yaml"
    path.write_text(
        """
filters:
  deal: sale
  property_types: [flat]
destinations:
  - id: flora
    name: Flora
    lat: 50.077
    lon: 14.461
transit:
  google_api_key: ${GOOGLE_MAPS_API_KEY}
storage:
  sqlite_path: data/db.sqlite
""",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.filters.deal == "sale"
    assert config.transit.google_api_key == "secret-key"
    assert config.storage.sqlite_path == tmp_path / "data" / "db.sqlite"
    assert config.has_journey_planner


def test_empty_api_key_is_none():
    config = parse_config(
        {
            "destinations": [{"id": "x", "lat": 50.0, "lon": 14.0}],
            "transit": {"google_api_key": "${GOOGLE_MAPS_API_KEY}"},
            "notify": {"telegram_bot_token": "${TELEGRAM_BOT_TOKEN}"},
        }
    )
    assert config.transit.google_api_key is None
    assert config.notify.telegram_bot_token is None
    assert not config.has_journey_planner


def test_example_config_loads(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    monkeypatch.setenv("OTP_BASE_URL", "")
    monkeypatch.setenv("GOLEMIO_API_KEY", "")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config.example.yaml")
    assert config.filters.min_area_m2 == 50
    assert len(config.destinations) == 2
