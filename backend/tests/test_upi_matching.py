"""Unit tests for UPI screenshot account matching."""
from agent.upi_matching import match_payee_account, match_source_bank_account, resolve_upi_accounts

ACCOUNTS = [
    {"id": 1, "name": "HDFC Savings", "nature": "asset", "group_name": "Bank Accounts"},
    {"id": 2, "name": "Axis Bank", "nature": "asset", "group_name": "Bank Accounts"},
    {"id": 3, "name": "Food & Dining", "nature": "expense", "group_name": "Indirect Expenses"},
    {"id": 4, "name": "Pankhuri Jain", "nature": "expense", "group_name": "Indirect Expenses"},
]

RULES = [
    {"pattern": "zomato", "account_id": 3},
    {"pattern": "pankhuri", "account_id": 4},
]


def test_match_source_bank_by_name():
    matched = match_source_bank_account(ACCOUNTS, source_bank_name="Axis Bank")
    assert matched is not None
    assert matched["id"] == 2


def test_match_payee_via_merchant_rule():
    matched = match_payee_account(ACCOUNTS, RULES, "PANKHURI JAIN")
    assert matched is not None
    assert matched["id"] == 4


def test_resolve_upi_accounts_fully_resolved():
    result = resolve_upi_accounts(
        ACCOUNTS,
        RULES,
        payee_name="Pankhuri Jain",
        source_bank_name="Axis Bank",
        source_account_last4="744783",
    )
    assert result["fully_resolved"] is True
    assert result["from_account"]["name"] == "Axis Bank"
    assert result["to_account"]["name"] == "Pankhuri Jain"
