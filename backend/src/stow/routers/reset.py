from fastapi import APIRouter
from sqlalchemy import text
from sqlmodel import Session

from stow.db import engine
from stow.seed import seed_account_groups

router = APIRouter(tags=["reset"])

_TABLES = ",".join([
    "recurring_queue_item",
    "recurring_schedule",
    "staging_row",
    "import_batch",
    "capital_gain_entry",
    "lot",
    "price_quote",
    "fd_metadata",
    "transaction_audit_log",
    "entry",
    "opening_balance",
    "transaction",
    "financial_year",
    "merchant_rule",
    "telegram_user",
    "account",
    "account_group",
    "capital_gains_tax_rule",
])


@router.post("/reset")
def reset_app():
    with Session(engine) as session:
        session.execute(text(f"TRUNCATE TABLE {_TABLES} RESTART IDENTITY CASCADE"))
        session.commit()
        seed_account_groups(session)
    return {"ok": True}
