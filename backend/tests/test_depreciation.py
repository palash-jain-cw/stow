import pytest


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def fy(client):
    return client.post("/financial-years", json={
        "start_date": "2025-04-01",
        "end_date": "2026-03-31",
    }).json()


@pytest.fixture()
def fixed_assets_group(client):
    return next(g for g in client.get("/account-groups").json() if g["name"] == "Fixed Assets")


@pytest.fixture()
def accum_depr_group(client):
    return next(g for g in client.get("/account-groups").json() if g["name"] == "Accumulated Depreciation")


@pytest.fixture()
def bank(client):
    grp = next(g for g in client.get("/account-groups").json() if g["name"] == "Bank Accounts")
    return client.post("/accounts", json={"name": "Test Bank", "group_id": grp["id"]}).json()


def make_asset(client, fixed_assets_group, accum_depr_group, name="Laptop", rate=0.15):
    asset = client.post("/accounts", json={
        "name": name,
        "group_id": fixed_assets_group["id"],
        "depreciation_rate": rate,
    }).json()
    accum = client.post("/accounts", json={
        "name": f"Accumulated Depreciation - {name}",
        "group_id": accum_depr_group["id"],
    }).json()
    client.put(f"/accounts/{asset['id']}", json={
        "name": asset["name"],
        "group_id": asset["group_id"],
        "depreciation_rate": rate,
        "accumulated_depreciation_account_id": accum["id"],
    })
    return asset, accum


def set_ob(client, account_id, fy_id, amount):
    client.put(f"/accounts/{account_id}/opening-balance", json={"fy_id": fy_id, "amount": amount})


def get_summary_item(client, fy_id, account_id):
    items = client.get(f"/depreciation/summary?fy_id={fy_id}").json()
    return next((i for i in items if i["account_id"] == account_id), None)


# ── Slice 1: basic WDV depreciation amount ────────────────────────────────────

def test_summary_returns_depreciation_amount_from_opening_balance(client, fy, fixed_assets_group, accum_depr_group):
    # ₹10,000 asset at 15% → ₹1,500 depreciation (150_000 paise)
    asset, _ = make_asset(client, fixed_assets_group, accum_depr_group)
    set_ob(client, asset["id"], fy["id"], 1_000_000)

    item = get_summary_item(client, fy["id"], asset["id"])

    assert item is not None
    assert item["depreciation_amount"] == 150_000
    assert item["opening_wdv"] == 1_000_000
    assert item["depreciation_rate"] == 0.15


def test_summary_wdv_is_net_of_accumulated_depreciation(client, fy, fixed_assets_group, accum_depr_group):
    # Asset gross ₹10,000; ₹1,500 already depreciated → WDV = ₹8,500 → depr = 8,500 * 0.15 = 1,275
    asset, accum = make_asset(client, fixed_assets_group, accum_depr_group, name="Server")
    set_ob(client, asset["id"], fy["id"], 1_000_000)
    set_ob(client, accum["id"], fy["id"], -150_000)  # credit balance on accum depr account

    item = get_summary_item(client, fy["id"], asset["id"])

    assert item["opening_wdv"] == 850_000
    assert item["depreciation_amount"] == 127_500


# ── Slice 3: half-year rule ────────────────────────────────────────────────────

def _post_journal(client, fy_id, asset_id, bank_id, amount, txn_date):
    client.post("/transactions", json={
        "fy_id": fy_id,
        "type": "journal",
        "date": txn_date,
        "narration": "Asset purchase",
        "entries": [
            {"account_id": asset_id, "amount": amount},
            {"account_id": bank_id, "amount": -amount},
        ],
    })


def test_half_year_rule_not_applied_when_acquired_on_oct3(client, fy, fixed_assets_group, accum_depr_group, bank):
    asset, _ = make_asset(client, fixed_assets_group, accum_depr_group, name="Oct3 Asset", rate=0.40)
    _post_journal(client, fy["id"], asset["id"], bank["id"], 1_000_000, "2025-10-03")

    item = get_summary_item(client, fy["id"], asset["id"])

    assert item["half_year_rule_applied"] is False
    assert item["depreciation_amount"] == 400_000  # full 40%


def test_half_year_rule_applied_when_acquired_after_oct3(client, fy, fixed_assets_group, accum_depr_group, bank):
    asset, _ = make_asset(client, fixed_assets_group, accum_depr_group, name="Oct4 Asset", rate=0.40)
    _post_journal(client, fy["id"], asset["id"], bank["id"], 1_000_000, "2025-10-04")

    item = get_summary_item(client, fy["id"], asset["id"])

    assert item["half_year_rule_applied"] is True
    assert item["depreciation_amount"] == 200_000  # 50% of 40%


# ── Slice 4: edge cases ────────────────────────────────────────────────────────

def test_zero_depreciation_rate_gives_zero_amount(client, fy, fixed_assets_group, accum_depr_group):
    asset, _ = make_asset(client, fixed_assets_group, accum_depr_group, name="Land", rate=0.0)
    set_ob(client, asset["id"], fy["id"], 5_000_000)

    item = get_summary_item(client, fy["id"], asset["id"])

    assert item["depreciation_amount"] == 0


def test_fully_depreciated_asset_gives_zero_amount(client, fy, fixed_assets_group, accum_depr_group):
    asset, accum = make_asset(client, fixed_assets_group, accum_depr_group, name="Old PC")
    set_ob(client, asset["id"], fy["id"], 1_000_000)
    set_ob(client, accum["id"], fy["id"], -1_000_000)  # fully depreciated

    item = get_summary_item(client, fy["id"], asset["id"])

    assert item["opening_wdv"] == 0
    assert item["depreciation_amount"] == 0


# ── Slice 5: pre-lock check ────────────────────────────────────────────────────

def test_pre_lock_check_flags_asset_with_no_depreciation_posted(client, fy, fixed_assets_group, accum_depr_group):
    asset, _ = make_asset(client, fixed_assets_group, accum_depr_group, name="Router")
    set_ob(client, asset["id"], fy["id"], 500_000)

    resp = client.get(f"/financial-years/{fy['id']}/pre-lock-check")
    assert resp.status_code == 200
    ids = [a["account_id"] for a in resp.json()["unposted_depreciation"]]
    assert asset["id"] in ids


def test_pre_lock_check_clears_asset_after_depreciation_posted(client, fy, fixed_assets_group, accum_depr_group, bank):
    asset, accum = make_asset(client, fixed_assets_group, accum_depr_group, name="Switch")
    set_ob(client, asset["id"], fy["id"], 500_000)

    # Post a depreciation journal: Dr Depreciation Expense, Cr Accumulated Depreciation
    depr_account = next(
        a for a in client.get("/accounts").json()
        if a["name"] == "Depreciation"
    )
    client.post("/transactions", json={
        "fy_id": fy["id"],
        "type": "journal",
        "date": "2026-03-31",
        "narration": "Depreciation FY2025-26",
        "entries": [
            {"account_id": depr_account["id"], "amount": 75_000},
            {"account_id": accum["id"], "amount": -75_000},
        ],
    })

    resp = client.get(f"/financial-years/{fy['id']}/pre-lock-check")
    ids = [a["account_id"] for a in resp.json()["unposted_depreciation"]]
    assert asset["id"] not in ids
