from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from prague_housing.models import Listing


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def listing_from_mapping(raw: dict[str, Any], default_source: str = "file") -> Listing:
    source = str(raw.get("source") or default_source)
    source_id = str(raw.get("source_id") or raw.get("id") or raw.get("url"))
    if not source_id:
        raise ValueError("File listing needs source_id, id, or url")
    return Listing(
        source=source,
        source_id=source_id,
        title=str(raw.get("title") or raw.get("name") or ""),
        url=str(raw.get("url") or ""),
        price_czk=_optional_int(raw.get("price_czk") if "price_czk" in raw else raw.get("price")),
        area_m2=_optional_float(raw.get("area_m2") if "area_m2" in raw else raw.get("area")),
        property_type=str(raw.get("property_type") or "flat"),
        deal=str(raw.get("deal") or "rent"),
        locality=str(raw.get("locality") or ""),
        lat=_optional_float(raw.get("lat")),
        lon=_optional_float(raw.get("lon")),
        raw=raw,
    )


def load_listings(path: str | Path) -> list[Listing]:
    file_path = Path(path)
    if file_path.suffix.lower() == ".csv":
        with file_path.open(newline="", encoding="utf-8") as handle:
            return [listing_from_mapping(row) for row in csv.DictReader(handle)]
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("listings") or payload.get("items") or []
    if not isinstance(payload, list):
        raise ValueError("File source must be a JSON list or {listings: [...]}")
    return [listing_from_mapping(item) for item in payload]


class FileCollector:
    name = "file"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def collect(self) -> list[Listing]:
        if not self.path.exists():
            raise FileNotFoundError(f"Listing file not found: {self.path}")
        return load_listings(self.path)
