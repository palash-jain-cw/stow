from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from sqlmodel import Session, select

from stow.fy_resolution import FyResolutionError, resolve_fy_for_posting
from stow.models import Account, AccountGroup, Entry, ImportBatch, MerchantRule, StagingRow, Transaction

logger = logging.getLogger(__name__)

BANK_GROUPS = {"Bank Accounts", "Cash-in-Hand"}


MISC_EXPENSE_GROUP = "Indirect Expenses"
MISC_INCOME_GROUP = "Indirect Income"
MISC_ACCOUNT_NAME = "Miscellaneous"


def normalize_merchant_pattern(pattern: str) -> str:
    """Bare patterns match as substring; explicit * / ? use fnmatch semantics."""
    trimmed = pattern.strip()
    if not trimmed:
        return trimmed
    if "*" not in trimmed and "?" not in trimmed:
        return f"*{trimmed}*"
    return trimmed


def description_matches_pattern(description: str, pattern: str) -> bool:
    normalized = normalize_merchant_pattern(pattern)
    return bool(normalized) and fnmatch.fnmatch(description.lower(), normalized.lower())


def default_import_account_id(session: Session, amount_paise: int) -> int | None:
    """Pre-fill import rows with seeded Miscellaneous expense/income accounts."""
    group_name = MISC_EXPENSE_GROUP if amount_paise < 0 else MISC_INCOME_GROUP
    account = session.exec(
        select(Account)
        .join(AccountGroup, Account.group_id == AccountGroup.id)
        .where(AccountGroup.name == group_name)
        .where(Account.name == MISC_ACCOUNT_NAME)
    ).first()
    if account is None:
        logger.warning(
            "Default import account %r under %r not found — run seed_account_groups",
            MISC_ACCOUNT_NAME,
            group_name,
        )
        return None
    return account.id


class MerchantRuleMatch:
    """Result of matching a description against merchant rules."""

    __slots__ = ("account_id", "tags")

    def __init__(self, account_id: int, tags: list[str] | None = None) -> None:
        self.account_id = account_id
        self.tags = tags


def match_merchant_rule(session: Session, description: str) -> MerchantRuleMatch | None:
    """Return account (and optional tags) from the first matching merchant rule."""
    rules = session.exec(select(MerchantRule)).all()
    for rule in rules:
        if description_matches_pattern(description, rule.pattern):
            rule_tags = list(rule.tags) if rule.tags else None
            return MerchantRuleMatch(account_id=rule.account_id, tags=rule_tags)
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


def apply_single_rule_to_batch(
    session: Session,
    batch_id: int,
    rule_id: int,
    *,
    only_defaults: bool = True,
) -> int:
    """Apply one merchant rule to staging rows in a batch."""
    rule = session.get(MerchantRule, rule_id)
    if not rule:
        logger.warning("Merchant rule id=%s not found for batch id=%s", rule_id, batch_id)
        return 0

    rows = session.exec(
        select(StagingRow).where(StagingRow.batch_id == batch_id)
    ).all()

    updated = 0
    for row in rows:
        if row.status == "reconciled":
            continue
        default_id = default_import_account_id(session, row.amount)
        if only_defaults and row.suggested_account_id not in (None, default_id):
            continue
        if not description_matches_pattern(row.description, rule.pattern):
            continue
        row.suggested_account_id = rule.account_id
        if rule.tags:
            row.tags = list(rule.tags)
        session.add(row)
        updated += 1

    if updated:
        session.commit()
        logger.info(
            "Applied merchant rule id=%s pattern=%r to %s row(s) in batch id=%s",
            rule_id,
            rule.pattern,
            updated,
            batch_id,
        )
    return updated


def map_accounts(session: Session, batch_id: int, *, only_defaults: bool = False) -> int:
    """Apply merchant rules, then Miscellaneous defaults for unmapped rows.

    When only_defaults=True, merchant rules update only rows still on the default
    Miscellaneous account (or unmapped). Used after the user adds a rule mid-review.

    Returns the number of staging rows updated.
    """
    rows = session.exec(
        select(StagingRow).where(StagingRow.batch_id == batch_id)
    ).all()

    updated = 0
    for row in rows:
        if row.status == "reconciled":
            continue

        default_id = default_import_account_id(session, row.amount)
        rule_match = match_merchant_rule(session, row.description)

        if rule_match is not None:
            if only_defaults and row.suggested_account_id not in (None, default_id):
                continue
            row.suggested_account_id = rule_match.account_id
            if rule_match.tags:
                row.tags = rule_match.tags
            session.add(row)
            updated += 1
        elif not only_defaults and row.suggested_account_id is None and default_id is not None:
            row.suggested_account_id = default_id
            session.add(row)
            updated += 1

    if updated:
        session.commit()
    return updated
