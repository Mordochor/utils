from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from prague_housing.config import Destination
from prague_housing.http import HttpClient
from prague_housing.models import Journey, Listing, TransitLeg
from prague_housing.transit.headway import classify_headway, format_headway, worst_service_class
from prague_housing.transit.google import PRAGUE_TZ


def parse_otp_plan(payload: dict[str, Any], destination: Destination) -> Journey | None:
    itineraries = ((payload.get("plan") or {}).get("itineraries")) or []
    if not itineraries:
        return None
    itinerary = itineraries[0]
    parsed_legs: list[TransitLeg] = []
    summary_parts: list[str] = []
    walk_s = int(itinerary.get("walkTime") or 0)
    for raw in itinerary.get("legs") or []:
        mode = str(raw.get("mode") or "").upper()
        duration = int(raw.get("duration") or 0)
        line = raw.get("routeShortName") or raw.get("route")
        headway = raw.get("headway")
        headway_s = int(headway) if isinstance(headway, (int, float)) else None
        if mode == "WALK":
            parsed_legs.append(
                TransitLeg(
                    mode="WALK",
                    line=None,
                    from_name=(raw.get("from") or {}).get("name"),
                    to_name=(raw.get("to") or {}).get("name"),
                    duration_s=duration,
                    headway_s=None,
                    service_class="unknown",
                    note=f"walk {max(1, duration // 60)} min",
                )
            )
            continue
        service = classify_headway(headway_s)
        parsed_legs.append(
            TransitLeg(
                mode=mode,
                line=str(line) if line else None,
                from_name=(raw.get("from") or {}).get("name"),
                to_name=(raw.get("to") or {}).get("name"),
                duration_s=duration,
                headway_s=headway_s,
                service_class=service,
                note=f"{line or mode} {format_headway(headway_s)}",
            )
        )
        if line:
            summary_parts.append(f"{line} ({format_headway(headway_s)})")
    duration_s = int(itinerary.get("duration") or 0)
    return Journey(
        destination_id=destination.id,
        destination_name=destination.name,
        provider="otp",
        duration_s=duration_s,
        walk_s=walk_s,
        transfers=int(itinerary.get("transfers") or 0),
        summary=" → ".join(summary_parts) or "transit",
        legs=parsed_legs,
        service_class=worst_service_class([leg.service_class for leg in parsed_legs if leg.line]),
    )


class OpenTripPlanner:
    def __init__(self, http: HttpClient, base_url: str, *, pause_s: float = 0.25) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/") + "/"
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
        when = now or datetime.now(PRAGUE_TZ)
        if when.tzinfo is None:
            when = when.replace(tzinfo=PRAGUE_TZ)
        when = when.astimezone(PRAGUE_TZ)
        params: dict[str, Any] = {
            "fromPlace": f"{listing.lat},{listing.lon}",
            "toPlace": f"{destination.lat},{destination.lon}",
            "mode": "TRANSIT,WALK",
            "numItineraries": 1,
            "date": when.date().isoformat(),
            "time": destination.arrive_by or when.strftime("%H:%M"),
            "arriveBy": "true" if destination.arrive_by else "false",
        }
        url = urljoin(self.base_url, "otp/routers/default/plan")
        payload = self.http.get_json(url, params=params, pause_s=self.pause_s)
        return parse_otp_plan(payload, destination)
