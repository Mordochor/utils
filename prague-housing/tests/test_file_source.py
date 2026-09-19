from __future__ import annotations

from pathlib import Path

from prague_housing.collectors.file_source import load_listings


def test_load_json_and_csv(tmp_path: Path):
    json_path = tmp_path / "listings.json"
    json_path.write_text(
        """
        [
          {
            "source": "bezrealitky",
            "source_id": "abc",
            "title": "Byt 3+kk 70 m2",
            "url": "https://example.test/abc",
            "price_czk": 28000,
            "area_m2": 70,
            "property_type": "flat",
            "deal": "rent",
            "locality": "Praha 7",
            "lat": 50.1,
            "lon": 14.43
          }
        ]
        """,
        encoding="utf-8",
    )
    listings = load_listings(json_path)
    assert listings[0].key == "bezrealitky:abc"
    assert listings[0].area_m2 == 70

    csv_path = tmp_path / "listings.csv"
    csv_path.write_text(
        "source,source_id,title,url,price,area,property_type,deal,locality,lat,lon\n"
        "ulovdomov,9,Dum,https://x,25000,80,house,rent,Praha 5,50.05,14.36\n",
        encoding="utf-8",
    )
    houses = load_listings(csv_path)
    assert houses[0].property_type == "house"
    assert houses[0].price_czk == 25000
