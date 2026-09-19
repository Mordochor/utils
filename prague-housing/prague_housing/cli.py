from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from prague_housing.config import load_config
from prague_housing.pipeline import Pipeline


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def cmd_init(dest: Path) -> int:
    example = _package_root() / "config.example.yaml"
    if dest.exists():
        print(f"Already exists: {dest}", file=sys.stderr)
        return 1
    shutil.copyfile(example, dest)
    print(f"Wrote {dest}. Edit filters, destinations, and API keys, then run:")
    print(f"  prague-housing run --config {dest}")
    return 0


def cmd_run(config_path: Path, report_dir: Path, once: bool) -> int:
    config = load_config(config_path)
    pipeline = Pipeline(config)
    result = pipeline.run(report_dir=report_dir)
    print(
        f"fetched={result.fetched} matching={result.matching} "
        f"new={result.new} first_run={result.first_run}"
    )
    if result.report_path:
        print(f"report={result.report_path}")
    print()
    print(result.markdown)
    if not once:
        return 0
    return 0


def cmd_watch(config_path: Path, report_dir: Path) -> int:
    config = load_config(config_path)
    interval = max(5, config.schedule.interval_minutes) * 60
    pipeline = Pipeline(config)
    while True:
        result = pipeline.run(report_dir=report_dir)
        print(
            f"fetched={result.fetched} matching={result.matching} "
            f"new={result.new} first_run={result.first_run}"
        )
        if result.report_path:
            print(f"report={result.report_path}")
        print(result.markdown)
        print(f"sleeping {interval}s …")
        time.sleep(interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prague-housing",
        description="Collect Prague listings and score public-transport access.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Write config.example.yaml to a local config.yaml")
    init.add_argument("--dest", type=Path, default=Path("config.yaml"))

    run = sub.add_parser("run", help="Collect once, score new matches, write a report")
    run.add_argument("--config", type=Path, default=Path("config.yaml"))
    run.add_argument("--report-dir", type=Path, default=Path("reports"))

    watch = sub.add_parser("watch", help="Repeat run on the configured interval")
    watch.add_argument("--config", type=Path, default=Path("config.yaml"))
    watch.add_argument("--report-dir", type=Path, default=Path("reports"))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        return cmd_init(args.dest)
    if args.command == "run":
        return cmd_run(args.config, args.report_dir, once=True)
    if args.command == "watch":
        return cmd_watch(args.config, args.report_dir)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
