from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from prague_housing.http import HttpClient
from prague_housing.transit.geo import haversine_m


@dataclass(frozen=True)
class PidStop:
    stop_id: str
    name: str
    lat: float
    lon: float
    lines: tuple[str, ...]


def parse_pid_stops(payload: dict[str, Any] | list[Any]) -> list[PidStop]:
    groups: Iterable[Any]
    if isinstance(payload, list):
        groups = payload
    else:
        groups = payload.get("stopGroups") or payload.get("stops") or []
    parsed: list[PidStop] = []
    for group in groups:
        name = str(group.get("name") or group.get("uniqueName") or "")
        group_lat = group.get("avgLat") or group.get("lat")
        group_lon = group.get("avgLon") or group.get("lon")
        stops = group.get("stops") or [group]
        for stop in stops:
            stop_id = str(stop.get("id") or stop.get("gtfsId") or "")
            if not stop_id:
                continue
            lat = stop.get("lat") or group_lat
            lon = stop.get("lon") or group_lon
            if lat is None or lon is None:
                continue
            lines_raw = stop.get("lines") or group.get("lines") or []
            line_names = tuple(
                str(item.get("name") or item.get("short_name") or item)
                for item in lines_raw
                if item
            )
            parsed.append(
                PidStop(
                    stop_id=stop_id,
                    name=str(stop.get("altIdosName") or name),
                    lat=float(lat),
                    lon=float(lon),
                    lines=line_names,
                )
            )
    return parsed


def nearest_stops(
    stops: list[PidStop],
    lat: float,
    lon: float,
    *,
    radius_m: float,
    limit: int,
) -> list[tuple[PidStop, int]]:
    ranked: list[tuple[PidStop, int]] = []
    for stop in stops:
        distance = int(round(haversine_m(lat, lon, stop.lat, stop.lon)))
        if distance <= radius_m:
            ranked.append((stop, distance))
    ranked.sort(key=lambda item: item[1])
    # Prefer unique stop names so one metro station does not fill the list.
    unique: list[tuple[PidStop, int]] = []
    seen_names: set[str] = set()
    for stop, distance in ranked:
        key = stop.name
        if key in seen_names:
            continue
        seen_names.add(key)
        unique.append((stop, distance))
        if len(unique) >= limit:
            break
    return unique


class PidStopIndex:
    def __init__(self, stops: list[PidStop]) -> None:
        self.stops = stops

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | list[Any]) -> "PidStopIndex":
        return cls(parse_pid_stops(payload))

    @classmethod
    def load(
        cls,
        http: HttpClient,
        url: str,
        cache_path: Path,
        *,
        max_age: timedelta = timedelta(hours=24),
    ) -> "PidStopIndex":
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.exists():
            age = datetime.now(timezone.utc) - datetime.fromtimestamp(
                cache_path.stat().st_mtime, tz=timezone.utc
            )
            if age <= max_age:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                return cls.from_payload(payload)
        payload = http.get_json(url)
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        return cls.from_payload(payload)

    def nearby(self, lat: float, lon: float, radius_m: float, limit: int) -> list[tuple[PidStop, int]]:
        return nearest_stops(self.stops, lat, lon, radius_m=radius_m, limit=limit)
