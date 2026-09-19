from __future__ import annotations

from datetime import datetime
from typing import Any

from prague_housing.http import HttpClient
from prague_housing.models import LineHeadway
from prague_housing.transit.headway import classify_headway, format_headway, headway_from_datetimes
from prague_housing.transit.pid_stops import PidStop

GOLEMIO_DEPARTURES_URL = "https://api.golemio.cz/v2/pid/departureboards"


def parse_departure_times(payload: dict[str, Any]) -> dict[str, list[datetime]]:
    by_line: dict[str, list[datetime]] = {}
    for item in payload.get("departures") or []:
        route = item.get("route") or {}
        line = str(route.get("short_name") or route.get("shortName") or item.get("line") or "")
        if not line:
            continue
        stamp = (item.get("departure_timestamp") or {}).get("predicted") or (
            item.get("departure_timestamp") or {}
        ).get("scheduled")
        if not stamp:
            continue
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        by_line.setdefault(line, []).append(when)
    return by_line


def headways_from_board(payload: dict[str, Any], known_lines: tuple[str, ...] = ()) -> list[LineHeadway]:
    by_line = parse_departure_times(payload)
    lines = list(by_line.keys())
    if known_lines:
        extra = [name for name in known_lines if name not in by_line]
        lines.extend(extra)
    result: list[LineHeadway] = []
    for line in lines:
        times = by_line.get(line, [])
        interval = headway_from_datetimes(times)
        result.append(
            LineHeadway(
                line=line,
                vehicle=None,
                interval_seconds=interval,
                sample_count=len(times),
                service_class=classify_headway(interval),
                note=format_headway(interval),
            )
        )
    return result


class GolemioClient:
    def __init__(self, http: HttpClient, api_key: str, *, pause_s: float = 0.25, limit: int = 24) -> None:
        self.http = http
        self.api_key = api_key
        self.pause_s = pause_s
        self.limit = limit

    def departures(self, stop: PidStop) -> list[LineHeadway]:
        payload = self.http.get_json(
            GOLEMIO_DEPARTURES_URL,
            params={"ids": stop.stop_id, "limit": self.limit},
            headers={"X-Access-Token": self.api_key},
            pause_s=self.pause_s,
        )
        return headways_from_board(payload, stop.lines)
