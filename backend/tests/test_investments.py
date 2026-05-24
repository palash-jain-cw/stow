import uuid

import pytest

from tests.helpers import get_or_create_account, get_or_create_fy, get_or_create_group


@pytest.fixture()
def inv(client):
    """Isolated bank + MF account pair per test (lots do not leak across tests)."""
    tag = uuid.uuid4().hex[:8]
    get_or_create_group(client, "Bank Accounts", "asset", cash_flow_tag="operating")
    get_or_create_group(client, "Investments", "asset", cash_flow_tag="investing")
    bank = get_or_create_account(client, f"Inv Bank {tag}", "Bank Accounts")
    mf = get_or_create_account(
        client,
        f"Inv MF {tag}",
        "Investments",
        investment_subtype="equity_mf",
    )
    return {"bank": bank, "mf": mf}


def buy(client, fy_id, mf_id, bank_id, units=10_000, cost_per_unit=100,
        dt="2025-05-01", narration="SIP purchase"):
    payload = {
        "fy_id": fy_id, "date": dt, "units": units,
        "cost_per_unit": cost_per_unit,
        "bank_account_id": bank_id,
    }
    if narration is not None:
        payload["narration"] = narration
    resp = client.post(f"/investments/{mf_id}/buy", json=payload)
    assert resp.status_code == 201, resp.text
    return resp


def sell(client, fy_id, mf_id, bank_id, units=5_000, price_per_unit=120,
         dt="2026-01-01", narration="Redemption"):
    return client.post(f"/investments/{mf_id}/sell", json={
        "fy_id": fy_id, "date": dt, "units": units,
        "price_per_unit": price_per_unit,
        "bank_account_id": bank_id, "narration": narration,
    })


# ── Slice 1: buy creates a lot ────────────────────────────────────────────────


def test_buy_creates_lot(client, inv):
    fy = get_or_create_fy(client, "2025-04-01", "2026-03-31")
    resp = buy(client, fy["id"], inv["mf"]["id"], inv["bank"]["id"])
    data = resp.json()
    assert data["units"] == 10_000
    assert data["cost_per_unit"] == 100
    assert data["remaining_units"] == 10_000
    assert data["acquisition_date"] == "2025-05-01"


def test_buy_without_narration(client, inv):
    fy = get_or_create_fy(client, "2025-04-01", "2026-03-31")
    resp = buy(client, fy["id"], inv["mf"]["id"], inv["bank"]["id"], narration=None)
    txn = client.get(f"/transactions/{resp.json()['transaction_id']}").json()
    assert txn["narration"] == ""


def test_update_buy_transaction_date_syncs_lot(client, inv):
    fy = get_or_create_fy(client, "2025-04-01", "2026-03-31")
    lot = buy(client, fy["id"], inv["mf"]["id"], inv["bank"]["id"], dt="2025-05-01").json()
    resp = client.put(f"/transactions/{lot['transaction_id']}", json={"date": "2024-06-15"})
    assert resp.status_code == 200
    assert resp.json()["date"] == "2024-06-15"
    mf_id = inv["mf"]["id"]
    holdings = client.get(f"/investments/{mf_id}/holdings").json()
    assert holdings[0]["acquisition_date"] == "2024-06-15"
    portfolio = client.get(f"/investments/{mf_id}/portfolio").json()
    assert portfolio[0]["acquisition_date"] == "2024-06-15"


# ── Slice 2: buy posts a balanced transaction ─────────────────────────────────


def test_buy_posts_balanced_transaction(client, inv):
    fy = get_or_create_fy(client, "2026-04-01", "2027-03-31")
    mf_id, bank_id = inv["mf"]["id"], inv["bank"]["id"]
    lot = buy(
        client, fy["id"], mf_id, bank_id,
        units=10_000, cost_per_unit=100, dt="2026-05-01",
    ).json()

    txn_id = lot["transaction_id"]
    ledger = client.get(f"/accounts/{mf_id}/ledger?fy_id={fy['id']}").json()
    txn_entry = next(e for e in ledger if e["transaction_id"] == txn_id)

    # total cost = 10_000 milliunits * 100 paise/milliunit / 1000 = 1_000 paise
    assert txn_entry["amount"] == 1_000
    assert txn_entry["running_balance"] == 1_000

    bank_ledger = client.get(f"/accounts/{bank_id}/ledger?fy_id={fy['id']}").json()
    bank_entry = next(e for e in bank_ledger if e["transaction_id"] == txn_id)
    assert bank_entry["amount"] == -1_000


# ── Slice 3: sell FIFO — oldest lot consumed first ────────────────────────────


def test_sell_fifo_oldest_lot_first(client, inv):
    fy = get_or_create_fy(client, "2027-04-01", "2028-03-31")
    mf_id, bank_id = inv["mf"]["id"], inv["bank"]["id"]

    buy(client, fy["id"], mf_id, bank_id, units=5_000, cost_per_unit=100, dt="2027-05-01")
    buy(client, fy["id"], mf_id, bank_id, units=5_000, cost_per_unit=150, dt="2027-08-01")

    resp = sell(client, fy["id"], mf_id, bank_id, units=5_000, price_per_unit=120, dt="2028-01-01")
    assert resp.status_code == 201
    entries = resp.json()

    assert len(entries) == 1
    assert entries[0]["sale_price_per_unit"] == 120
    assert entries[0]["units_sold"] == 5_000
    assert entries[0]["gain"] == 100

    holdings = client.get(f"/investments/{mf_id}/holdings").json()
    assert len(holdings) == 1
    assert holdings[0]["remaining_units"] == 5_000
    assert holdings[0]["cost_per_unit"] == 150


# ── Slice 4: STCG / LTCG classification and gain amount ──────────────────────


def test_sell_stcg_when_held_less_than_365_days(client, inv):
    fy = get_or_create_fy(client, "2028-04-01", "2029-03-31")
    mf_id, bank_id = inv["mf"]["id"], inv["bank"]["id"]
    buy(client, fy["id"], mf_id, bank_id, units=10_000, cost_per_unit=100, dt="2028-05-01")

    entries = sell(
        client, fy["id"], mf_id, bank_id,
        units=10_000, price_per_unit=150, dt="2028-11-01",
    ).json()

    assert entries[0]["gain_type"] == "stcg"
    assert entries[0]["gain"] == 500


def test_sell_ltcg_when_held_365_days_or_more(client, inv):
    fy = get_or_create_fy(client, "2029-04-01", "2030-03-31")
    fy2 = get_or_create_fy(client, "2028-04-01", "2029-03-31")
    mf_id, bank_id = inv["mf"]["id"], inv["bank"]["id"]

    buy(client, fy2["id"], mf_id, bank_id, units=10_000, cost_per_unit=100, dt="2028-04-01")
    entries = sell(
        client, fy["id"], mf_id, bank_id,
        units=10_000, price_per_unit=200, dt="2029-05-01",
    ).json()

    assert entries[0]["gain_type"] == "ltcg"
    assert entries[0]["gain"] == 1_000


def test_sell_records_loss_as_negative_gain(client, inv):
    fy = get_or_create_fy(client, "2030-04-01", "2031-03-31")
    mf_id, bank_id = inv["mf"]["id"], inv["bank"]["id"]
    buy(client, fy["id"], mf_id, bank_id, units=10_000, cost_per_unit=200, dt="2030-05-01")

    entries = sell(
        client, fy["id"], mf_id, bank_id,
        units=10_000, price_per_unit=150, dt="2030-08-01",
    ).json()

    assert entries[0]["gain"] == -500
    assert entries[0]["gain_type"] == "stcg"


# ── Slice 5: partial lot consumption ─────────────────────────────────────────


def test_partial_lot_remaining_units_decremented(client, inv):
    fy = get_or_create_fy(client, "2031-04-01", "2032-03-31")
    mf_id, bank_id = inv["mf"]["id"], inv["bank"]["id"]
    buy(client, fy["id"], mf_id, bank_id, units=10_000, cost_per_unit=100, dt="2031-05-01")

    entries = sell(
        client, fy["id"], mf_id, bank_id,
        units=3_000, price_per_unit=120, dt="2031-08-01",
    ).json()

    assert len(entries) == 1
    assert entries[0]["units_sold"] == 3_000
    assert entries[0]["gain"] == 60

    holdings = client.get(f"/investments/{mf_id}/holdings").json()
    assert len(holdings) == 1
    assert holdings[0]["remaining_units"] == 7_000
    assert holdings[0]["cost_basis"] == 700


def test_partial_then_full_consumes_same_lot(client, inv):
    fy = get_or_create_fy(client, "2032-04-01", "2033-03-31")
    mf_id, bank_id = inv["mf"]["id"], inv["bank"]["id"]
    buy(client, fy["id"], mf_id, bank_id, units=10_000, cost_per_unit=100, dt="2032-05-01")

    sell(client, fy["id"], mf_id, bank_id, units=4_000, price_per_unit=120, dt="2032-08-01")
    sell(client, fy["id"], mf_id, bank_id, units=6_000, price_per_unit=130, dt="2032-09-01")

    holdings = client.get(f"/investments/{mf_id}/holdings").json()
    assert holdings == []


# ── Slice 6: sell more than held → 422 ───────────────────────────────────────


def test_sell_more_than_held_returns_422(client, inv):
    fy = get_or_create_fy(client, "2033-04-01", "2034-03-31")
    mf_id, bank_id = inv["mf"]["id"], inv["bank"]["id"]
    buy(client, fy["id"], mf_id, bank_id, units=5_000, cost_per_unit=100, dt="2033-05-01")

    resp = sell(client, fy["id"], mf_id, bank_id, units=6_000, price_per_unit=120, dt="2033-08-01")
    assert resp.status_code == 422

    holdings = client.get(f"/investments/{mf_id}/holdings").json()
    assert holdings[0]["remaining_units"] == 5_000


def test_sell_on_empty_holdings_returns_422(client, inv):
    fy = get_or_create_fy(client, "2034-04-01", "2035-03-31")
    resp = sell(
        client, fy["id"], inv["mf"]["id"], inv["bank"]["id"],
        units=1_000, price_per_unit=100, dt="2034-08-01",
    )
    assert resp.status_code == 422


# ── Slice 7: holdings excludes fully consumed lots ────────────────────────────


def test_holdings_excludes_exhausted_lots(client, inv):
    fy = get_or_create_fy(client, "2035-04-01", "2036-03-31")
    mf_id, bank_id = inv["mf"]["id"], inv["bank"]["id"]
    buy(client, fy["id"], mf_id, bank_id, units=4_000, cost_per_unit=100, dt="2035-05-01")
    buy(client, fy["id"], mf_id, bank_id, units=6_000, cost_per_unit=120, dt="2035-06-01")

    sell(client, fy["id"], mf_id, bank_id, units=4_000, price_per_unit=130, dt="2035-09-01")

    holdings = client.get(f"/investments/{mf_id}/holdings").json()
    assert len(holdings) == 1
    assert holdings[0]["remaining_units"] == 6_000
    assert holdings[0]["cost_per_unit"] == 120


def test_holdings_shows_cost_basis_on_remaining_units(client, inv):
    fy = get_or_create_fy(client, "2036-04-01", "2037-03-31")
    mf_id, bank_id = inv["mf"]["id"], inv["bank"]["id"]
    buy(client, fy["id"], mf_id, bank_id, units=10_000, cost_per_unit=150, dt="2036-05-01")
    sell(client, fy["id"], mf_id, bank_id, units=3_000, price_per_unit=200, dt="2036-08-01")

    holdings = client.get(f"/investments/{mf_id}/holdings").json()
    assert holdings[0]["remaining_units"] == 7_000
    assert holdings[0]["cost_basis"] == 1_050


# ── Slice 8: capital gains totals by type for FY ─────────────────────────────


def test_capital_gains_totals_stcg_and_ltcg(client, inv):
    fy = get_or_create_fy(client, "2037-04-01", "2038-03-31")
    fy_prev = get_or_create_fy(client, "2036-04-01", "2037-03-31")
    mf_id, bank_id = inv["mf"]["id"], inv["bank"]["id"]

    buy(client, fy_prev["id"], mf_id, bank_id, units=10_000, cost_per_unit=100, dt="2036-04-01")
    buy(client, fy["id"], mf_id, bank_id, units=5_000, cost_per_unit=200, dt="2037-05-01")

    sell(client, fy["id"], mf_id, bank_id, units=10_000, price_per_unit=200, dt="2037-05-15")
    sell(client, fy["id"], mf_id, bank_id, units=5_000, price_per_unit=250, dt="2037-08-01")

    data = client.get(f"/investments/{mf_id}/capital-gains?fy_id={fy['id']}").json()
    assert data["total_ltcg"] == 1_000
    assert data["total_stcg"] == 250
    assert data["total_loss"] == 0
    assert len(data["entries"]) == 2


def test_capital_gains_only_includes_current_fy(client, inv):
    fy = get_or_create_fy(client, "2038-04-01", "2039-03-31")
    fy_prev = get_or_create_fy(client, "2037-04-01", "2038-03-31")
    mf_id, bank_id = inv["mf"]["id"], inv["bank"]["id"]

    buy(client, fy_prev["id"], mf_id, bank_id, units=10_000, cost_per_unit=100, dt="2037-04-01")
    sell(client, fy_prev["id"], mf_id, bank_id, units=10_000, price_per_unit=150, dt="2037-10-01")

    data = client.get(f"/investments/{mf_id}/capital-gains?fy_id={fy['id']}").json()
    assert data["entries"] == []
    assert data["total_stcg"] == 0
    assert data["total_ltcg"] == 0


# ── Slice 9: tax rule versioning ─────────────────────────────────────────────


def test_sell_uses_tax_rule_effective_on_sale_date(client, inv):
    """Custom rule from 2039-06-01 lowers LTCG threshold to 180 days."""
    rule_date = "2039-06-01"
    client.post("/tax-rules", json={
        "asset_type": "equity",
        "holding_threshold_days": 180,
        "stcg_rate_bps": 2000,
        "ltcg_rate_bps": 1250,
        "ltcg_exemption_paise": 12_500_000,
        "effective_from": rule_date,
    })

    fy_a = get_or_create_fy(client, "2038-04-01", "2039-03-31")
    fy_b = get_or_create_fy(client, "2039-04-01", "2040-03-31")
    mf_id, bank_id = inv["mf"]["id"], inv["bank"]["id"]

    # 183-day hold; sale on 2039-04-02 (before custom rule) → STCG (365-day threshold)
    buy(client, fy_a["id"], mf_id, bank_id, units=5_000, cost_per_unit=100, dt="2038-10-01")
    resp_a = sell(
        client, fy_b["id"], mf_id, bank_id,
        units=5_000, price_per_unit=120, dt="2039-04-02",
    )
    assert resp_a.status_code == 201, resp_a.text
    assert resp_a.json()[0]["gain_type"] == "stcg"

    # 183-day hold; sale on/after custom rule → LTCG (180-day threshold)
    buy(client, fy_a["id"], mf_id, bank_id, units=5_000, cost_per_unit=100, dt="2038-12-14")
    resp_b = sell(
        client, fy_b["id"], mf_id, bank_id,
        units=5_000, price_per_unit=120, dt="2039-06-15",
    )
    assert resp_b.status_code == 201, resp_b.text
    assert resp_b.json()[0]["gain_type"] == "ltcg"
