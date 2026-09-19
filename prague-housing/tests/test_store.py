from __future__ import annotations

from pathlib import Path

from prague_housing.models import Listing
from prague_housing.store import ListingStore


def _listing(source_id: str = "1") -> Listing:
    return Listing(
        source="file",
        source_id=source_id,
        title="x",
        url="https://x",
        price_czk=1,
        area_m2=50,
        property_type="flat",
        deal="rent",
        locality="Praha",
        lat=50.0,
        lon=14.0,
    )


def test_upsert_detects_new_and_first_run(tmp_path: Path):
    store = ListingStore(tmp_path / "db.sqlite")
    assert store.is_first_run()
    assert store.upsert_listing(_listing()) is True
    assert store.upsert_listing(_listing()) is False
    assert store.known_keys() == {"file:1"}
    store.mark_initialized()
    assert not store.is_first_run()
    store.save_score("file:1", {"ok": True})
    store.close()
