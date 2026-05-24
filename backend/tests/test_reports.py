import uuid

import pytest

from tests.helpers import get_or_create_account, get_or_create_fy, get_or_create_group


@pytest.fixture()
def chart(client):
    """Isolated mini chart per test."""
    tag = uuid.uuid4().hex[:8]
    asset_grp = get_or_create_group(client, f"Reports Banks {tag}", "asset")
    exp_grp = get_or_create_group(client, f"Reports Expenses {tag}", "expense")
    inc_grp = get_or_create_group(client, f"Reports Income {tag}", "income")
    bank = get_or_create_account(client, f"Reports Bank {tag}", f"Reports Banks {tag}")
    expense = get_or_create_account(client, f"Reports Expense {tag}", f"Reports Expenses {tag}")
    income = get_or_create_account(client, f"Reports Income {tag}", f"Reports Income {tag}")
    return {
        "bank": bank,
        "expense": expense,
        "income": income,
        "asset_grp": asset_grp,
        "exp_grp": exp_grp,
        "inc_grp": inc_grp,
        "tag": tag,
    }


def _fy(client, start: str, end: str):
    return get_or_create_fy(client, start, end)


# ── Slice 1: trial balance ────────────────────────────────────────────────────


def test_trial_balance_with_opening_and_movements(client, chart):
    fy = _fy(client, "2040-04-01", "2041-03-31")
    bank_id = chart["bank"]["id"]
    expense_id = chart["expense"]["id"]

    client.put(f"/accounts/{bank_id}/opening-balance", json={"fy_id": fy["id"], "amount": 50_000})
    client.post("/transactions", json={
        "type": "payment",
        "date": "2040-06-01",
        "narration": "Office supplies",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": expense_id, "amount": 10_000},
            {"account_id": bank_id, "amount": -10_000},
        ],
    })

    data = client.get(f"/reports/trial-balance?fy_id={fy['id']}").json()
    rows = {r["account_name"]: r for r in data["rows"]}

    bank_row = rows[chart["bank"]["name"]]
    assert bank_row["opening_balance"] == 50_000
    assert bank_row["debit"] == 0
    assert bank_row["credit"] == 10_000
    assert bank_row["closing_balance"] == 40_000

    exp_row = rows[chart["expense"]["name"]]
    assert exp_row["opening_balance"] == 0
    assert exp_row["debit"] == 10_000
    assert exp_row["credit"] == 0
    assert exp_row["closing_balance"] == 10_000


# ── Slice 2: profit & loss ────────────────────────────────────────────────────


def test_profit_loss_income_expense_and_net_profit(client, chart):
    fy = _fy(client, "2041-04-01", "2042-03-31")
    bank_id = chart["bank"]["id"]
    expense_id = chart["expense"]["id"]
    income_id = chart["income"]["id"]

    client.post("/transactions", json={
        "type": "receipt",
        "date": "2041-05-01",
        "narration": "Client invoice",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": bank_id, "amount": 100_000},
            {"account_id": income_id, "amount": -100_000},
        ],
    })
    client.post("/transactions", json={
        "type": "payment",
        "date": "2041-06-01",
        "narration": "Office supplies",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": expense_id, "amount": 30_000},
            {"account_id": bank_id, "amount": -30_000},
        ],
    })

    data = client.get(f"/reports/profit-loss?fy_id={fy['id']}").json()
    assert data["total_income"] == 100_000
    assert data["total_expenses"] == 30_000
    assert data["net_profit"] == 70_000

    income_groups = {g["group_name"]: g for g in data["income_groups"]}
    expense_groups = {g["group_name"]: g for g in data["expense_groups"]}
    assert income_groups[chart["inc_grp"]["name"]]["subtotal"] == 100_000
    assert expense_groups[chart["exp_grp"]["name"]]["subtotal"] == 30_000


def test_profit_loss_zero_when_no_transactions(client, chart):
    fy = _fy(client, "2042-04-01", "2043-03-31")
    data = client.get(f"/reports/profit-loss?fy_id={fy['id']}").json()
    assert data["net_profit"] == 0
    assert data["total_income"] == 0
    assert data["total_expenses"] == 0


# ── Slice 4: cash flow ───────────────────────────────────────────────────────


@pytest.fixture()
def cash_flow_chart(client):
    tag = uuid.uuid4().hex[:8]
    bank_grp = get_or_create_group(
        client, f"CF Banks {tag}", "asset", cash_flow_tag="operating",
    )
    fa_grp = get_or_create_group(
        client, f"CF Fixed Assets {tag}", "asset", cash_flow_tag="investing",
    )
    loan_grp = get_or_create_group(
        client, f"CF Loans {tag}", "liability", cash_flow_tag="financing",
    )
    exp_grp = get_or_create_group(client, f"CF Expenses {tag}", "expense")
    inc_grp = get_or_create_group(client, f"CF Income {tag}", "income")

    bank = get_or_create_account(client, f"CF Bank {tag}", f"CF Banks {tag}")
    asset = get_or_create_account(client, f"CF Laptop {tag}", f"CF Fixed Assets {tag}")
    loan = get_or_create_account(client, f"CF Loan {tag}", f"CF Loans {tag}")
    expense = get_or_create_account(client, f"CF Expense {tag}", f"CF Expenses {tag}")
    income = get_or_create_account(client, f"CF Income {tag}", f"CF Income {tag}")
    return {"bank": bank, "asset": asset, "loan": loan, "expense": expense, "income": income}


def test_cash_flow_sections_and_reconciliation(client, cash_flow_chart):
    fy = _fy(client, "2043-04-01", "2044-03-31")
    c = cash_flow_chart
    bank_id = c["bank"]["id"]
    asset_id = c["asset"]["id"]
    loan_id = c["loan"]["id"]
    expense_id = c["expense"]["id"]
    income_id = c["income"]["id"]

    client.put(f"/accounts/{bank_id}/opening-balance", json={"fy_id": fy["id"], "amount": 100_000})

    client.post("/transactions", json={
        "type": "receipt", "date": "2043-05-01", "narration": "Invoice",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": bank_id, "amount": 200_000},
            {"account_id": income_id, "amount": -200_000},
        ],
    })
    client.post("/transactions", json={
        "type": "payment", "date": "2043-06-01", "narration": "Rent",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": expense_id, "amount": 50_000},
            {"account_id": bank_id, "amount": -50_000},
        ],
    })
    client.post("/transactions", json={
        "type": "payment", "date": "2043-07-01", "narration": "Laptop purchase",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": asset_id, "amount": 80_000},
            {"account_id": bank_id, "amount": -80_000},
        ],
    })
    client.post("/transactions", json={
        "type": "receipt", "date": "2043-08-01", "narration": "Loan disbursement",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": bank_id, "amount": 50_000},
            {"account_id": loan_id, "amount": -50_000},
        ],
    })

    data = client.get(f"/reports/cash-flow?fy_id={fy['id']}").json()
    sections = {s["tag"]: s for s in data["sections"]}
    assert set(sections) == {"operating", "investing", "financing"}
    assert data["net_profit"] == 150_000
    assert sections["investing"]["subtotal"] == -80_000
    assert sections["financing"]["subtotal"] == 50_000
    assert data["opening_cash"] == 100_000
    assert data["closing_cash"] == data["opening_cash"] + data["net_change_in_cash"]
    assert data["closing_cash"] == 220_000


# ── Slice 5: PDF export ───────────────────────────────────────────────────────


def test_trial_balance_pdf_returns_pdf_bytes(client, chart):
    fy = _fy(client, "2044-04-01", "2045-03-31")
    bank_id = chart["bank"]["id"]
    expense_id = chart["expense"]["id"]
    client.post("/transactions", json={
        "type": "payment", "date": "2044-05-01", "narration": "Stationery",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": expense_id, "amount": 5_000},
            {"account_id": bank_id, "amount": -5_000},
        ],
    })
    resp = client.get(f"/reports/trial-balance?fy_id={fy['id']}&format=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_profit_loss_pdf(client, chart):
    fy = _fy(client, "2045-04-01", "2046-03-31")
    resp = client.get(f"/reports/profit-loss?fy_id={fy['id']}&format=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_balance_sheet_pdf(client, chart):
    fy = _fy(client, "2046-04-01", "2047-03-31")
    resp = client.get(f"/reports/balance-sheet?fy_id={fy['id']}&format=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_cash_flow_pdf(client, cash_flow_chart):
    fy = _fy(client, "2047-04-01", "2048-03-31")
    resp = client.get(f"/reports/cash-flow?fy_id={fy['id']}&format=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


# ── Slice 3: balance sheet ────────────────────────────────────────────────────


def test_balance_sheet_accounting_equation(client, chart):
    fy = _fy(client, "2048-04-01", "2049-03-31")
    bank_id = chart["bank"]["id"]
    income_id = chart["income"]["id"]
    expense_id = chart["expense"]["id"]

    client.put(f"/accounts/{bank_id}/opening-balance", json={"fy_id": fy["id"], "amount": 200_000})
    client.post("/transactions", json={
        "type": "receipt",
        "date": "2048-05-01",
        "narration": "Invoice payment",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": bank_id, "amount": 150_000},
            {"account_id": income_id, "amount": -150_000},
        ],
    })
    client.post("/transactions", json={
        "type": "payment",
        "date": "2048-06-01",
        "narration": "Rent",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": expense_id, "amount": 40_000},
            {"account_id": bank_id, "amount": -40_000},
        ],
    })

    data = client.get(f"/reports/balance-sheet?fy_id={fy['id']}").json()
    assert data["total_assets"] == data["total_liabilities_and_equity"]
    retained = next(
        s for s in data["equity_sections"] if s["group_name"] == "Retained Earnings"
    )
    assert retained["subtotal"] == 110_000


def test_balance_sheet_no_transactions(client, chart):
    fy = _fy(client, "2049-04-01", "2050-03-31")
    data = client.get(f"/reports/balance-sheet?fy_id={fy['id']}").json()
    assert data["total_assets"] == data["total_liabilities_and_equity"]


def test_trial_balance_totals_balance(client, chart):
    fy = _fy(client, "2050-04-01", "2051-03-31")
    bank_id = chart["bank"]["id"]
    expense_id = chart["expense"]["id"]
    client.post("/transactions", json={
        "type": "payment",
        "date": "2050-05-01",
        "narration": "Stationery",
        "fy_id": fy["id"],
        "entries": [
            {"account_id": expense_id, "amount": 5_000},
            {"account_id": bank_id, "amount": -5_000},
        ],
    })
    data = client.get(f"/reports/trial-balance?fy_id={fy['id']}").json()
    assert data["total_debit"] == data["total_credit"]
