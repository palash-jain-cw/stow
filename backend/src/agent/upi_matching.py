"""Deterministic account matching for UPI/payment screenshots."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _contains(haystack: str, needle: str) -> bool:
    h, n = haystack.lower(), needle.lower()
    return n in h or h in n


def _bank_accounts(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        a
        for a in accounts
        if a.get("nature") == "asset"
        and (
            "bank" in (a.get("group_name") or "").lower()
            or "cash" in (a.get("group_name") or "").lower()
        )
    ]


def match_payee_account(
    accounts: list[dict[str, Any]],
    merchant_rules: list[dict[str, Any]],
    payee_name: str,
) -> dict[str, Any] | None:
    """Match payee from screenshot to an expense account via rules then name."""
    if not payee_name.strip():
        return None

    payee_lower = payee_name.lower()
    for rule in merchant_rules:
        pattern = (rule.get("pattern") or "").lower()
        if pattern and pattern in payee_lower:
            matched = next((a for a in accounts if a["id"] == rule["account_id"]), None)
            if matched:
                logger.info("Payee matched via merchant rule %r -> account %s", pattern, matched["name"])
                return matched

    expense_accounts = [a for a in accounts if a.get("nature") == "expense"]
    for acc in expense_accounts:
        name = acc.get("name") or ""
        if _contains(payee_lower, name):
            logger.info("Payee matched via expense account name %s", name)
            return acc

    # First token of payee name vs account name (e.g. "Pankhuri" in "Pankhuri Jain")
    first_token = payee_lower.split()[0] if payee_lower.split() else ""
    if len(first_token) >= 4:
        for acc in expense_accounts:
            if first_token in (acc.get("name") or "").lower():
                logger.info("Payee matched via first token %r -> %s", first_token, acc["name"])
                return acc

    return None


def match_source_bank_account(
    accounts: list[dict[str, Any]],
    source_bank_name: str | None = None,
    source_account_last4: str | None = None,
) -> dict[str, Any] | None:
    """Match debited-from bank on screenshot to a ledger bank account."""
    banks = _bank_accounts(accounts)
    if not banks:
        return None

    if source_bank_name and source_bank_name.strip():
        bank_lower = source_bank_name.lower()
        for acc in banks:
            name = (acc.get("name") or "").lower()
            if bank_lower in name or name in bank_lower:
                logger.info("Source bank matched via name %r -> %s", source_bank_name, acc["name"])
                return acc
        # Bank brand only: "Axis Bank" -> account containing "axis"
        for token in bank_lower.replace("bank", "").split():
            if len(token) < 3:
                continue
            for acc in banks:
                if token in (acc.get("name") or "").lower():
                    logger.info("Source bank matched via token %r -> %s", token, acc["name"])
                    return acc

    if source_account_last4 and source_account_last4.strip():
        last4 = source_account_last4.strip()
        for acc in banks:
            if last4 in (acc.get("name") or ""):
                logger.info("Source bank matched via last4 %s -> %s", last4, acc["name"])
                return acc

    return None


def resolve_upi_accounts(
    accounts: list[dict[str, Any]],
    merchant_rules: list[dict[str, Any]],
    *,
    payee_name: str,
    source_bank_name: str | None = None,
    source_account_last4: str | None = None,
) -> dict[str, Any]:
    """Return matched from/to accounts and whether both sides are resolved."""
    payee = match_payee_account(accounts, merchant_rules, payee_name)
    source = match_source_bank_account(accounts, source_bank_name, source_account_last4)
    return {
        "from_account": source,
        "to_account": payee,
        "from_resolved": source is not None,
        "to_resolved": payee is not None,
        "fully_resolved": source is not None and payee is not None,
    }
