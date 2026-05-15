# ADR 012 — Background Scheduler (Price Fetches & Recurring Transactions)

**Status:** Accepted  
**Date:** 2026-05-15  
**Issue:** [#21](https://github.com/palash-jain-cw/stow/issues/21)

---

## Context

Issue #10 wired a basic `AsyncScheduler` into the FastAPI lifespan with two naive-UTC cron jobs. Issue #21 productionises this: correct IST timezone, adds the price-fetch job, adds job-level error handling, and exposes a management API for manual triggering and introspection.

---

## Decisions

### 1. Timezone

All `CronTrigger` instances use `timezone="Asia/Kolkata"`. APScheduler 4.x passes this directly to `zoneinfo`.

### 2. Jobs

| ID | Function | Cron (IST) | Description |
|----|----------|-----------|-------------|
| `generate_recurring` | `create_queue_entries_for_today` | `00:05` | Create queue entries for due schedules; advance `next_due_date` |
| `auto_post` | `auto_post_pending` | `00:10` | Auto-post any pending queue items |
| `fetch_prices_evening` | `PriceRepository.fetch_all` | `23:50` | Evening price fetch — stocks and most MF NAVs settle by end of day |
| `fetch_prices_morning` | `PriceRepository.fetch_all` | `09:00` | Morning catch-up — some funds publish NAV the following morning |

The two recurring jobs run at 00:05 and 00:10 so queue entries exist before auto-post attempts them. The two price-fetch jobs are idempotent (upsert on `account_id, quote_date`) so running both on the same calendar day simply overwrites with the fresher value.

Replaces the placeholder UTC jobs added in #10.

### 3. Shared scheduler instance

The `AsyncScheduler` is started in the FastAPI lifespan and stored on `app.state.scheduler`. The `/scheduler` router receives it via a `get_scheduler` dependency:

```python
def get_scheduler(request: Request) -> AsyncScheduler:
    return request.app.state.scheduler
```

### 4. Named schedule IDs

Each `add_schedule` call passes an explicit `id=` string matching the table above (`"generate_recurring"`, `"auto_post"`, `"fetch_prices_evening"`, `"fetch_prices_morning"`). This makes the trigger endpoint deterministic.

### 5. Management API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/scheduler/jobs` | List schedules with `id`, `next_fire_time`, `paused` |
| POST | `/scheduler/jobs/{job_id}/trigger` | Fire a named job immediately via one-shot `DateTrigger` |

`GET /scheduler/jobs` calls `await scheduler.get_schedules()` and returns a stable subset of each `Schedule` object.

`POST /scheduler/jobs/{job_id}/trigger` resolves the function by job ID from a registry dict, then calls `await scheduler.add_schedule(func, DateTrigger(now_utc), id=f"{job_id}__manual__{uuid}")`. Returns `204`.

### 6. Error handling

- **Per-account errors** in `fetch_all()` are already caught and swallowed (existing behaviour).
- **Job-level errors** are caught in the job wrapper with `logging.exception(...)` so the scheduler continues. The wrapper pattern:

```python
async def _guarded(name: str, coro_fn):
    try:
        await coro_fn()
    except Exception:
        logging.exception("Scheduler job %r failed", name)
```

### 7. No persistent job store

In-memory job store is acceptable for single-process deployment. On restart, schedules are re-registered from code. Missed jobs since last run are not replayed (coalesce = latest, which is APScheduler 4.x default).

---

## Consequences

- The `app.state.scheduler` pattern couples the router to the FastAPI `Request` object, which is standard practice.
- Manual trigger creates a separate one-shot schedule entry; it will appear briefly in `GET /scheduler/jobs` until APScheduler cleans it up.
- Replacing the placeholder jobs from #10 is a breaking change to the cron schedule (UTC → IST), but this is intentional and correct.
