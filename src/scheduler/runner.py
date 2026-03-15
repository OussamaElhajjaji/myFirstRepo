"""
Scheduler: run the pipeline at configured times each day.

Usage:
    python -m src.scheduler.runner
    python -m src.scheduler.runner --once          # run once immediately
    python -m src.scheduler.runner --dry-run       # skip posting
    python -m src.scheduler.runner --topic "stoicism quotes"
"""

import argparse
import logging
import random
import time
from datetime import datetime

import schedule

from config.settings import NICHE_TOPICS, POST_TIMES
from src.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/funnel.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def _job(topic: str | None = None, dry_run: bool = False) -> None:
    t = topic or random.choice(NICHE_TOPICS)
    logger.info("Scheduled job fired | topic=%s | dry_run=%s", t, dry_run)
    try:
        result = run_pipeline(topic=t, dry_run=dry_run)
        logger.info("Job done | success=%s | video=%s", result["success"], result.get("video_path"))
    except Exception as exc:
        logger.exception("Job raised an unhandled exception: %s", exc)


def start_scheduler(dry_run: bool = False, topic: str | None = None) -> None:
    """Register jobs at each configured post time and block forever."""
    for t in POST_TIMES:
        schedule.every().day.at(t).do(_job, topic=topic, dry_run=dry_run)
        logger.info("Scheduled post at %s", t)

    logger.info("Scheduler running. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(30)


def main() -> None:
    parser = argparse.ArgumentParser(description="Social Media Video Funnel Scheduler")
    parser.add_argument("--once", action="store_true", help="Run pipeline once immediately and exit")
    parser.add_argument("--dry-run", action="store_true", help="Build video but skip posting")
    parser.add_argument("--topic", type=str, default=None, help="Override topic (default: random)")
    args = parser.parse_args()

    if args.once:
        _job(topic=args.topic, dry_run=args.dry_run)
    else:
        start_scheduler(dry_run=args.dry_run, topic=args.topic)


if __name__ == "__main__":
    main()
