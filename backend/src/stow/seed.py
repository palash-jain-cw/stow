from sqlmodel import Session, select
from stow.models import AccountGroup

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
]


def seed_account_groups(session: Session) -> None:
    existing = {g.name: g for g in session.exec(select(AccountGroup)).all()}

    # Two passes: roots first, then children (single level of nesting is enough
    # since the hierarchy is at most 2 levels deep in seed data)
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
        session.flush()  # get id before next iteration needs it as parent
        existing[name] = group

    session.commit()
