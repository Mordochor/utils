from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Listing:
    source: str
    source_id: str
    title: str
    url: str
    price_czk: int | None
    area_m2: float | None
    property_type: str
    deal: str
    locality: str
    lat: float | None
    lon: float | None
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("raw", None)
        return data


@dataclass(frozen=True)
class LineHeadway:
    line: str
    vehicle: str | None
    interval_seconds: int | None
    sample_count: int
    service_class: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NearbyStop:
    stop_id: str
    name: str
    distance_m: int
    lines: list[LineHeadway]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TransitLeg:
    mode: str
    line: str | None
    from_name: str | None
    to_name: str | None
    duration_s: int | None
    headway_s: int | None
    service_class: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Journey:
    destination_id: str
    destination_name: str
    provider: str
    duration_s: int
    walk_s: int
    transfers: int
    summary: str
    legs: list[TransitLeg]
    service_class: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoredListing:
    listing: Listing
    journeys: list[Journey]
    nearby_stops: list[NearbyStop]
    passes_duration_filter: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing": self.listing.to_public_dict(),
            "journeys": [j.to_dict() for j in self.journeys],
            "nearby_stops": [s.to_dict() for s in self.nearby_stops],
            "passes_duration_filter": self.passes_duration_filter,
        }
