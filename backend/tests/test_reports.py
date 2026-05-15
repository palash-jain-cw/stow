import pytest


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def fy(client):
    return client.post("/financial-years", json={
        "start_date": "2025-04-01",
        "end_date": "2026-03-31",
    }).json()


@pytest.fixture()
def chart(client):
    """Minimal chart of accounts: one bank account (asset) + one expense."""
    asset_grp = client.post("/account-groups", json={"name": "Bank Accounts", "nature": "asset"}).json()
    exp_grp   = client.post("/account-groups", json={"name": "Indirect Expenses", "nature": "expense"}).json()
    inc_grp   = client.post("/account-groups", json={"name": "Direct Income", "nature": "income"}).json()
    bank      = client.post("/accounts", json={"name": "HDFC Bank", "group_id": asset_grp["id"]}).json()
    expense   = client.post("/accounts", json={"name": "Office Supplies", "group_id": exp_grp["id"]}).json()
    income    = client.post("/accounts", json={"name": "Consulting Income", "group_id": inc_grp["id"]}).json()
    return {"bank": bank, "expense": expense, "income": income,
            "asset_grp": asset_grp, "exp_grp": exp_grp, "inc_grp": inc_grp}


# ── Slice 1: trial balance ────────────────────────────────────────────────────

def test_trial_balance_with_opening_and_movements(client, fy, chart):
    bank_id    = chart["bank"]["id"]
    expense_id = chart["expense"]["id"]

    # opening balance: bank 50,000 paise (Dr)
    client.put(f"/accounts/{bank_id}/opening-balance",
               json={"fy_id": fy["id"], "amount": 50_000})

    # one payment: bank pays 10,000 paise for office supplies
    client.post("/transactions", json={
        "type": "payment",
        "date": "2025-06-01",
        "narration": "Office supplies",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": expense_id, "amount": 10_000},
            {"account_id": bank_id,    "amount": -10_000},
        ],
    })

    resp = client.get(f"/reports/trial-balance?fy_id={fy['id']}")
    assert resp.status_code == 200
    data = resp.json()

    rows = {r["account_name"]: r for r in data["rows"]}

    bank_row = rows["HDFC Bank"]
    assert bank_row["opening_balance"] == 50_000
    assert bank_row["debit"]           == 0
    assert bank_row["credit"]          == 10_000
    assert bank_row["closing_balance"] == 40_000

    exp_row = rows["Office Supplies"]
    assert exp_row["opening_balance"] == 0
    assert exp_row["debit"]           == 10_000
    assert exp_row["credit"]          == 0
    assert exp_row["closing_balance"] == 10_000


# ── Slice 2: profit & loss ────────────────────────────────────────────────────

def test_profit_loss_income_expense_and_net_profit(client, fy, chart):
    bank_id    = chart["bank"]["id"]
    expense_id = chart["expense"]["id"]
    income_id  = chart["income"]["id"]

    # receipt: 1,00,000 paise consulting income
    client.post("/transactions", json={
        "type": "receipt",
        "date": "2025-05-01",
        "narration": "Client invoice",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": bank_id,   "amount": 100_000},
            {"account_id": income_id, "amount": -100_000},
        ],
    })

    # payment: 30,000 paise office supplies
    client.post("/transactions", json={
        "type": "payment",
        "date": "2025-06-01",
        "narration": "Office supplies",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": expense_id, "amount": 30_000},
            {"account_id": bank_id,    "amount": -30_000},
        ],
    })

    resp = client.get(f"/reports/profit-loss?fy_id={fy['id']}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_income"]   == 100_000
    assert data["total_expenses"] == 30_000
    assert data["net_profit"]     == 70_000

    income_groups  = {g["group_name"]: g for g in data["income_groups"]}
    expense_groups = {g["group_name"]: g for g in data["expense_groups"]}

    assert "Direct Income"       in income_groups
    assert "Indirect Expenses"   in expense_groups
    assert income_groups["Direct Income"]["subtotal"]     == 100_000
    assert expense_groups["Indirect Expenses"]["subtotal"] == 30_000


def test_profit_loss_zero_when_no_transactions(client, fy, chart):
    data = client.get(f"/reports/profit-loss?fy_id={fy['id']}").json()
    assert data["net_profit"]     == 0
    assert data["total_income"]   == 0
    assert data["total_expenses"] == 0


# ── Slice 4: cash flow ───────────────────────────────────────────────────────

@pytest.fixture()
def cash_flow_chart(client):
    """Chart with cash_flow_tag set so the cash flow report can categorise movements."""
    bank_grp    = client.post("/account-groups", json={"name": "Bank Accounts",      "nature": "asset",   "cash_flow_tag": "operating"}).json()
    fa_grp      = client.post("/account-groups", json={"name": "Fixed Assets",       "nature": "asset",   "cash_flow_tag": "investing"}).json()
    loan_grp    = client.post("/account-groups", json={"name": "Loans",              "nature": "liability","cash_flow_tag": "financing"}).json()
    exp_grp     = client.post("/account-groups", json={"name": "Indirect Expenses",  "nature": "expense"}).json()
    inc_grp     = client.post("/account-groups", json={"name": "Direct Income",      "nature": "income"}).json()

    bank    = client.post("/accounts", json={"name": "HDFC Bank",          "group_id": bank_grp["id"]}).json()
    asset   = client.post("/accounts", json={"name": "Laptop",             "group_id": fa_grp["id"]}).json()
    loan    = client.post("/accounts", json={"name": "Personal Loan",      "group_id": loan_grp["id"]}).json()
    expense = client.post("/accounts", json={"name": "Office Supplies",    "group_id": exp_grp["id"]}).json()
    income  = client.post("/accounts", json={"name": "Consulting Income",  "group_id": inc_grp["id"]}).json()
    return {"bank": bank, "asset": asset, "loan": loan, "expense": expense, "income": income}


def test_cash_flow_sections_and_reconciliation(client, fy, cash_flow_chart):
    c = cash_flow_chart
    bank_id    = c["bank"]["id"]
    asset_id   = c["asset"]["id"]
    loan_id    = c["loan"]["id"]
    expense_id = c["expense"]["id"]
    income_id  = c["income"]["id"]

    # opening cash
    client.put(f"/accounts/{bank_id}/opening-balance",
               json={"fy_id": fy["id"], "amount": 100_000})

    # receipt: 2,00,000 consulting income  (operating inflow via net profit)
    client.post("/transactions", json={
        "type": "receipt", "date": "2025-05-01", "narration": "Invoice",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": bank_id,   "amount": 200_000},
            {"account_id": income_id, "amount": -200_000},
        ],
    })

    # payment: 50,000 expenses  (operating outflow via net profit)
    client.post("/transactions", json={
        "type": "payment", "date": "2025-06-01", "narration": "Rent",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": expense_id, "amount": 50_000},
            {"account_id": bank_id,    "amount": -50_000},
        ],
    })

    # purchase laptop: 80,000 cash  (investing outflow)
    client.post("/transactions", json={
        "type": "payment", "date": "2025-07-01", "narration": "Laptop purchase",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": asset_id, "amount":  80_000},
            {"account_id": bank_id,  "amount": -80_000},
        ],
    })

    # loan received: 50,000 into bank  (financing inflow)
    client.post("/transactions", json={
        "type": "receipt", "date": "2025-08-01", "narration": "Loan disbursement",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": bank_id, "amount":  50_000},
            {"account_id": loan_id, "amount": -50_000},
        ],
    })

    resp = client.get(f"/reports/cash-flow?fy_id={fy['id']}")
    assert resp.status_code == 200
    data = resp.json()

    sections = {s["tag"]: s for s in data["sections"]}
    assert set(sections) == {"operating", "investing", "financing"}

    # Net profit = 2,00,000 - 50,000 = 1,50,000 (part of operating)
    assert data["net_profit"] == 150_000

    # Laptop purchase is an investing outflow: asset increased by 80,000 → CF = -80,000
    assert sections["investing"]["subtotal"] == -80_000

    # Loan received is a financing inflow: liability increased by -50,000 (Cr) → CF = +50,000
    assert sections["financing"]["subtotal"] == 50_000

    # Closing cash = opening + net_change
    assert data["opening_cash"] == 100_000
    assert data["closing_cash"] == data["opening_cash"] + data["net_change_in_cash"]

    # Verify closing cash matches actual bank closing balance
    bank_closing = 100_000 + 200_000 - 50_000 - 80_000 + 50_000  # = 220,000
    assert data["closing_cash"] == bank_closing


# ── Slice 5: PDF export ───────────────────────────────────────────────────────

def test_trial_balance_pdf_returns_pdf_bytes(client, fy, chart):
    bank_id    = chart["bank"]["id"]
    expense_id = chart["expense"]["id"]
    client.post("/transactions", json={
        "type": "payment", "date": "2025-05-01", "narration": "Stationery",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": expense_id, "amount": 5_000},
            {"account_id": bank_id,    "amount": -5_000},
        ],
    })
    resp = client.get(f"/reports/trial-balance?fy_id={fy['id']}&format=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_profit_loss_pdf(client, fy, chart):
    resp = client.get(f"/reports/profit-loss?fy_id={fy['id']}&format=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_balance_sheet_pdf(client, fy, chart):
    resp = client.get(f"/reports/balance-sheet?fy_id={fy['id']}&format=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_cash_flow_pdf(client, fy, cash_flow_chart):
    resp = client.get(f"/reports/cash-flow?fy_id={fy['id']}&format=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


# ── Slice 3: balance sheet ────────────────────────────────────────────────────

def test_balance_sheet_accounting_equation(client, fy, chart):
    bank_id    = chart["bank"]["id"]
    income_id  = chart["income"]["id"]
    expense_id = chart["expense"]["id"]

    # opening equity: capital introduced via bank (manual opening balance)
    client.put(f"/accounts/{bank_id}/opening-balance",
               json={"fy_id": fy["id"], "amount": 200_000})

    # receipt: 1,50,000 consulting income
    client.post("/transactions", json={
        "type": "receipt",
        "date": "2025-05-01",
        "narration": "Invoice payment",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": bank_id,   "amount": 150_000},
            {"account_id": income_id, "amount": -150_000},
        ],
    })

    # payment: 40,000 expenses
    client.post("/transactions", json={
        "type": "payment",
        "date": "2025-06-01",
        "narration": "Rent",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": expense_id, "amount": 40_000},
            {"account_id": bank_id,    "amount": -40_000},
        ],
    })

    resp = client.get(f"/reports/balance-sheet?fy_id={fy['id']}")
    assert resp.status_code == 200
    data = resp.json()

    # Accounting equation must hold
    assert data["total_assets"] == data["total_liabilities_and_equity"]

    # Net profit 1,10,000 should appear in equity section
    retained = next(
        s for s in data["equity_sections"] if s["group_name"] == "Retained Earnings"
    )
    assert retained["subtotal"] == 110_000


def test_balance_sheet_no_transactions(client, fy, chart):
    data = client.get(f"/reports/balance-sheet?fy_id={fy['id']}").json()
    assert data["total_assets"] == data["total_liabilities_and_equity"]


def test_trial_balance_totals_balance(client, fy, chart):
    bank_id    = chart["bank"]["id"]
    expense_id = chart["expense"]["id"]

    client.post("/transactions", json={
        "type": "payment",
        "date": "2025-05-01",
        "narration": "Stationery",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": expense_id, "amount": 5_000},
            {"account_id": bank_id,    "amount": -5_000},
        ],
    })

    data = client.get(f"/reports/trial-balance?fy_id={fy['id']}").json()
    assert data["total_debit"] == data["total_credit"]
