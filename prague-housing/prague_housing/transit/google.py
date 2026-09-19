from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from prague_housing.config import Destination
from prague_housing.http import HttpClient
from prague_housing.models import Journey, Listing, TransitLeg
from prague_housing.transit.headway import classify_headway, format_headway, worst_service_class

GOOGLE_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
PRAGUE_TZ = ZoneInfo("Europe/Prague")


def arrival_unix(clock: str | None, *, now: datetime | None = None) -> int | None:
    if not clock:
        return None
    hour, minute = (int(part) for part in clock.split(":", 1))
    current = now or datetime.now(PRAGUE_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=PRAGUE_TZ)
    current = current.astimezone(PRAGUE_TZ)
    target = datetime.combine(current.date(), time(hour, minute), tzinfo=PRAGUE_TZ)
    if target <= current:
        target += timedelta(days=1)
    return int(target.timestamp())


def parse_google_route(payload: dict[str, Any], destination: Destination) -> Journey | None:
    routes = payload.get("routes") or []
    if not routes:
        return None
    legs = routes[0].get("legs") or []
    if not legs:
        return None
    duration_s = sum(int((leg.get("duration") or {}).get("value") or 0) for leg in legs)
    walk_s = 0
    transit_count = 0
    parsed_legs: list[TransitLeg] = []
    summary_parts: list[str] = []
    for leg in legs:
        for step in leg.get("steps") or []:
            mode = str(step.get("travel_mode") or "").upper()
            duration = int((step.get("duration") or {}).get("value") or 0)
            if mode == "WALKING":
                walk_s += duration
                parsed_legs.append(
                    TransitLeg(
                        mode="WALK",
                        line=None,
                        from_name=None,
                        to_name=None,
                        duration_s=duration,
                        headway_s=None,
                        service_class="unknown",
                        note=f"walk {max(1, duration // 60)} min",
                    )
                )
                continue
            details = step.get("transit_details") or {}
            line_info = details.get("line") or {}
            line = str(line_info.get("short_name") or line_info.get("name") or "")
            vehicle = ((line_info.get("vehicle") or {}).get("type") or "TRANSIT").lower()
            headway = details.get("headway")
            headway_s = int(headway) if isinstance(headway, (int, float)) else None
            service = classify_headway(headway_s)
            parsed_legs.append(
                TransitLeg(
                    mode=vehicle.upper(),
                    line=line or None,
                    from_name=(details.get("departure_stop") or {}).get("name"),
                    to_name=(details.get("arrival_stop") or {}).get("name"),
                    duration_s=duration,
                    headway_s=headway_s,
                    service_class=service,
                    note=f"{line or vehicle} {format_headway(headway_s)}",
                )
            )
            transit_count += 1
            if line:
                summary_parts.append(f"{line} ({format_headway(headway_s)})")
    return Journey(
        destination_id=destination.id,
        destination_name=destination.name,
        provider="google",
        duration_s=duration_s,
        walk_s=walk_s,
        transfers=max(0, transit_count - 1),
        summary=" → ".join(summary_parts) or "transit",
        legs=parsed_legs,
        service_class=worst_service_class([leg.service_class for leg in parsed_legs if leg.line]),
    )


class GoogleDirections:
    def __init__(self, http: HttpClient, api_key: str, *, pause_s: float = 0.25) -> None:
        self.http = http
        self.api_key = api_key
        self.pause_s = pause_s

    def plan(
        self,
        listing: Listing,
        destination: Destination,
        *,
        now: datetime | None = None,
    ) -> Journey | None:
        if listing.lat is None or listing.lon is None:
            return None
        params: dict[str, Any] = {
            "origin": f"{listing.lat},{listing.lon}",
            "destination": f"{destination.lat},{destination.lon}",
            "mode": "transit",
            "alternatives": "false",
            "key": self.api_key,
        }
        arrival = arrival_unix(destination.arrive_by, now=now)
        if arrival is not None:
            params["arrival_time"] = arrival
        payload = self.http.get_json(
            GOOGLE_DIRECTIONS_URL,
            params=params,
            pause_s=self.pause_s,
        )
        if payload.get("status") not in (None, "OK"):
            return None
        return parse_google_route(payload, destination)
