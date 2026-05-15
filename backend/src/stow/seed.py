from datetime import date

from sqlmodel import Session, col, select
from stow.models import Account, AccountGroup, CapitalGainsTaxRule

# (name, nature, cash_flow_tag, sort_order, parent_name)
_GROUPS: list[tuple[str, str, str | None, int, str | None]] = [
    # Balance Sheet roots
    ("Capital Account",      "equity",     "financing",  10,  None),
    ("Loans (Liability)",    "liability",  "financing",  20,  None),
    ("Current Liabilities",  "liability",  "operating",  30,  None),
    ("Fixed Assets",         "asset",      "investing",  40,  None),
    ("Investments",          "asset",      "investing",  50,  None),
    ("Current Assets",       "asset",      "operating",  60,  None),
    # P&L roots
    ("Income",               "income",     None,         70,  None),
    ("Expenses",             "expense",    None,         80,  None),
    # Capital Account children
    ("Capital",                    "equity",    "financing",  11, "Capital Account"),
    ("Reserves & Surplus",         "equity",    "financing",  12, "Capital Account"),
    # Loans children
    ("Bank OD Accounts",           "liability", "financing",  21, "Loans (Liability)"),
    ("Secured Loans",              "liability", "financing",  22, "Loans (Liability)"),
    ("Unsecured Loans",            "liability", "financing",  23, "Loans (Liability)"),
    # Current Liabilities children
    ("Duties & Taxes",             "liability", "operating",  31, "Current Liabilities"),
    ("Credit Cards",               "liability", "operating",  32, "Current Liabilities"),
    ("Sundry Creditors",           "liability", "operating",  33, "Current Liabilities"),
    ("Provisions",                 "liability", "operating",  34, "Current Liabilities"),
    # Fixed Assets children
    ("Accumulated Depreciation",   "asset",     "investing",  41, "Fixed Assets"),
    # Current Assets children
    ("Bank Accounts",              "asset",     "operating",  61, "Current Assets"),
    ("Cash-in-Hand",               "asset",     "operating",  62, "Current Assets"),
    ("Sundry Debtors",             "asset",     "operating",  63, "Current Assets"),
    # Income children
    ("Direct Income",              "income",    None,         71, "Income"),
    ("Indirect Income",            "income",    None,         72, "Income"),
    # Expenses children
    ("Direct Expenses",            "expense",   None,         81, "Expenses"),
    ("Indirect Expenses",          "expense",   None,         82, "Expenses"),
    # GST accounts under Duties & Taxes
    ("Input CGST",                 "asset",     "operating",  311, "Duties & Taxes"),
    ("Input SGST",                 "asset",     "operating",  312, "Duties & Taxes"),
    ("Input IGST",                 "asset",     "operating",  313, "Duties & Taxes"),
    ("Output CGST",                "liability", "operating",  314, "Duties & Taxes"),
    ("Output SGST",                "liability", "operating",  315, "Duties & Taxes"),
    ("Output IGST",                "liability", "operating",  316, "Duties & Taxes"),
    # TDS accounts under Duties & Taxes
    ("TDS Receivable",             "asset",     "operating",  317, "Duties & Taxes"),
    ("TDS Payable",                "liability", "operating",  318, "Duties & Taxes"),
    # Capital Gains — under Income
    ("Capital Gains",              "income",    None,          73, "Income"),
]

# (name, group_name)
_CAPITAL_GAINS_ACCOUNTS: list[tuple[str, str]] = [
    ("Short Term Capital Gains",        "Capital Gains"),
    ("Long Term Capital Gains",         "Capital Gains"),
    ("Capital Loss",                    "Capital Gains"),
    ("Fixed Deposit Interest Income",   "Indirect Income"),
    ("Depreciation",                    "Indirect Expenses"),
]

# Versioned equity CGT rules — add a new row when the budget changes; never edit old rows.
# Rates in basis points; amounts in paise.
_TAX_RULES: list[tuple[str, int, int, int, int, date]] = [
    # (asset_type, holding_threshold_days, stcg_bps, ltcg_bps, ltcg_exemption_paise, effective_from)
    # Pre-2024 budget (LTCG reintroduced Feb 2018)
    ("equity", 365, 1500, 1000, 10_000_000, date(2018, 2, 1)),
    # Union Budget 2024 (effective 23 Jul 2024)
    ("equity", 365, 2000, 1250, 12_500_000, date(2024, 7, 23)),
]


def seed_account_groups(session: Session) -> None:
    existing = {g.name: g for g in session.exec(select(AccountGroup)).all()}

    for name, nature, cash_flow_tag, sort_order, parent_name in _GROUPS:
        if name in existing:
            continue
        parent_id = existing[parent_name].id if parent_name else None
        group = AccountGroup(
            name=name,
            nature=nature,
            cash_flow_tag=cash_flow_tag,
            sort_order=sort_order,
            parent_id=parent_id,
        )
        session.add(group)
        session.flush()
        existing[name] = group

    # Capital Gains accounts
    existing_accounts = {a.name for a in session.exec(select(Account)).all()}
    for acct_name, group_name in _CAPITAL_GAINS_ACCOUNTS:
        if acct_name in existing_accounts:
            continue
        group = existing[group_name]
        session.add(Account(name=acct_name, group_id=group.id or 0))

    # Versioned tax rules — insert only if that effective_from date is not already present
    existing_rules = {
        (r.asset_type, r.effective_from)
        for r in session.exec(select(CapitalGainsTaxRule)).all()
    }
    for asset_type, threshold, stcg_bps, ltcg_bps, exemption, eff_from in _TAX_RULES:
        if (asset_type, eff_from) in existing_rules:
            continue
        session.add(CapitalGainsTaxRule(
            asset_type=asset_type,
            holding_threshold_days=threshold,
            stcg_rate_bps=stcg_bps,
            ltcg_rate_bps=ltcg_bps,
            ltcg_exemption_paise=exemption,
            effective_from=eff_from,
        ))

    session.commit()
