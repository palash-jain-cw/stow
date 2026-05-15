import pytest
from datetime import date


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def fy(client):
    return client.post("/financial-years", json={
        "start_date": "2025-04-01",
        "end_date": "2026-03-31",
    }).json()


@pytest.fixture()
def bank(client):
    grp = client.post("/account-groups", json={"name": "Bank Accounts", "nature": "asset", "cash_flow_tag": "operating"}).json()
    return client.post("/accounts", json={"name": "HDFC Bank", "group_id": grp["id"]}).json()


@pytest.fixture()
def mf_account(client):
    grp = client.post("/account-groups", json={"name": "Investments", "nature": "asset", "cash_flow_tag": "investing"}).json()
    return client.post("/accounts", json={
        "name": "HDFC Flexi Cap Fund",
        "group_id": grp["id"],
        "investment_subtype": "equity_mf",
    }).json()


# ── helpers ───────────────────────────────────────────────────────────────────

def buy(client, fy_id, mf_id, bank_id, units=10_000, cost_per_unit=100,
        dt="2025-05-01", narration="SIP purchase"):
    return client.post(f"/investments/{mf_id}/buy", json={
        "fy_id": fy_id, "date": dt, "units": units,
        "cost_per_unit": cost_per_unit,
        "bank_account_id": bank_id, "narration": narration,
    })


def sell(client, fy_id, mf_id, bank_id, units=5_000, price_per_unit=120,
         dt="2026-01-01", narration="Redemption"):
    return client.post(f"/investments/{mf_id}/sell", json={
        "fy_id": fy_id, "date": dt, "units": units,
        "price_per_unit": price_per_unit,
        "bank_account_id": bank_id, "narration": narration,
    })


# ── Slice 1: buy creates a lot ────────────────────────────────────────────────

def test_buy_creates_lot(client, fy, bank, mf_account):
    resp = client.post(f"/investments/{mf_account['id']}/buy", json={
        "fy_id": fy["id"],
        "date": "2025-05-01",
        "units": 10_000,          # 10.000 units in milliunits
        "cost_per_unit": 100,     # ₹0.10 per milliunit = ₹100 per unit
        "bank_account_id": bank["id"],
        "narration": "SIP purchase",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["units"] == 10_000
    assert data["cost_per_unit"] == 100
    assert data["remaining_units"] == 10_000
    assert data["acquisition_date"] == "2025-05-01"


# ── Slice 2: buy posts a balanced transaction ─────────────────────────────────

def test_buy_posts_balanced_transaction(client, fy, bank, mf_account):
    lot = buy(client, fy["id"], mf_account["id"], bank["id"],
              units=10_000, cost_per_unit=100).json()

    # Fetch the transaction via the ledger endpoint
    txn_id = lot["transaction_id"]
    ledger = client.get(f"/accounts/{mf_account['id']}/ledger?fy_id={fy['id']}").json()
    txn_entry = next(e for e in ledger if e["transaction_id"] == txn_id)

    # total cost = 10_000 milliunits * 100 paise/milliunit / 1000 = 1_000 paise
    assert txn_entry["amount"] == 1_000          # Dr investment account
    assert txn_entry["running_balance"] == 1_000

    # Bank ledger should show the equal and opposite credit
    bank_ledger = client.get(f"/accounts/{bank['id']}/ledger?fy_id={fy['id']}").json()
    bank_entry = next(e for e in bank_ledger if e["transaction_id"] == txn_id)
    assert bank_entry["amount"] == -1_000        # Cr bank account


# ── Slice 3: sell FIFO — oldest lot consumed first ────────────────────────────

def test_sell_fifo_oldest_lot_first(client, fy, bank, mf_account):
    mf_id = mf_account["id"]

    # Lot A: bought 2025-05-01 (older)
    buy(client, fy["id"], mf_id, bank["id"], units=5_000,
        cost_per_unit=100, dt="2025-05-01")
    # Lot B: bought 2025-08-01 (newer)
    buy(client, fy["id"], mf_id, bank["id"], units=5_000,
        cost_per_unit=150, dt="2025-08-01")

    # Sell 5_000 milliunits — should fully consume Lot A (cost 100), leave Lot B intact
    resp = sell(client, fy["id"], mf_id, bank["id"],
                units=5_000, price_per_unit=120, dt="2026-01-01")
    assert resp.status_code == 201
    entries = resp.json()

    # Only one capital gain entry — from Lot A
    assert len(entries) == 1
    assert entries[0]["sale_price_per_unit"] == 120
    assert entries[0]["units_sold"] == 5_000
    # gain = (120 - 100) * 5_000 / 1000 = 100 paise
    assert entries[0]["gain"] == 100

    # Lot B should still be fully intact
    holdings = client.get(f"/investments/{mf_id}/holdings").json()
    assert len(holdings) == 1
    assert holdings[0]["remaining_units"] == 5_000
    assert holdings[0]["cost_per_unit"] == 150


# ── Slice 4: STCG / LTCG classification and gain amount ──────────────────────

def test_sell_stcg_when_held_less_than_365_days(client, fy, bank, mf_account):
    mf_id = mf_account["id"]
    # Buy 2025-05-01, sell 2025-11-01 → 184 days → STCG
    buy(client, fy["id"], mf_id, bank["id"],
        units=10_000, cost_per_unit=100, dt="2025-05-01")

    entries = sell(client, fy["id"], mf_id, bank["id"],
                   units=10_000, price_per_unit=150,
                   dt="2025-11-01").json()

    assert entries[0]["gain_type"] == "stcg"
    # gain = (150 - 100) * 10_000 / 1000 = 500 paise
    assert entries[0]["gain"] == 500


def test_sell_ltcg_when_held_365_days_or_more(client, fy, bank, mf_account):
    mf_id = mf_account["id"]

    fy2 = client.post("/financial-years", json={
        "start_date": "2024-04-01", "end_date": "2025-03-31",
    }).json()

    # Buy 2024-04-01, sell 2025-05-01 → 396 days → LTCG
    buy(client, fy2["id"], mf_id, bank["id"],
        units=10_000, cost_per_unit=100, dt="2024-04-01")

    entries = sell(client, fy["id"], mf_id, bank["id"],
                   units=10_000, price_per_unit=200,
                   dt="2025-05-01").json()

    assert entries[0]["gain_type"] == "ltcg"
    # gain = (200 - 100) * 10_000 / 1000 = 1000 paise
    assert entries[0]["gain"] == 1_000


def test_sell_records_loss_as_negative_gain(client, fy, bank, mf_account):
    mf_id = mf_account["id"]
    buy(client, fy["id"], mf_id, bank["id"],
        units=10_000, cost_per_unit=200, dt="2025-05-01")

    entries = sell(client, fy["id"], mf_id, bank["id"],
                   units=10_000, price_per_unit=150,
                   dt="2025-08-01").json()

    # gain = (150 - 200) * 10_000 / 1000 = -500 paise
    assert entries[0]["gain"] == -500
    assert entries[0]["gain_type"] == "stcg"


# ── Slice 5: partial lot consumption ─────────────────────────────────────────

def test_partial_lot_remaining_units_decremented(client, fy, bank, mf_account):
    mf_id = mf_account["id"]
    buy(client, fy["id"], mf_id, bank["id"],
        units=10_000, cost_per_unit=100, dt="2025-05-01")

    # Sell only 3_000 of the 10_000 milliunits
    entries = sell(client, fy["id"], mf_id, bank["id"],
                   units=3_000, price_per_unit=120,
                   dt="2025-08-01").json()

    assert len(entries) == 1
    assert entries[0]["units_sold"] == 3_000
    # gain = (120 - 100) * 3_000 / 1000 = 60 paise
    assert entries[0]["gain"] == 60

    # The original lot should have 7_000 remaining
    holdings = client.get(f"/investments/{mf_id}/holdings").json()
    assert len(holdings) == 1
    assert holdings[0]["remaining_units"] == 7_000
    assert holdings[0]["cost_basis"] == 7_000 * 100 // 1000  # 700 paise


def test_partial_then_full_consumes_same_lot(client, fy, bank, mf_account):
    mf_id = mf_account["id"]
    buy(client, fy["id"], mf_id, bank["id"],
        units=10_000, cost_per_unit=100, dt="2025-05-01")

    sell(client, fy["id"], mf_id, bank["id"],
         units=4_000, price_per_unit=120, dt="2025-08-01")
    sell(client, fy["id"], mf_id, bank["id"],
         units=6_000, price_per_unit=130, dt="2025-09-01")

    # Lot fully consumed — holdings should be empty
    holdings = client.get(f"/investments/{mf_id}/holdings").json()
    assert holdings == []


# ── Slice 6: sell more than held → 422 ───────────────────────────────────────

def test_sell_more_than_held_returns_422(client, fy, bank, mf_account):
    mf_id = mf_account["id"]
    buy(client, fy["id"], mf_id, bank["id"],
        units=5_000, cost_per_unit=100, dt="2025-05-01")

    resp = sell(client, fy["id"], mf_id, bank["id"],
                units=6_000, price_per_unit=120, dt="2025-08-01")
    assert resp.status_code == 422

    # Original lot must be untouched
    holdings = client.get(f"/investments/{mf_id}/holdings").json()
    assert holdings[0]["remaining_units"] == 5_000


def test_sell_on_empty_holdings_returns_422(client, fy, bank, mf_account):
    resp = sell(client, fy["id"], mf_account["id"], bank["id"],
                units=1_000, price_per_unit=100, dt="2025-08-01")
    assert resp.status_code == 422


# ── Slice 7: holdings excludes fully consumed lots ────────────────────────────

def test_holdings_excludes_exhausted_lots(client, fy, bank, mf_account):
    mf_id = mf_account["id"]
    # Buy two lots
    buy(client, fy["id"], mf_id, bank["id"],
        units=4_000, cost_per_unit=100, dt="2025-05-01")
    buy(client, fy["id"], mf_id, bank["id"],
        units=6_000, cost_per_unit=120, dt="2025-06-01")

    # Fully consume the first lot
    sell(client, fy["id"], mf_id, bank["id"],
         units=4_000, price_per_unit=130, dt="2025-09-01")

    holdings = client.get(f"/investments/{mf_id}/holdings").json()
    assert len(holdings) == 1
    assert holdings[0]["remaining_units"] == 6_000
    assert holdings[0]["cost_per_unit"] == 120


def test_holdings_shows_cost_basis_on_remaining_units(client, fy, bank, mf_account):
    mf_id = mf_account["id"]
    buy(client, fy["id"], mf_id, bank["id"],
        units=10_000, cost_per_unit=150, dt="2025-05-01")
    sell(client, fy["id"], mf_id, bank["id"],
         units=3_000, price_per_unit=200, dt="2025-08-01")

    holdings = client.get(f"/investments/{mf_id}/holdings").json()
    assert holdings[0]["remaining_units"] == 7_000
    # cost_basis = 7_000 * 150 / 1000 = 1_050 paise
    assert holdings[0]["cost_basis"] == 1_050


# ── Slice 8: capital gains totals by type for FY ─────────────────────────────

def test_capital_gains_totals_stcg_and_ltcg(client, fy, bank, mf_account):
    mf_id = mf_account["id"]

    fy_prev = client.post("/financial-years", json={
        "start_date": "2024-04-01", "end_date": "2025-03-31",
    }).json()

    # LTCG lot: bought 2024-04-01, held > 365 days, sold in current FY
    buy(client, fy_prev["id"], mf_id, bank["id"],
        units=10_000, cost_per_unit=100, dt="2024-04-01")

    # STCG lot: bought 2025-05-01, sold same FY within 365 days
    buy(client, fy["id"], mf_id, bank["id"],
        units=5_000, cost_per_unit=200, dt="2025-05-01")

    # Sell LTCG lot: gain = (200-100)*10_000/1000 = 1_000 paise
    sell(client, fy["id"], mf_id, bank["id"],
         units=10_000, price_per_unit=200, dt="2025-05-15")

    # Sell STCG lot: gain = (250-200)*5_000/1000 = 250 paise
    sell(client, fy["id"], mf_id, bank["id"],
         units=5_000, price_per_unit=250, dt="2025-08-01")

    resp = client.get(f"/investments/{mf_id}/capital-gains?fy_id={fy['id']}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_ltcg"] == 1_000
    assert data["total_stcg"] == 250
    assert data["total_loss"] == 0
    assert len(data["entries"]) == 2


def test_capital_gains_only_includes_current_fy(client, fy, bank, mf_account):
    mf_id = mf_account["id"]

    fy_prev = client.post("/financial-years", json={
        "start_date": "2024-04-01", "end_date": "2025-03-31",
    }).json()

    buy(client, fy_prev["id"], mf_id, bank["id"],
        units=10_000, cost_per_unit=100, dt="2024-04-01")
    # Sell in the previous FY
    sell(client, fy_prev["id"], mf_id, bank["id"],
         units=10_000, price_per_unit=150, dt="2024-10-01")

    # Current FY should have no CG entries
    data = client.get(f"/investments/{mf_id}/capital-gains?fy_id={fy['id']}").json()
    assert data["entries"] == []
    assert data["total_stcg"] == 0
    assert data["total_ltcg"] == 0


# ── Slice 9: tax rule versioning ─────────────────────────────────────────────

def test_sell_uses_tax_rule_effective_on_sale_date(client, bank, mf_account):
    """
    Seed has two equity rules:
      - effective 2018-02-01: STCG threshold = 365 days
      - effective 2024-07-23: STCG threshold = 365 days (same threshold, different rates)
    We insert a test rule effective 2025-06-01 with threshold = 180 days so a
    180-day holding flips from stcg (pre-rule) to ltcg (post-rule).
    """
    # Insert a test rule effective 2025-06-01: holding >= 180 days → ltcg
    client.post("/tax-rules", json={
        "asset_type": "equity",
        "holding_threshold_days": 180,
        "stcg_rate_bps": 2000,
        "ltcg_rate_bps": 1250,
        "ltcg_exemption_paise": 12_500_000,
        "effective_from": "2025-06-01",
    })

    fy_a = client.post("/financial-years", json={
        "start_date": "2024-04-01", "end_date": "2025-03-31",
    }).json()
    fy_b = client.post("/financial-years", json={
        "start_date": "2025-04-01", "end_date": "2026-03-31",
    }).json()

    mf_id = mf_account["id"]

    # Buy 2024-10-01 in both cases — we'll sell at exactly 183-day gap
    # Sale A: 2025-04-02 (183 days) — pre-test rule → uses 2024-07-23 rule → threshold 365 → STCG
    buy(client, fy_a["id"], mf_id, bank["id"],
        units=5_000, cost_per_unit=100, dt="2024-10-01")
    entries_a = sell(client, fy_a["id"], mf_id, bank["id"],
                     units=5_000, price_per_unit=120,
                     dt="2025-04-02").json()
    assert entries_a[0]["gain_type"] == "stcg"

    # Sale B: 2025-06-15 (another fresh lot, 183 days) — post-test rule → threshold 180 → LTCG
    buy(client, fy_b["id"], mf_id, bank["id"],
        units=5_000, cost_per_unit=100, dt="2024-12-14")
    entries_b = sell(client, fy_b["id"], mf_id, bank["id"],
                     units=5_000, price_per_unit=120,
                     dt="2025-06-15").json()
    assert entries_b[0]["gain_type"] == "ltcg"
