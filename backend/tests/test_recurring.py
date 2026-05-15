from datetime import date, timedelta
import pytest


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def fy(client):
    return client.post("/financial-years", json={
        "start_date": "2025-04-01",
        "end_date": "2026-03-31",
    }).json()


@pytest.fixture()
def bank(client):
    grp = next(g for g in client.get("/account-groups").json() if g["name"] == "Bank Accounts")
    return client.post("/accounts", json={"name": "Recurring Bank", "group_id": grp["id"]}).json()


@pytest.fixture()
def expense_account(client):
    grp = next(g for g in client.get("/account-groups").json() if g["name"] == "Indirect Expenses")
    return client.post("/accounts", json={"name": "Rent", "group_id": grp["id"]}).json()


@pytest.fixture()
def template_txn(client, fy, bank, expense_account):
    resp = client.post("/transactions", json={
        "fy_id": fy["id"],
        "type": "payment",
        "date": "2025-04-01",
        "narration": "Monthly rent",
        "entries": [
            {"account_id": expense_account["id"], "amount": 5_000_000},
            {"account_id": bank["id"], "amount": -5_000_000},
        ],
    })
    return resp.json()


def make_schedule(client, template_id, frequency="monthly", day_of_period=1,
                  first_due_date="2025-05-01", end_date=None):
    return client.post("/recurring/schedules", json={
        "template_transaction_id": template_id,
        "frequency": frequency,
        "day_of_period": day_of_period,
        "first_due_date": first_due_date,
        "end_date": end_date,
    })


# ── Slice 1: POST /recurring/schedules ───────────────────────────────────────

def test_create_schedule_returns_201_with_next_due_date(client, template_txn):
    resp = make_schedule(client, template_txn["id"])
    assert resp.status_code == 201
    data = resp.json()
    assert data["template_transaction_id"] == template_txn["id"]
    assert data["frequency"] == "monthly"
    assert data["next_due_date"] == "2025-05-01"
    assert data["is_active"] is True


# ── Slice 2: next_due_date advancement ────────────────────────────────────────

def _run_morning_job(client, session, today):
    from stow.recurring import create_queue_entries_for_today
    create_queue_entries_for_today(session, today=today)


def _schedule_id(resp):
    return resp.json()["id"]


def _get_schedule(client, schedule_id):
    return next(s for s in client.get("/recurring/schedules").json() if s["id"] == schedule_id)


def test_daily_schedule_advances_by_one_day(client, session, template_txn):
    sid = _schedule_id(make_schedule(client, template_txn["id"], frequency="daily",
                                     first_due_date="2025-05-01"))
    _run_morning_job(client, session, date(2025, 5, 1))
    assert _get_schedule(client, sid)["next_due_date"] == "2025-05-02"


def test_weekly_schedule_advances_by_seven_days(client, session, template_txn):
    sid = _schedule_id(make_schedule(client, template_txn["id"], frequency="weekly",
                                     first_due_date="2025-05-01"))
    _run_morning_job(client, session, date(2025, 5, 1))
    assert _get_schedule(client, sid)["next_due_date"] == "2025-05-08"


def test_monthly_schedule_advances_by_one_month(client, session, template_txn):
    sid = _schedule_id(make_schedule(client, template_txn["id"], frequency="monthly",
                                     day_of_period=5, first_due_date="2025-05-05"))
    _run_morning_job(client, session, date(2025, 5, 5))
    assert _get_schedule(client, sid)["next_due_date"] == "2025-06-05"


def test_yearly_schedule_advances_by_one_year(client, session, template_txn):
    sid = _schedule_id(make_schedule(client, template_txn["id"], frequency="yearly",
                                     first_due_date="2025-05-01"))
    _run_morning_job(client, session, date(2025, 5, 1))
    assert _get_schedule(client, sid)["next_due_date"] == "2026-05-01"


# ── Slice 3: monthly day-31 overflow ─────────────────────────────────────────

def test_monthly_day31_in_february_snaps_to_last_day(client, session, template_txn):
    sid = _schedule_id(make_schedule(client, template_txn["id"], frequency="monthly",
                                     day_of_period=31, first_due_date="2025-01-31"))
    _run_morning_job(client, session, date(2025, 1, 31))
    assert _get_schedule(client, sid)["next_due_date"] == "2025-02-28"


def test_monthly_day31_in_30day_month_snaps_to_30(client, session, template_txn):
    sid = _schedule_id(make_schedule(client, template_txn["id"], frequency="monthly",
                                     day_of_period=31, first_due_date="2025-03-31"))
    _run_morning_job(client, session, date(2025, 3, 31))
    assert _get_schedule(client, sid)["next_due_date"] == "2025-04-30"


# ── Slice 4: GET /recurring/due-today ────────────────────────────────────────

def test_due_today_shows_pending_queue_items(client, session, template_txn):
    today = date.today()
    make_schedule(client, template_txn["id"], frequency="daily",
                  first_due_date=today.isoformat())
    _run_morning_job(client, session, today)

    resp = client.get("/recurring/due-today")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
    assert all(i["status"] == "pending" for i in resp.json())


# ── Slice 5: POST /recurring/queue/{id}/confirm ───────────────────────────────

def test_confirm_creates_posted_transaction(client, session, template_txn):
    # Ensure a FY covering today exists so the clone can find one
    today = date.today()
    client.post("/financial-years", json={
        "start_date": f"{today.year}-04-01",
        "end_date": f"{today.year + 1}-03-31",
    })
    make_schedule(client, template_txn["id"], frequency="daily",
                  first_due_date=today.isoformat())
    _run_morning_job(client, session, today)

    item = client.get("/recurring/due-today").json()[0]
    resp = client.post(f"/recurring/queue/{item['id']}/confirm", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "confirmed"
    assert data["posted_transaction_id"] is not None

    # confirmed item no longer appears in due-today
    pending_ids = [i["id"] for i in client.get("/recurring/due-today").json()]
    assert item["id"] not in pending_ids


# ── Slice 6: POST /recurring/queue/{id}/skip ─────────────────────────────────

def test_skip_marks_item_skipped(client, session, template_txn):
    today = date.today()
    make_schedule(client, template_txn["id"], frequency="daily",
                  first_due_date=today.isoformat())
    _run_morning_job(client, session, today)

    item = client.get("/recurring/due-today").json()[0]
    resp = client.post(f"/recurring/queue/{item['id']}/skip")
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"


# ── Slice 7: end_date boundary ───────────────────────────────────────────────

def test_schedule_past_end_date_produces_no_queue_entry(client, session, template_txn):
    sid = _schedule_id(make_schedule(client, template_txn["id"], frequency="daily",
                                     first_due_date="2025-05-01",
                                     end_date="2025-04-30"))
    _run_morning_job(client, session, date(2025, 5, 1))
    # next_due_date should NOT have advanced (no queue entry created)
    s = _get_schedule(client, sid)
    assert s["next_due_date"] == "2025-05-01"


# ── Slice 8: auto_post_pending ───────────────────────────────────────────────

def test_auto_post_pending_creates_auto_posted_transaction(client, session, template_txn):
    from stow.recurring import auto_post_pending

    today = date.today()
    client.post("/financial-years", json={
        "start_date": f"{today.year}-04-01",
        "end_date": f"{today.year + 1}-03-31",
    })
    make_schedule(client, template_txn["id"], frequency="daily",
                  first_due_date=today.isoformat())
    _run_morning_job(client, session, today)

    auto_post_pending(session, today=today)
    session.expire_all()

    items = client.get("/recurring/due-today").json()
    # no pending items remain — all auto-posted
    assert all(i["status"] != "pending" for i in items)
