from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prague_housing.models import Listing


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ListingStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS listings (
                key TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                title TEXT,
                url TEXT,
                price_czk INTEGER,
                area_m2 REAL,
                property_type TEXT,
                deal TEXT,
                locality TEXT,
                lat REAL,
                lon REAL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                score_json TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def is_first_run(self) -> bool:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'initialized'"
        ).fetchone()
        return row is None

    def mark_initialized(self) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('initialized', ?)",
            (_utc_now(),),
        )
        self._conn.commit()

    def known_keys(self) -> set[str]:
        rows = self._conn.execute("SELECT key FROM listings").fetchall()
        return {row["key"] for row in rows}

    def upsert_listing(self, listing: Listing, *, seen_at: str | None = None) -> bool:
        """Insert or refresh a listing. Returns True if this key is new."""
        now = seen_at or _utc_now()
        existing = self._conn.execute(
            "SELECT first_seen FROM listings WHERE key = ?", (listing.key,)
        ).fetchone()
        if existing:
            self._conn.execute(
                """
                UPDATE listings
                SET title = ?, url = ?, price_czk = ?, area_m2 = ?, property_type = ?,
                    deal = ?, locality = ?, lat = ?, lon = ?, last_seen = ?
                WHERE key = ?
                """,
                (
                    listing.title,
                    listing.url,
                    listing.price_czk,
                    listing.area_m2,
                    listing.property_type,
                    listing.deal,
                    listing.locality,
                    listing.lat,
                    listing.lon,
                    now,
                    listing.key,
                ),
            )
            self._conn.commit()
            return False
        self._conn.execute(
            """
            INSERT INTO listings (
                key, source, source_id, title, url, price_czk, area_m2,
                property_type, deal, locality, lat, lon, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                listing.key,
                listing.source,
                listing.source_id,
                listing.title,
                listing.url,
                listing.price_czk,
                listing.area_m2,
                listing.property_type,
                listing.deal,
                listing.locality,
                listing.lat,
                listing.lon,
                now,
                now,
            ),
        )
        self._conn.commit()
        return True

    def save_score(self, key: str, payload: dict[str, Any]) -> None:
        self._conn.execute(
            "UPDATE listings SET score_json = ? WHERE key = ?",
            (json.dumps(payload, ensure_ascii=False), key),
        )
        self._conn.commit()
