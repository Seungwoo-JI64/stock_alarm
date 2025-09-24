from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from zoneinfo import ZoneInfo

try:  # optional dependency for local development
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional
    load_dotenv = None

from .config import Settings
from .supabase_client import upload_snapshots
from .volume_fetcher import fetch_snapshots, load_tickers

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch US stock volumes and store in Supabase.")
    parser.add_argument(
        "--tickers-file",
        default=None,
        help="Optional override for tickers CSV file.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N tickers (for testing).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data but do not upload to Supabase.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        stream=sys.stdout,
    )


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    if load_dotenv is not None:
        load_dotenv()

    settings = Settings.load()
    if args.tickers_file:
        settings = replace(settings, tickers_file=args.tickers_file)

    logger.info("Starting volume snapshot run")

    if args.limit is not None:
        tickers = load_tickers(settings.tickers_file)[: args.limit]
        logger.info("Limiting run to %d tickers", len(tickers))
    else:
        tickers = None

    snapshots = fetch_snapshots(settings, tickers_override=tickers)

    if not snapshots:
        logger.warning("No snapshots produced; aborting.")
        return

    fetched_at_utc = datetime.now(timezone.utc)
    fetched_at_kst = fetched_at_utc.astimezone(ZoneInfo("Asia/Seoul"))
    batch_id = uuid4()

    logger.info(
        "Prepared %d snapshots (batch_id=%s)",
        len(snapshots),
        batch_id,
    )

    if args.dry_run:
        preview = [snapshots[i] for i in range(min(5, len(snapshots)))]
        logger.info("Dry run enabled; skipping upload. Preview:")
        for record in preview:
            logger.info("%s", json.dumps(record.__dict__, default=str))
        return

    upload_snapshots(
        settings=settings,
        batch_id=batch_id,
        snapshots=snapshots,
        fetched_at_utc=fetched_at_utc,
        fetched_at_kst=fetched_at_kst,
    )
    logger.info("Upload complete.")


if __name__ == "__main__":
    main()
