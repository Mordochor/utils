from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from prague_housing.collectors.file_source import FileCollector
from prague_housing.collectors.sreality import SrealityCollector
from prague_housing.config import AppConfig
from prague_housing.filters import matches_filters
from prague_housing.http import HttpClient, UrlLibHttp
from prague_housing.models import Listing, ScoredListing
from prague_housing.notify import send_telegram
from prague_housing.report import render_markdown, telegram_text, write_report
from prague_housing.store import ListingStore
from prague_housing.transit.scorer import TransitScorer


@dataclass
class RunResult:
    fetched: int
    matching: int
    new: int
    scored: list[ScoredListing]
    report_path: Path | None
    first_run: bool
    markdown: str


class Pipeline:
    def __init__(
        self,
        config: AppConfig,
        http: HttpClient | None = None,
        store: ListingStore | None = None,
        scorer: TransitScorer | None = None,
        collectors: list | None = None,
    ) -> None:
        self.config = config
        self.http = http or UrlLibHttp(config.http.user_agent, config.http.timeout_s)
        self.store = store or ListingStore(config.storage.sqlite_path)
        self.scorer = scorer or TransitScorer.from_config(config, self.http)
        self.collectors = collectors if collectors is not None else self._default_collectors()

    def _default_collectors(self) -> list:
        collectors = []
        if self.config.sreality.enabled:
            collectors.append(SrealityCollector(self.config, self.http))
        if self.config.file_source.enabled and self.config.file_source.path is not None:
            collectors.append(FileCollector(self.config.file_source.path))
        return collectors

    def collect(self) -> list[Listing]:
        listings: list[Listing] = []
        seen: set[str] = set()
        for collector in self.collectors:
            for listing in collector.collect():
                if listing.key in seen:
                    continue
                seen.add(listing.key)
                listings.append(listing)
        return listings

    def run(self, *, report_dir: Path | None = None, now: datetime | None = None) -> RunResult:
        first_run = self.store.is_first_run()
        fetched = self.collect()
        matching = [item for item in fetched if matches_filters(item, self.config.filters)]
        known = self.store.known_keys()
        if first_run and self.config.filters.first_run == "mark_seen_only":
            for listing in matching:
                self.store.upsert_listing(listing)
            self.store.mark_initialized()
            markdown = render_markdown([])
            return RunResult(
                fetched=len(fetched),
                matching=len(matching),
                new=0,
                scored=[],
                report_path=None,
                first_run=True,
                markdown=markdown,
            )

        to_score: list[Listing] = []
        for listing in matching:
            is_new = listing.key not in known
            self.store.upsert_listing(listing)
            if first_run or is_new:
                to_score.append(listing)

        scored = [self.scorer.score(listing, now=now) for listing in to_score]
        for item in scored:
            self.store.save_score(item.listing.key, item.to_dict())
        self.store.mark_initialized()

        markdown = render_markdown(scored)
        report_path = None
        if report_dir is not None:
            stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
            report_path = write_report(scored, Path(report_dir) / f"watch-{stamp}.md")

        if scored and self.config.notify.telegram_bot_token:
            try:
                send_telegram(self.config.notify, telegram_text(scored), self.config.http.user_agent)
            except Exception as exc:
                markdown += f"\n\n_Telegram notify failed: {exc}_\n"

        return RunResult(
            fetched=len(fetched),
            matching=len(matching),
            new=len(scored),
            scored=scored,
            report_path=report_path,
            first_run=first_run,
            markdown=markdown,
        )
