from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):

        def repl(match: re.Match[str]) -> str:
            return os.environ.get(match.group(1), "")

        return _ENV_RE.sub(repl, value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.startswith("${") and stripped.endswith("}"):
        return None
    return stripped


@dataclass(frozen=True)
class Filters:
    deal: str
    property_types: list[str]
    price_min_czk: int | None
    price_max_czk: int | None
    min_area_m2: float | None
    max_pages_per_source: int
    first_run: str


@dataclass(frozen=True)
class Destination:
    id: str
    name: str
    lat: float
    lon: float
    arrive_by: str | None
    max_duration_min: int | None


@dataclass(frozen=True)
class TransitSettings:
    google_api_key: str | None
    otp_base_url: str | None
    golemio_api_key: str | None
    pid_stops_url: str
    pid_stops_cache: Path
    walk_radius_m: int
    nearby_stop_limit: int
    departure_limit: int
    request_pause_s: float


@dataclass(frozen=True)
class StorageSettings:
    sqlite_path: Path


@dataclass(frozen=True)
class NotifySettings:
    telegram_bot_token: str | None
    telegram_chat_id: str | None


@dataclass(frozen=True)
class ScheduleSettings:
    interval_minutes: int


@dataclass(frozen=True)
class HttpSettings:
    user_agent: str
    timeout_s: int


@dataclass(frozen=True)
class FileSourceSettings:
    enabled: bool
    path: Path | None


@dataclass(frozen=True)
class SrealitySettings:
    enabled: bool
    pause_s: float


@dataclass(frozen=True)
class AppConfig:
    filters: Filters
    destinations: list[Destination]
    sreality: SrealitySettings
    file_source: FileSourceSettings
    transit: TransitSettings
    storage: StorageSettings
    notify: NotifySettings
    schedule: ScheduleSettings
    http: HttpSettings
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def has_journey_planner(self) -> bool:
        return bool(self.transit.google_api_key or self.transit.otp_base_url)


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a mapping")
    data = _expand_env(raw)
    return parse_config(data, base_dir=config_path.parent)


def parse_config(data: dict[str, Any], base_dir: Path | None = None) -> AppConfig:
    base = base_dir or Path.cwd()
    filters_raw = data.get("filters") or {}
    deal = str(filters_raw.get("deal", "rent")).lower()
    if deal not in {"rent", "sale"}:
        raise ValueError("filters.deal must be 'rent' or 'sale'")
    property_types = [
        str(item).lower() for item in filters_raw.get("property_types") or ["flat", "house"]
    ]
    allowed_types = {"flat", "house"}
    unknown = set(property_types) - allowed_types
    if unknown:
        raise ValueError(f"Unknown property types: {sorted(unknown)}")
    first_run = str(filters_raw.get("first_run", "report_all"))
    if first_run not in {"report_all", "mark_seen_only"}:
        raise ValueError("filters.first_run must be report_all or mark_seen_only")

    destinations: list[Destination] = []
    for item in data.get("destinations") or []:
        destinations.append(
            Destination(
                id=str(item["id"]),
                name=str(item.get("name") or item["id"]),
                lat=float(item["lat"]),
                lon=float(item["lon"]),
                arrive_by=_empty_to_none(str(item["arrive_by"])) if item.get("arrive_by") else None,
                max_duration_min=int(item["max_duration_min"])
                if item.get("max_duration_min") is not None
                else None,
            )
        )
    if not destinations:
        raise ValueError("At least one destination is required")

    sources = data.get("sources") or {}
    sreality_raw = sources.get("sreality") or {}
    file_raw = sources.get("file") or {}
    file_path = file_raw.get("path")
    transit_raw = data.get("transit") or {}
    storage_raw = data.get("storage") or {}
    notify_raw = data.get("notify") or {}
    schedule_raw = data.get("schedule") or {}
    http_raw = data.get("http") or {}

    def resolve_path(value: str | None, default: str) -> Path:
        raw_path = Path(value or default)
        return raw_path if raw_path.is_absolute() else base / raw_path

    return AppConfig(
        filters=Filters(
            deal=deal,
            property_types=property_types,
            price_min_czk=filters_raw.get("price_min_czk"),
            price_max_czk=filters_raw.get("price_max_czk"),
            min_area_m2=filters_raw.get("min_area_m2"),
            max_pages_per_source=int(filters_raw.get("max_pages_per_source", 5)),
            first_run=first_run,
        ),
        destinations=destinations,
        sreality=SrealitySettings(
            enabled=bool(sreality_raw.get("enabled", True)),
            pause_s=float(sreality_raw.get("pause_s", 0.8)),
        ),
        file_source=FileSourceSettings(
            enabled=bool(file_raw.get("enabled", False)),
            path=resolve_path(str(file_path), "extra-listings.json") if file_path else None,
        ),
        transit=TransitSettings(
            google_api_key=_empty_to_none(str(transit_raw.get("google_api_key") or "")),
            otp_base_url=_empty_to_none(str(transit_raw.get("otp_base_url") or "")),
            golemio_api_key=_empty_to_none(str(transit_raw.get("golemio_api_key") or "")),
            pid_stops_url=str(
                transit_raw.get("pid_stops_url") or "https://data.pid.cz/stops/json/stops.json"
            ),
            pid_stops_cache=resolve_path(transit_raw.get("pid_stops_cache"), "data/pid_stops.json"),
            walk_radius_m=int(transit_raw.get("walk_radius_m", 700)),
            nearby_stop_limit=int(transit_raw.get("nearby_stop_limit", 4)),
            departure_limit=int(transit_raw.get("departure_limit", 24)),
            request_pause_s=float(transit_raw.get("request_pause_s", 0.25)),
        ),
        storage=StorageSettings(
            sqlite_path=resolve_path(storage_raw.get("sqlite_path"), "data/listings.db"),
        ),
        notify=NotifySettings(
            telegram_bot_token=_empty_to_none(str(notify_raw.get("telegram_bot_token") or "")),
            telegram_chat_id=_empty_to_none(str(notify_raw.get("telegram_chat_id") or "")),
        ),
        schedule=ScheduleSettings(interval_minutes=int(schedule_raw.get("interval_minutes", 60))),
        http=HttpSettings(
            user_agent=str(
                http_raw.get("user_agent") or "prague-housing/0.1 (+personal apartment search)"
            ),
            timeout_s=int(http_raw.get("timeout_s", 30)),
        ),
        raw=data,
    )
