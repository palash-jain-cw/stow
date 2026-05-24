from __future__ import annotations

from sqlmodel import Session, select

from stow.models import FinancialYear, Transaction

_TYPE_ABBR = {
    "payment": "PAY",
    "receipt": "REC",
    "journal": "JRN",
    "contra": "CTR",
}


def next_transaction_number(session: Session, fy: FinancialYear, txn_type: str) -> str:
    abbr = _TYPE_ABBR[txn_type]
    fy_year = fy.start_date.year
    existing = session.exec(
        select(Transaction).where(
            Transaction.fy_id == fy.id,
            Transaction.type == txn_type,
        )
    ).all()
    seq = len(existing) + 1
    return f"{abbr}-{fy_year}-{seq:03d}"
