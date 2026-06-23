#!/usr/bin/env python3
"""Phase 3 — CLI entry point for AI-Contextualized Cold Email Outreach."""

import asyncio
import logging
import sys

from phase3_config import load_config
from phase3_pipeline import Phase3Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


def main():
    config = load_config()
    log = logging.getLogger(__name__)

    # Reset checkpoint files from a previous (possibly failed) run
    if config.reset_checkpoint:
        for path in [config.checkpoint_csv, config.checkpoint_jsonl, config.progress_json]:
            if path.exists():
                path.unlink()
                log.info("Deleted stale checkpoint: %s", path)

    log.info("Phase 3: AI-Contextualized Personalized Cold Email Outreach")
    log.info("Backend: %s | Model: %s | Concurrency: %d | Min quality: %d", config.backend, config.model, config.concurrency, config.min_quality)
    log.info("Tiers: %s | Max: %s | Dry run: %s", config.tiers, config.max_prospects or "unlimited", config.dry_run)

    pipeline = Phase3Pipeline(config)
    summary = asyncio.run(pipeline.run())

    if summary.errors > 0:
        log.warning("%d errors occurred during processing.", summary.errors)
    sys.exit(0)


if __name__ == "__main__":
    main()
