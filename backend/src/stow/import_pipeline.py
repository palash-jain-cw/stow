from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from sqlmodel import Session, select

from stow.fy_resolution import FyResolutionError, resolve_fy_for_posting
from stow.models import Entry, ImportBatch, MerchantRule, StagingRow, Transaction

logger = logging.getLogger(__name__)

BANK_GROUPS = {"Bank Accounts", "Cash-in-Hand"}


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


@dataclass
class ConfirmBatchResult:
    posted_count: int = 0
    skipped_count: int = 0
    skipped: list[dict[str, str | int]] = field(default_factory=list)


def match_bank_account(accounts: list[dict], detected_bank: str | None) -> dict | None:
    """Match parsed bank name to a ledger bank/cash account."""
    if not detected_bank:
        return None
    bank_accounts = [
        a for a in accounts
        if a.get("group_name") in BANK_GROUPS and not a.get("is_archived")
    ]
    detected = detected_bank.lower()
    for account in bank_accounts:
        name = account["name"].lower()
        if name in detected or detected in name:
            return account
    for token in detected.replace("-", " ").split():
        if len(token) < 4:
            continue
        for account in bank_accounts:
            if token in account["name"].lower():
                return account
    return None


def confirm_batch(
    session: Session,
    batch_id: int,
    bank_account_id: int,
    fy_id: int | None = None,
) -> ConfirmBatchResult:
    """Post confirmed staging rows as transactions. Skips unmapped or invalid rows."""
    rows = session.exec(
        select(StagingRow).where(
            StagingRow.batch_id == batch_id,
            StagingRow.status == "confirmed",
        )
    ).all()

    existing_numbers = {
        t.number for t in session.exec(select(Transaction)).all()
    }

    result = ConfirmBatchResult()
    for row in rows:
        if row.suggested_account_id is None:
            result.skipped_count += 1
            result.skipped.append({
                "row_id": row.id or 0,
                "reason": "no account mapped — assign an expense/income account before posting",
            })
            logger.warning("Skipping import row id=%s: no suggested_account_id", row.id)
            continue

        amount = abs(row.amount)
        is_debit = row.amount < 0
        narration = row.narration_override or row.description

        try:
            fy, _ = resolve_fy_for_posting(session, row.date, fy_id)
        except FyResolutionError as exc:
            result.skipped_count += 1
            result.skipped.append({"row_id": row.id or 0, "reason": exc.detail})
            logger.warning(
                "Skipping import row id=%s on %s: %s",
                row.id,
                row.date,
                exc.detail,
            )
            continue

        if fy.status == "open":
            fy.status = "active"

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
            fy_id=fy.id,
            tags=row.tags,
        )
        session.add(txn)
        session.flush()
        assert txn.id is not None

        if is_debit:
            session.add(Entry(
                transaction_id=txn.id,
                account_id=row.suggested_account_id,
                amount=amount,
            ))
            session.add(Entry(
                transaction_id=txn.id,
                account_id=bank_account_id,
                amount=-amount,
            ))
        else:
            session.add(Entry(
                transaction_id=txn.id,
                account_id=bank_account_id,
                amount=amount,
            ))
            session.add(Entry(
                transaction_id=txn.id,
                account_id=row.suggested_account_id,
                amount=-amount,
            ))

        row.status = "reconciled"
        session.add(row)
        result.posted_count += 1

    batch = session.get(ImportBatch, batch_id)
    if batch:
        batch.status = "posted" if result.posted_count else batch.status
        batch.bank_account_id = bank_account_id
        session.add(batch)

    session.commit()
    return result


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
