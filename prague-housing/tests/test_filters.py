from __future__ import annotations

from prague_housing.filters import matches_filters
from prague_housing.models import Listing


def _listing(**overrides) -> Listing:
    data = dict(
        source="file",
        source_id="1",
        title="Byt 2+kk 55 m²",
        url="https://example.test/1",
        price_czk=22000,
        area_m2=55,
        property_type="flat",
        deal="rent",
        locality="Praha 3",
        lat=50.08,
        lon=14.45,
    )
    data.update(overrides)
    return Listing(**data)


def test_matches_price_and_size(sample_config):
    assert matches_filters(_listing(), sample_config.filters)
    assert not matches_filters(_listing(price_czk=40000), sample_config.filters)
    assert not matches_filters(_listing(area_m2=40), sample_config.filters)
    assert not matches_filters(_listing(deal="sale"), sample_config.filters)
    assert not matches_filters(_listing(property_type="land"), sample_config.filters)
    assert not matches_filters(_listing(price_czk=None), sample_config.filters)
    assert not matches_filters(_listing(area_m2=None), sample_config.filters)
