from __future__ import annotations

from prague_housing.config import Filters
from prague_housing.models import Listing


def matches_filters(listing: Listing, filters: Filters) -> bool:
    if listing.deal != filters.deal:
        return False
    if listing.property_type not in filters.property_types:
        return False
    if listing.price_czk is None:
        return False
    if filters.price_min_czk is not None and listing.price_czk < filters.price_min_czk:
        return False
    if filters.price_max_czk is not None and listing.price_czk > filters.price_max_czk:
        return False
    if filters.min_area_m2 is not None:
        if listing.area_m2 is None or listing.area_m2 < filters.min_area_m2:
            return False
    return True
