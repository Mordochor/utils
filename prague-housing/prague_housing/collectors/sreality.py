from __future__ import annotations

import re
from typing import Any, Iterable

from prague_housing.config import AppConfig
from prague_housing.http import HttpClient
from prague_housing.models import Listing

SREALITY_SEARCH_URL = "https://www.sreality.cz/api/cs/v2/estates"
PRAGUE_REGION_ID = 10

CATEGORY_MAIN = {"flat": 1, "house": 2}
CATEGORY_TYPE = {"sale": 1, "rent": 2}
TYPE_SLUG = {1: "prodej", 2: "pronajem", 3: "drazby"}
MAIN_SLUG = {1: "byt", 2: "dum", 3: "pozemek", 4: "komercni", 5: "ostatni"}
SUB_SLUG = {
    2: "1+kk",
    3: "1+1",
    4: "2+kk",
    5: "2+1",
    6: "3+kk",
    7: "3+1",
    8: "4+kk",
    9: "4+1",
    10: "5+kk",
    11: "5+1",
    12: "6-a-vice",
    16: "atypicky",
    37: "rodinny",
    39: "vila",
    43: "chalupa",
    33: "chata",
}

AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m(?:²|2)", re.IGNORECASE)


def extract_area_m2(title: str, raw: dict[str, Any] | None = None) -> float | None:
    if raw:
        for key in ("usable_area", "usableArea", "area"):
            value = raw.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
    match = AREA_RE.search(title or "")
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def listing_url(raw: dict[str, Any]) -> str:
    hash_id = raw.get("hash_id") or raw.get("id")
    seo = raw.get("seo") or {}
    type_cb = int(seo.get("category_type_cb") or 2)
    main_cb = int(seo.get("category_main_cb") or 1)
    sub_cb = int(seo.get("category_sub_cb") or 0)
    locality = seo.get("locality") or "praha"
    return (
        "https://www.sreality.cz/detail/"
        f"{TYPE_SLUG.get(type_cb, 'pronajem')}/"
        f"{MAIN_SLUG.get(main_cb, 'byt')}/"
        f"{SUB_SLUG.get(sub_cb, 'byt')}/"
        f"{locality}/{hash_id}"
    )


def parse_price(raw: dict[str, Any]) -> int | None:
    price = raw.get("price")
    if isinstance(price, (int, float)) and price > 1:
        return int(price)
    price_czk = raw.get("price_czk") or {}
    if isinstance(price_czk, dict):
        value = price_czk.get("value_raw") or price_czk.get("value")
        if isinstance(value, (int, float)) and value > 1:
            return int(value)
    return None


def parse_estate(raw: dict[str, Any]) -> Listing | None:
    hash_id = raw.get("hash_id") or raw.get("id")
    if hash_id is None:
        return None
    seo = raw.get("seo") or {}
    main_cb = int(seo.get("category_main_cb") or raw.get("category") or 1)
    type_cb = int(seo.get("category_type_cb") or 2)
    property_type = {1: "flat", 2: "house"}.get(main_cb)
    deal = {1: "sale", 2: "rent"}.get(type_cb)
    if property_type is None or deal is None:
        return None
    gps = raw.get("gps") or {}
    lat = gps.get("lat")
    lon = gps.get("lon")
    title = str(raw.get("name") or raw.get("title") or "")
    return Listing(
        source="sreality",
        source_id=str(hash_id),
        title=title,
        url=listing_url(raw),
        price_czk=parse_price(raw),
        area_m2=extract_area_m2(title, raw),
        property_type=property_type,
        deal=deal,
        locality=str(raw.get("locality") or ""),
        lat=float(lat) if lat is not None else None,
        lon=float(lon) if lon is not None else None,
        raw=raw,
    )


def search_params(config: AppConfig, property_type: str, page: int) -> dict[str, Any]:
    filters = config.filters
    params: dict[str, Any] = {
        "category_main_cb": CATEGORY_MAIN[property_type],
        "category_type_cb": CATEGORY_TYPE[filters.deal],
        "locality_region_id": PRAGUE_REGION_ID,
        "per_page": 20,
        "page": page,
    }
    if filters.price_min_czk is not None:
        params["czk_price_from"] = int(filters.price_min_czk)
    if filters.price_max_czk is not None:
        params["czk_price_to"] = int(filters.price_max_czk)
    if filters.min_area_m2 is not None:
        params["usable_area"] = f"{int(filters.min_area_m2)}|10000"
    return params


class SrealityCollector:
    name = "sreality"

    def __init__(self, config: AppConfig, http: HttpClient) -> None:
        self.config = config
        self.http = http

    def collect(self) -> list[Listing]:
        listings: list[Listing] = []
        seen: set[str] = set()
        for property_type in self.config.filters.property_types:
            if property_type not in CATEGORY_MAIN:
                continue
            listings.extend(self._collect_type(property_type, seen))
        return listings

    def _collect_type(self, property_type: str, seen: set[str]) -> list[Listing]:
        out: list[Listing] = []
        previous_ids: set[str] | None = None
        for page in range(1, self.config.filters.max_pages_per_source + 1):
            payload = self.http.get_json(
                SREALITY_SEARCH_URL,
                params=search_params(self.config, property_type, page),
                pause_s=self.config.sreality.pause_s,
            )
            estates = ((payload or {}).get("_embedded") or {}).get("estates") or []
            page_ids: set[str] = set()
            if not estates:
                break
            for raw in estates:
                listing = parse_estate(raw)
                if listing is None:
                    continue
                page_ids.add(listing.source_id)
                if listing.source_id in seen:
                    continue
                seen.add(listing.source_id)
                out.append(listing)
            if previous_ids is not None and page_ids == previous_ids:
                break
            if not page_ids:
                break
            previous_ids = page_ids
            result_size = (payload or {}).get("result_size")
            if isinstance(result_size, int) and len(out) >= result_size:
                break
        return out


def iter_parsed(estates: Iterable[dict[str, Any]]) -> list[Listing]:
    parsed: list[Listing] = []
    for raw in estates:
        listing = parse_estate(raw)
        if listing is not None:
            parsed.append(listing)
    return parsed
