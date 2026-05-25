from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlmodel import Session

from stow.db import engine

logger = logging.getLogger(__name__)


def run_migrations(session: Session) -> None:
    """Apply lightweight schema patches not handled by create_all on existing DBs."""
    inspector = inspect(engine)
    if inspector.has_table("merchant_rule"):
        columns = {col["name"] for col in inspector.get_columns("merchant_rule")}
        if "tags" not in columns:
            session.execute(text("ALTER TABLE merchant_rule ADD COLUMN tags JSON"))
            session.commit()
            logger.info("Added merchant_rule.tags column")
