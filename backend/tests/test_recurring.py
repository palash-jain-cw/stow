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


# ── Slice 8: due-today detail enrichment ──────────────────────────────────────

def test_due_today_includes_transaction_details(client, session, template_txn, bank, expense_account):
    today = date.today()
    make_schedule(client, template_txn["id"], frequency="daily",
                  first_due_date=today.isoformat())
    _run_morning_job(client, session, today)

    resp = client.get("/recurring/due-today")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    item = items[0]
    assert item["narration"] == "Monthly rent"
    assert item["txn_type"] == "payment"
    assert item["amount_paise"] == 5_000_000
    assert item["from_account_name"] == bank["name"]      # bank is credit (money leaves)
    assert item["to_account_name"] == expense_account["name"]  # expense is debit


# ── Slice 9: recurring digest job ─────────────────────────────────────────────

def test_build_digest_text_formats_items():
    from stow.scheduler import _build_digest_text

    class _FakeItem:
        narration = "Monthly rent"
        amount_paise = 5_000_000
        from_account_name = "HDFC Bank"
        to_account_name = "Rent Expense"

    text = _build_digest_text([_FakeItem()])
    assert "Monthly rent" in text
    assert "₹" in text
    assert "HDFC Bank" in text
    assert "Rent Expense" in text


async def test_recurring_digest_sends_message_when_items_due(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    today = date.today()

    # Fake queue item returned by the DB
    fake_item = MagicMock()
    fake_item.schedule_id = 1
    fake_item.due_date = today
    fake_item.status = "pending"

    fake_schedule = MagicMock()
    fake_schedule.template_transaction_id = 10

    fake_txn = MagicMock()
    fake_txn.narration = "Monthly rent"
    fake_txn.type = "payment"

    credit_entry = MagicMock()
    credit_entry.amount = -5_000_000
    credit_entry.account_id = 2

    debit_entry = MagicMock()
    debit_entry.amount = 5_000_000
    debit_entry.account_id = 3

    fake_from_acc = MagicMock()
    fake_from_acc.name = "HDFC Bank"

    fake_to_acc = MagicMock()
    fake_to_acc.name = "Rent Expense"

    fake_user = MagicMock()
    fake_user.telegram_user_id = 123456789

    # exec() is called three times: pending items, entries, telegram users
    exec_results = [
        MagicMock(**{"all.return_value": [fake_item]}),
        MagicMock(**{"all.return_value": [credit_entry, debit_entry]}),
        MagicMock(**{"all.return_value": [fake_user]}),
    ]
    # get() is called four times: schedule, txn, from_acc, to_acc
    get_results = [fake_schedule, fake_txn, fake_from_acc, fake_to_acc]

    mock_session = MagicMock()
    mock_session.exec.side_effect = exec_results
    mock_session.get.side_effect = get_results

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_session)
    mock_cm.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr("stow.scheduler.Session", lambda *a, **kw: mock_cm)

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()
    monkeypatch.setattr("agent.transport.telegram.bot._bot", mock_bot)

    from stow.scheduler import _job_recurring_digest
    await _job_recurring_digest()

    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == 123456789
    assert "Monthly rent" in call_kwargs["text"]


async def test_recurring_digest_silent_when_nothing_due(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    mock_session = MagicMock()
    mock_session.exec.return_value = MagicMock(**{"all.return_value": []})

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_session)
    mock_cm.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr("stow.scheduler.Session", lambda *a, **kw: mock_cm)

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()
    monkeypatch.setattr("agent.transport.telegram.bot._bot", mock_bot)

    from stow.scheduler import _job_recurring_digest
    await _job_recurring_digest()

    mock_bot.send_message.assert_not_called()


def test_recurring_digest_job_is_registered():
    from stow.scheduler import JOB_REGISTRY, SCHEDULES
    assert "recurring_digest" in JOB_REGISTRY
    schedule_ids = {s[0] for s in SCHEDULES}
    assert "recurring_digest" in schedule_ids


# ── Slice 10: auto_post_pending ───────────────────────────────────────────────

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
