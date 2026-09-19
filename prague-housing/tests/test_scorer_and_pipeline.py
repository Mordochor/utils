from __future__ import annotations

from pathlib import Path

from prague_housing.collectors.file_source import FileCollector
from prague_housing.config import Destination
from prague_housing.http import SequenceHttp
from prague_housing.models import Journey, LineHeadway, Listing, NearbyStop, TransitLeg
from prague_housing.pipeline import Pipeline
from prague_housing.report import render_markdown
from prague_housing.store import ListingStore
from prague_housing.transit.pid_stops import PidStopIndex
from prague_housing.transit.scorer import TransitScorer, enrich_journey_with_stop_headways, passes_duration_limits


def _listing() -> Listing:
    return Listing(
        source="file",
        source_id="vin",
        title="Pronájem bytu 2+kk 55 m²",
        url="https://example.test/vin",
        price_czk=22000,
        area_m2=55,
        property_type="flat",
        deal="rent",
        locality="Vinohrady",
        lat=50.0755,
        lon=14.4378,
    )


PID_PAYLOAD = {
    "stopGroups": [
        {
            "name": "Náměstí Míru",
            "avgLat": 50.0753,
            "avgLon": 14.4376,
            "stops": [
                {
                    "id": "U107Z8P",
                    "lat": 50.0753,
                    "lon": 14.4376,
                    "lines": [{"name": "A"}, {"name": "22"}],
                }
            ],
        }
    ]
}

GOOGLE_OK = {
    "status": "OK",
    "routes": [
        {
            "legs": [
                {
                    "duration": {"value": 1260},
                    "steps": [
                        {"travel_mode": "WALKING", "duration": {"value": 180}},
                        {
                            "travel_mode": "TRANSIT",
                            "duration": {"value": 900},
                            "transit_details": {
                                "line": {"short_name": "A", "vehicle": {"type": "SUBWAY"}},
                                "departure_stop": {"name": "Náměstí Míru"},
                                "arrival_stop": {"name": "Anděl"},
                            },
                        },
                    ],
                }
            ]
        }
    ],
}

BOARD = {
    "departures": [
        {
            "route": {"short_name": "A"},
            "departure_timestamp": {"predicted": "2026-09-21T09:00:00+02:00"},
        },
        {
            "route": {"short_name": "A"},
            "departure_timestamp": {"predicted": "2026-09-21T09:03:00+02:00"},
        },
        {
            "route": {"short_name": "A"},
            "departure_timestamp": {"predicted": "2026-09-21T09:06:00+02:00"},
        },
    ]
}


def test_enrich_fills_missing_headway():
    journey = Journey(
        destination_id="andel",
        destination_name="Anděl",
        provider="google",
        duration_s=1200,
        walk_s=180,
        transfers=0,
        summary="A (unknown interval)",
        legs=[
            TransitLeg(
                mode="SUBWAY",
                line="A",
                from_name="Náměstí Míru",
                to_name="Anděl",
                duration_s=900,
                headway_s=None,
                service_class="unknown",
                note="A unknown interval",
            )
        ],
        service_class="unknown",
    )
    stops = [
        NearbyStop(
            stop_id="U107Z8P",
            name="Náměstí Míru",
            distance_m=80,
            lines=[
                LineHeadway(
                    line="A",
                    vehicle="metro",
                    interval_seconds=180,
                    sample_count=3,
                    service_class="frequent",
                    note="every 3 min",
                )
            ],
        )
    ]
    enriched = enrich_journey_with_stop_headways(journey, stops)
    assert enriched.legs[0].headway_s == 180
    assert enriched.service_class == "frequent"
    assert "every 3 min" in enriched.summary


def test_duration_filter():
    dests = [
        Destination(id="andel", name="Anděl", lat=1, lon=2, arrive_by=None, max_duration_min=40)
    ]
    short = Journey(
        destination_id="andel",
        destination_name="Anděl",
        provider="x",
        duration_s=20 * 60,
        walk_s=0,
        transfers=0,
        summary="",
        legs=[],
        service_class="frequent",
    )
    long = Journey(
        destination_id="andel",
        destination_name="Anděl",
        provider="x",
        duration_s=50 * 60,
        walk_s=0,
        transfers=0,
        summary="",
        legs=[],
        service_class="sparse",
    )
    assert passes_duration_limits([short], dests)
    assert not passes_duration_limits([long], dests)
    assert not passes_duration_limits([], dests)


def test_scorer_combines_google_and_golemio(sample_config):
    http = SequenceHttp(
        by_url={
            "https://maps.googleapis.com/maps/api/directions/json": GOOGLE_OK,
            "https://api.golemio.cz/v2/pid/departureboards": BOARD,
        }
    )
    from prague_housing.transit.golemio import GolemioClient
    from prague_housing.transit.google import GoogleDirections

    scorer = TransitScorer(
        sample_config,
        http,
        stop_index=PidStopIndex.from_payload(PID_PAYLOAD),
        google=GoogleDirections(http, "key", pause_s=0),
        golemio=GolemioClient(http, "token", pause_s=0),
    )
    scored = scorer.score(_listing())
    assert scored.passes_duration_filter
    assert scored.journeys[0].duration_s == 1260
    assert scored.journeys[0].legs[1].headway_s == 180
    assert scored.nearby_stops[0].name == "Náměstí Míru"
    assert scored.nearby_stops[0].lines[0].note == "every 3 min"


def test_pipeline_first_run_then_only_new(tmp_path: Path, sample_config):
    listings_path = tmp_path / "extra.json"
    listings_path.write_text(
        """
        [
          {
            "source": "file",
            "source_id": "vin",
            "title": "Pronájem bytu 2+kk 55 m²",
            "url": "https://example.test/vin",
            "price_czk": 22000,
            "area_m2": 55,
            "property_type": "flat",
            "deal": "rent",
            "locality": "Vinohrady",
            "lat": 50.0755,
            "lon": 14.4378
          },
          {
            "source": "file",
            "source_id": "tiny",
            "title": "Garzonka 20 m2",
            "url": "https://example.test/tiny",
            "price_czk": 16000,
            "area_m2": 20,
            "property_type": "flat",
            "deal": "rent",
            "locality": "Praha 1"
          }
        ]
        """,
        encoding="utf-8",
    )
    store = ListingStore(tmp_path / "db.sqlite")
    scorer = TransitScorer(
        sample_config,
        SequenceHttp([]),
        stop_index=PidStopIndex.from_payload(PID_PAYLOAD),
    )
    pipeline = Pipeline(
        sample_config,
        http=SequenceHttp([]),
        store=store,
        scorer=scorer,
        collectors=[FileCollector(listings_path)],
    )
    first = pipeline.run(report_dir=tmp_path / "reports")
    assert first.fetched == 2
    assert first.matching == 1
    assert first.new == 1
    assert first.first_run
    assert first.report_path is not None
    assert "Pronájem bytu 2+kk" in first.markdown
    assert "every" in first.markdown or "Náměstí Míru" in first.markdown

    second = pipeline.run(report_dir=tmp_path / "reports")
    assert second.new == 0
    assert "No new matching listings" in second.markdown


def test_report_highlights_frequent_service():
    from prague_housing.models import ScoredListing

    scored = ScoredListing(
        listing=_listing(),
        journeys=[
            Journey(
                destination_id="andel",
                destination_name="Anděl",
                provider="google",
                duration_s=1260,
                walk_s=180,
                transfers=0,
                summary="A (every 3 min)",
                legs=[],
                service_class="frequent",
            )
        ],
        nearby_stops=[
            NearbyStop(
                stop_id="1",
                name="Náměstí Míru",
                distance_m=90,
                lines=[
                    LineHeadway(
                        line="A",
                        vehicle=None,
                        interval_seconds=180,
                        sample_count=3,
                        service_class="frequent",
                        note="every 3 min",
                    )
                ],
            )
        ],
        passes_duration_filter=True,
    )
    text = render_markdown([scored])
    assert "HIGHLIGHT frequent" in text
    assert "**A** every 3 min" in text
    assert "fits commute caps" in text
