from __future__ import annotations

from prague_housing.collectors.sreality import (
    SrealityCollector,
    extract_area_m2,
    listing_url,
    parse_estate,
    search_params,
)
from prague_housing.http import SequenceHttp


ESTATE = {
    "hash_id": 1234567890,
    "name": "Pronájem bytu 2+kk 55 m²",
    "locality": "Štěpánská, Praha 1 - Nové Město",
    "price": 22000,
    "price_czk": {"value_raw": 22000, "unit": "za měsíc"},
    "gps": {"lat": 50.078, "lon": 14.426},
    "seo": {
        "category_main_cb": 1,
        "category_sub_cb": 4,
        "category_type_cb": 2,
        "locality": "praha-nove-mesto",
    },
}


def test_parse_estate_and_url():
    listing = parse_estate(ESTATE)
    assert listing is not None
    assert listing.source == "sreality"
    assert listing.source_id == "1234567890"
    assert listing.price_czk == 22000
    assert listing.area_m2 == 55
    assert listing.property_type == "flat"
    assert listing.deal == "rent"
    assert listing.lat == 50.078
    assert "praha-nove-mesto/1234567890" in listing.url
    assert listing_url(ESTATE).endswith("/2+kk/praha-nove-mesto/1234567890")


def test_extract_area_from_title_and_field():
    assert extract_area_m2("Prodej domu 120 m2") == 120
    assert extract_area_m2("no size", {"usable_area": 88}) == 88
    assert extract_area_m2("nothing") is None


def test_search_params(sample_config):
    params = search_params(sample_config, "flat", 2)
    assert params["category_main_cb"] == 1
    assert params["category_type_cb"] == 2
    assert params["locality_region_id"] == 10
    assert params["czk_price_from"] == 15000
    assert params["usable_area"] == "50|10000"
    assert params["page"] == 2


def test_pagination_stops_on_repeated_ids(sample_config):
    page = {"result_size": 40, "_embedded": {"estates": [ESTATE]}}
    http = SequenceHttp(by_url={"https://www.sreality.cz/api/cs/v2/estates": page})
    collector = SrealityCollector(sample_config, http)
    listings = collector.collect()
    # flats + houses, each stops after the repeated page
    assert {item.source_id for item in listings} == {"1234567890"}
    assert len(http.calls) == 4  # page1+page2 for flat, page1+page2 for house


def test_skips_estates_without_id():
    assert parse_estate({"name": "x"}) is None
