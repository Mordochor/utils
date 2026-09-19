from __future__ import annotations

from datetime import datetime

from prague_housing.config import AppConfig, Destination
from prague_housing.http import HttpClient
from prague_housing.models import Journey, Listing, NearbyStop, ScoredListing, TransitLeg
from prague_housing.transit.golemio import GolemioClient
from prague_housing.transit.google import GoogleDirections
from prague_housing.transit.headway import classify_headway, format_headway, worst_service_class
from prague_housing.transit.otp import OpenTripPlanner
from prague_housing.transit.pid_stops import PidStopIndex


def enrich_journey_with_stop_headways(journey: Journey, stops: list[NearbyStop]) -> Journey:
    headway_by_line: dict[str, int] = {}
    for stop in stops:
        for line in stop.lines:
            if line.interval_seconds and line.line not in headway_by_line:
                headway_by_line[line.line] = line.interval_seconds
    if not headway_by_line:
        return journey
    new_legs: list[TransitLeg] = []
    changed = False
    for leg in journey.legs:
        if leg.line and leg.headway_s is None and leg.line in headway_by_line:
            interval = headway_by_line[leg.line]
            new_legs.append(
                TransitLeg(
                    mode=leg.mode,
                    line=leg.line,
                    from_name=leg.from_name,
                    to_name=leg.to_name,
                    duration_s=leg.duration_s,
                    headway_s=interval,
                    service_class=classify_headway(interval),
                    note=f"{leg.line} {format_headway(interval)}",
                )
            )
            changed = True
        else:
            new_legs.append(leg)
    if not changed:
        return journey
    summary = " → ".join(
        f"{leg.line} ({format_headway(leg.headway_s)})" for leg in new_legs if leg.line
    ) or journey.summary
    return Journey(
        destination_id=journey.destination_id,
        destination_name=journey.destination_name,
        provider=journey.provider,
        duration_s=journey.duration_s,
        walk_s=journey.walk_s,
        transfers=journey.transfers,
        summary=summary,
        legs=new_legs,
        service_class=worst_service_class([leg.service_class for leg in new_legs if leg.line]),
    )


def passes_duration_limits(journeys: list[Journey], destinations: list[Destination]) -> bool:
    limits = {item.id: item.max_duration_min for item in destinations}
    if not any(limit is not None for limit in limits.values()):
        return True
    if not journeys:
        return False
    for journey in journeys:
        limit = limits.get(journey.destination_id)
        if limit is None:
            continue
        if journey.duration_s > limit * 60:
            return False
    return True


class TransitScorer:
    def __init__(
        self,
        config: AppConfig,
        http: HttpClient,
        *,
        stop_index: PidStopIndex | None = None,
        google: GoogleDirections | None = None,
        otp: OpenTripPlanner | None = None,
        golemio: GolemioClient | None = None,
    ) -> None:
        self.config = config
        self.http = http
        self.stop_index = stop_index
        self.google = google
        self.otp = otp
        self.golemio = golemio

    @classmethod
    def from_config(
        cls,
        config: AppConfig,
        http: HttpClient,
        *,
        stop_index: PidStopIndex | None = None,
    ) -> "TransitScorer":
        google = (
            GoogleDirections(http, config.transit.google_api_key, pause_s=config.transit.request_pause_s)
            if config.transit.google_api_key
            else None
        )
        otp = (
            OpenTripPlanner(http, config.transit.otp_base_url, pause_s=config.transit.request_pause_s)
            if config.transit.otp_base_url
            else None
        )
        golemio = (
            GolemioClient(
                http,
                config.transit.golemio_api_key,
                pause_s=config.transit.request_pause_s,
                limit=config.transit.departure_limit,
            )
            if config.transit.golemio_api_key
            else None
        )
        return cls(config, http, stop_index=stop_index, google=google, otp=otp, golemio=golemio)

    def ensure_stops(self) -> PidStopIndex | None:
        if self.stop_index is not None:
            return self.stop_index
        try:
            self.stop_index = PidStopIndex.load(
                self.http,
                self.config.transit.pid_stops_url,
                self.config.transit.pid_stops_cache,
            )
        except Exception:
            self.stop_index = None
        return self.stop_index

    def nearby_stops(self, listing: Listing) -> list[NearbyStop]:
        if listing.lat is None or listing.lon is None:
            return []
        index = self.ensure_stops()
        if index is None:
            return []
        nearby: list[NearbyStop] = []
        for stop, distance in index.nearby(
            listing.lat,
            listing.lon,
            radius_m=self.config.transit.walk_radius_m,
            limit=self.config.transit.nearby_stop_limit,
        ):
            lines = []
            if self.golemio is not None:
                try:
                    lines = self.golemio.departures(stop)
                except Exception:
                    lines = []
            if not lines and stop.lines:
                from prague_housing.models import LineHeadway

                lines = [
                    LineHeadway(
                        line=name,
                        vehicle=None,
                        interval_seconds=None,
                        sample_count=0,
                        service_class="unknown",
                        note="interval unknown (no Golemio key)",
                    )
                    for name in stop.lines
                ]
            nearby.append(
                NearbyStop(stop_id=stop.stop_id, name=stop.name, distance_m=distance, lines=lines)
            )
        return nearby

    def score(self, listing: Listing, *, now: datetime | None = None) -> ScoredListing:
        nearby = self.nearby_stops(listing)
        journeys: list[Journey] = []
        for destination in self.config.destinations:
            journey = None
            if self.google is not None:
                journey = self.google.plan(listing, destination, now=now)
            if journey is None and self.otp is not None:
                journey = self.otp.plan(listing, destination, now=now)
            if journey is not None:
                journeys.append(enrich_journey_with_stop_headways(journey, nearby))
        return ScoredListing(
            listing=listing,
            journeys=journeys,
            nearby_stops=nearby,
            passes_duration_filter=passes_duration_limits(journeys, self.config.destinations),
        )
