from __future__ import annotations

import fnmatch
from datetime import timedelta, date as date_type

from sqlmodel import Session, select

from stow.models import Entry, ImportBatch, MerchantRule, StagingRow, Transaction


def match_merchant_rule(session: Session, description: str) -> int | None:
    """Return account_id of the first matching merchant rule, or None."""
    rules = session.exec(select(MerchantRule)).all()
    desc_lower = description.lower()
    for rule in rules:
        if fnmatch.fnmatch(desc_lower, rule.pattern.lower()):
            return rule.account_id
    return None


def detect_duplicates(session: Session, batch_id: int) -> None:
    """Flag staging rows where amount+date matches a posted Entry within ±1 day."""
    rows = session.exec(
        select(StagingRow).where(StagingRow.batch_id == batch_id)
    ).all()

    for row in rows:
        window_start = row.date - timedelta(days=1)
        window_end = row.date + timedelta(days=1)

        match = session.exec(
            select(Entry)
            .join(Transaction, Entry.transaction_id == Transaction.id)
            .where(Entry.amount == row.amount)
            .where(Transaction.date >= window_start)
            .where(Transaction.date <= window_end)
        ).first()

        if match:
            row.possible_duplicate = True
            session.add(row)

    session.commit()


def confirm_batch(session: Session, batch_id: int, bank_account_id: int, fy_id: int) -> int:
    """Post all confirmed staging rows as Transactions. Returns count of posted rows."""
    rows = session.exec(
        select(StagingRow).where(
            StagingRow.batch_id == batch_id,
            StagingRow.status == "confirmed",
        )
    ).all()

    existing_numbers = {
        t.number for t in session.exec(select(Transaction)).all()
    }

    posted = 0
    for row in rows:
        amount = abs(row.amount)
        is_debit = row.amount < 0
        narration = row.narration_override or row.description

        # Generate a unique transaction number
        base = f"IMP-{row.date.strftime('%Y%m%d')}-{row.id}"
        number = base
        suffix = 1
        while number in existing_numbers:
            number = f"{base}-{suffix}"
            suffix += 1
        existing_numbers.add(number)

        txn = Transaction(
            number=number,
            type="payment" if is_debit else "receipt",
            date=row.date,
            narration=narration,
            fy_id=fy_id,
            tags=row.tags,
        )
        session.add(txn)
        session.commit()
        session.refresh(txn)

        if is_debit:
            debit_account = row.suggested_account_id or bank_account_id
            session.add(Entry(transaction_id=txn.id, account_id=debit_account, amount=amount))
            session.add(Entry(transaction_id=txn.id, account_id=bank_account_id, amount=-amount))
        else:
            session.add(Entry(transaction_id=txn.id, account_id=bank_account_id, amount=amount))
            credit_account = row.suggested_account_id or bank_account_id
            session.add(Entry(transaction_id=txn.id, account_id=credit_account, amount=-amount))

        row.status = "reconciled"
        session.add(row)
        posted += 1

    batch = session.get(ImportBatch, batch_id)
    if batch:
        batch.status = "posted"
        batch.bank_account_id = bank_account_id
        session.add(batch)

    session.commit()
    return posted


def map_accounts(session: Session, batch_id: int) -> None:
    """Apply merchant rules to staging rows, overriding any existing suggestion."""
    rows = session.exec(
        select(StagingRow).where(StagingRow.batch_id == batch_id)
    ).all()

    for row in rows:
        rule_account_id = match_merchant_rule(session, row.description)
        if rule_account_id is not None:
            row.suggested_account_id = rule_account_id
            session.add(row)

    session.commit()
