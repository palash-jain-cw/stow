#!/usr/bin/env python3
"""One-time repair: reassign transactions to the FY matching their date."""

from __future__ import annotations

import argparse
import logging
import sys

from sqlmodel import Session, create_engine

from stow.fy_repair import repair_fy_assignments

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair FY assignments for all transactions")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to the database",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Database URL (defaults to DATABASE_URL env var)",
    )
    args = parser.parse_args()

    import os

    url = args.database_url or os.environ.get("DATABASE_URL")
    if not url:
        logger.error("DATABASE_URL is required")
        return 1

    engine = create_engine(url)
    with Session(engine) as session:
        summary = repair_fy_assignments(session, dry_run=args.dry_run)

    logger.info(
        "Repair complete dry_run=%s moved=%s skipped=%s fys_created=%s",
        summary.dry_run,
        summary.moved,
        len(summary.skipped_locked),
        len(summary.fys_created),
    )
    if summary.skipped_locked:
        for skip in summary.skipped_locked[:20]:
            logger.warning("Skipped txn %s: %s", skip.txn_id, skip.reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
