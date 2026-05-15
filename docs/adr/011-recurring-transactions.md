# ADR 011 — Recurring Transactions

**Status:** Draft  
**Date:** 2026-05-15  
**Issue:** [#10](https://github.com/palash-jain-cw/stow/issues/10)

---

## Context

Issue #10 adds support for scheduled transaction templates: the user attaches a recurrence schedule to any existing transaction, which then surfaces for review each period and auto-posts if not actioned by end of day.

---

## Decisions

### 1. Models

**`RecurringSchedule`**

```
id
template_transaction_id  INT FK → transaction   # the transaction to clone
frequency                TEXT                   # daily | weekly | monthly | yearly
day_of_period            INT  nullable          # day of month (1–31) for monthly;
                                                #   day of week (0=Mon–6=Sun) for weekly;
                                                #   NULL for daily/yearly
end_date                 DATE nullable          # inclusive; NULL = runs forever
next_due_date            DATE                   # set to first_due_date at creation; advanced after each queue entry
is_active                BOOL default True
```

**`RecurringQueueItem`**

```
id
schedule_id              INT FK → recurring_schedule
due_date                 DATE
status                   TEXT   # pending | confirmed | skipped | auto-posted
posted_transaction_id    INT FK → transaction, nullable
```

### 2. `next_due_date` advancement

After creating a queue entry, `next_due_date` advances according to `frequency`:

| Frequency | Advance by |
|---|---|
| `daily` | + 1 day |
| `weekly` | + 7 days |
| `monthly` | + 1 calendar month, then snap to `day_of_period` with last-day-of-month overflow |
| `yearly` | + 1 calendar year |

**Monthly snap logic** (`day_of_period = D`, `next_due_date` just advanced by one month):
```python
from calendar import monthrange
last_day = monthrange(year, month)[1]
actual_day = min(D, last_day)
next_due_date = next_due_date.replace(day=actual_day)
```

Example: schedule on day 31, advancing from Jan 31 → Feb 28 (in a non-leap year).

### 3. Transaction cloning

When a queue item is confirmed or auto-posted, a new `Transaction` is created by cloning the template:

- Same `type`, `narration`, `tags`
- `date` = queue item's `due_date` (or the override date provided by the user on confirm)
- `fy_id` = looked up from the FY where `start_date <= date <= end_date`; 422 if no active FY covers the date or if the FY is locked
- `entries` = copy of all `Entry` rows on the template transaction (same `account_id`, same `amount`)
- New transaction number assigned via existing `_next_number` logic

### 4. Morning job logic

`create_queue_entries_for_today(session)` — called by APScheduler at 7:00 AM IST:

1. Find all active schedules where `next_due_date <= today` and (`end_date IS NULL OR end_date >= today`).
2. For each: create a `RecurringQueueItem(status="pending", due_date=today)`.
3. Advance `next_due_date` per §2.

This is a standalone async function, not a method — APScheduler calls it directly.

### 5. Midnight job logic

`auto_post_pending(session)` — called by APScheduler at 23:59 IST:

1. Find all queue items where `due_date = today` and `status = "pending"`.
2. For each: clone the template transaction (§3), set `status = "auto-posted"`, set `posted_transaction_id`.

### 6. APScheduler setup

`apscheduler>=4.0` added as a production dependency (APScheduler 4.x `AsyncScheduler`).

Scheduler is created in the FastAPI lifespan and torn down on shutdown:

```python
from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger

async with AsyncScheduler() as scheduler:
    await scheduler.add_schedule(morning_job, CronTrigger(hour=7, minute=0, timezone="Asia/Kolkata"))
    await scheduler.add_schedule(midnight_job, CronTrigger(hour=23, minute=59, timezone="Asia/Kolkata"))
    yield
```

`morning_job` and `midnight_job` are thin wrappers that open a DB session and call the respective logic functions. The logic functions themselves are pure (session-injected), making them directly testable without a running scheduler.

### 7. Testing approach

APScheduler jobs are not tested via HTTP — instead, the job logic functions (`create_queue_entries_for_today`, `auto_post_pending`) are called directly in tests with a test session. This is the correct public interface for background job logic.

HTTP-level tests cover all the REST endpoints (CRUD + confirm/skip).

### 8. API surface

| Method | Path | Description |
|---|---|---|
| `GET` | `/recurring/schedules` | List all active schedules |
| `POST` | `/recurring/schedules` | Attach a schedule to an existing transaction |
| `PUT` | `/recurring/schedules/{id}` | Edit frequency, day, end_date |
| `DELETE` | `/recurring/schedules/{id}` | Deactivate schedule |
| `GET` | `/recurring/due-today` | Pending queue items for today |
| `POST` | `/recurring/queue/{id}/confirm` | Confirm (optionally with overrides); posts transaction |
| `POST` | `/recurring/queue/{id}/skip` | Mark skipped |

`POST /recurring/schedules` body:
```json
{
  "template_transaction_id": 1,
  "frequency": "monthly",
  "day_of_period": 5,
  "first_due_date": "2025-05-05",
  "end_date": null
}
```

`POST /recurring/queue/{id}/confirm` body (all optional — defaults to template values):
```json
{
  "date": "2025-05-06",
  "narration": "Override narration"
}
```

### 9. Data access: direct queries, no repository

Logic is contained in `stow/recurring.py` (job functions + helpers). Route handlers in `stow/routers/recurring.py` call them directly.

---

## Rejected Alternatives

- **Storing recurrence on Transaction directly:** Would conflate the template concept with posted transactions. Separate table is cleaner and allows the template to be edited without affecting posted history.
- **APScheduler 3.x:** Version 4.x `AsyncScheduler` integrates cleanly with `asyncio` and FastAPI's lifespan. 3.x uses `BackgroundScheduler` which needs threading glue.
- **Auto-generating all future queue items on schedule creation:** Unbounded writes; makes end_date changes expensive. Generate one item at a time on the morning job instead.
- **Separate confirm endpoint per edit field:** Single confirm endpoint with optional overrides is simpler and covers all cases.
