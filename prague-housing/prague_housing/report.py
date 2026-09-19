from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from prague_housing.models import ScoredListing
from prague_housing.transit.headway import format_headway

CLASS_MARK = {
    "frequent": "HIGHLIGHT frequent",
    "regular": "regular",
    "sparse": "sparse",
    "unknown": "unknown",
}


def _minutes(seconds: int) -> int:
    return max(1, int(round(seconds / 60))) if seconds else 0


def render_markdown(scored: list[ScoredListing], *, generated_at: datetime | None = None) -> str:
    when = generated_at or datetime.now(timezone.utc)
    lines = [
        "# Prague housing watch",
        "",
        f"Generated {when.replace(microsecond=0).isoformat()} · {len(scored)} listing(s)",
        "",
        "Frequency classes: **frequent** ≤6 min · **regular** ≤12 min · **sparse** >12 min.",
        "",
    ]
    if not scored:
        lines.append("No new matching listings this run.")
        lines.append("")
        return "\n".join(lines)

    for item in scored:
        listing = item.listing
        price = f"{listing.price_czk:,} Kč".replace(",", " ") if listing.price_czk is not None else "?"
        area = f"{listing.area_m2:g} m²" if listing.area_m2 is not None else "? m²"
        badge = "fits commute caps" if item.passes_duration_filter else "over commute cap"
        lines.append(f"## {listing.title or listing.key}")
        lines.append("")
        lines.append(
            f"- {listing.property_type} · {listing.deal} · {price} · {area} · {listing.locality or 'Prague'}"
        )
        lines.append(f"- source `{listing.source}` · [{listing.url}]({listing.url})")
        lines.append(f"- commute filter: **{badge}**")
        if listing.lat is not None and listing.lon is not None:
            lines.append(f"- GPS `{listing.lat:.5f},{listing.lon:.5f}`")
        lines.append("")
        if item.journeys:
            lines.append("| Destination | Door-to-door | Walk | Transfers | Lines and period | Service |")
            lines.append("|---|---:|---:|---:|---|---|")
            for journey in item.journeys:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            journey.destination_name,
                            f"{_minutes(journey.duration_s)} min",
                            f"{_minutes(journey.walk_s)} min",
                            str(journey.transfers),
                            journey.summary,
                            CLASS_MARK.get(journey.service_class, journey.service_class),
                        ]
                    )
                    + " |"
                )
            lines.append("")
        else:
            lines.append("No door-to-door itinerary (set Google Maps or OpenTripPlanner).")
            lines.append("")
        if item.nearby_stops:
            lines.append("Nearby PID stops and how often they run:")
            lines.append("")
            for stop in item.nearby_stops:
                line_bits = ", ".join(
                    f"**{line.line}** {line.note}" if line.service_class == "frequent" else f"{line.line} {line.note}"
                    for line in stop.lines
                ) or "no lines"
                lines.append(f"- {stop.name} ({stop.distance_m} m): {line_bits}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(scored: list[ScoredListing], path: str | Path) -> Path:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(scored), encoding="utf-8")
    return report_path


def telegram_text(scored: list[ScoredListing], limit: int = 8) -> str:
    if not scored:
        return "Prague housing watch: no new matching listings."
    chunks = [f"Prague housing watch: {len(scored)} new listing(s)"]
    for item in scored[:limit]:
        listing = item.listing
        price = f"{listing.price_czk} Kč" if listing.price_czk is not None else "?"
        journeys = "; ".join(
            f"{j.destination_name} {_minutes(j.duration_s)}m ({j.summary})" for j in item.journeys
        ) or "no itinerary"
        chunks.append(f"• {listing.title} — {price} — {journeys}\n{listing.url}")
    if len(scored) > limit:
        chunks.append(f"…and {len(scored) - limit} more")
    return "\n\n".join(chunks)
