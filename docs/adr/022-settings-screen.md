# ADR 022 — Settings Screen

**Status:** Accepted
**Issue:** #20
**Date:** 2026-05-16

---

## Context

Issue #20 covers four settings panels. Several API mismatches vs the issue spec exist:
- `FinancialYear` model has no `transaction_count` or `locked_at` — omit those columns.
- No `POST /opening-balances/bulk` endpoint — use individual `PUT /accounts/{id}/opening-balance` per account.
- `ScheduleOut` has no `narration` — fetch template transactions in parallel to show narration.
- `RuleOut` has no `times_used` — omit that column.

---

## Decisions

### 1. Layout

Two-panel layout: left nav strip (w-48, border-r) listing the four panels; right content (`flex-1`). Panel selected via `useSearchParams` `?panel=fy` (default).

### 2. Financial Years panel

**List**: fetch `GET /financial-years`, order by `start_date` desc. Display FY label as `FY {start_year}–{end_year_2d}`. Status badge: `active` → emerald, `locked` → zinc, `open` → blue. Show date range only (no transaction count — not available in API).

Active FY row shows two buttons: "Opening balances" and "Lock year". Locked FY rows show "View reports" link (`/reports?tab=pl`).

**New FY modal**: suggest next FY start = last FY end date + 1 day (April 1 of next year), end = March 31 following year. Submit `POST /financial-years` with `{start_date, end_date, status: 'open'}`. After success invalidate `financialYears.all()` query.

**Opening balances modal**: fetch `GET /accounts`, filter to non-income/expense nature accounts (asset, liability, equity). Group by `group_name`. For each account show a rupee input (convert to/from paise). Live balance check: `sum(asset OBs) − sum(liability OBs) − sum(equity OBs)`. If 0 → "Balanced." (emerald), else show difference (red). Save: individual `PUT /accounts/{id}/opening-balance` calls for all accounts that have a non-zero value. On success close modal + invalidate accounts.

**Lock year modal**: show FY label and net profit estimate (from report or shown as "—" pre-lock). Fetch `GET /financial-years/{id}/pre-lock-check` → `{unposted_depreciation: [...]}` (show warning list if non-empty). Confirm → `POST /financial-years/{id}/lock`. On success invalidate FY list.

### 3. Recurring panel

Fetch `GET /recurring/schedules` → list of `ScheduleOut`. Parallel-fetch each `template_transaction_id` via `GET /transactions/{id}` to get narration.

**Table columns**: Narration | Frequency badge | Next due | Until | Actions (Edit / Stop).

Frequency badge colours: daily=blue, weekly=violet, monthly=emerald, yearly=amber.

**Edit modal**: `frequency` select (daily/weekly/monthly/yearly), `end_date` date input (optional). Submit `PUT /recurring/schedules/{id}` with existing `template_transaction_id` + `first_due_date` = `next_due_date`. No amount field (amount is in template transaction, not schedule).

**Stop modal**: confirmation "Stop {narration}? Past transactions are kept." Confirm → `DELETE /recurring/schedules/{id}` → invalidate schedules query.

Read-only note at bottom: "Recurring transactions are created from the transaction entry sheet."

### 4. Merchant Rules panel

Fetch `GET /merchant-rules` + `GET /accounts` (for account name lookup by id).

**Table columns**: Pattern (monospace, `font-mono text-sm`) | Maps to account | Group/nature | Actions (Edit / Delete).

`times_used` column omitted — not in `RuleOut`.

**Edit**: inline form replacing the row — pattern text input + account select. Submit `PUT /merchant-rules/{id}`.

**Delete**: immediately call `DELETE /merchant-rules/{id}` with undo toast (200ms timeout, "Undo" re-creates via `POST /merchant-rules`). Invalidate on delete (and on failed undo).

Wildcard syntax note at bottom.

### 5. AI / LLM panel

On mount fetch `GET /ai/config` → pre-fill server URL and model name inputs.

**Test connection**: button → `POST /ai/test-connection` → inline status. States:
- idle: grey "Not tested"
- loading: `Loader2` spin + "Testing…"
- ok: emerald `CheckCircle2` + "Connected · {model} · {latency_ms}ms"
- fail: red `XCircle` + error message from `result.error`

**Save**: `POST /ai/config` with `{base_url, model, api_key: ""}`. On success, button shows "Saved" for 1.8s then resets. Invalidate `ai.config()` query.

---

## Consequences

- Transaction count not shown on FY list rows (API doesn't provide it).
- Opening balances modal makes N individual PUT requests (one per non-zero account) — acceptable for personal use.
- Recurring table makes N+1 requests (schedules + one transaction fetch per schedule) — acceptable for < 20 schedules.
- Merchant rule undo uses a 200ms optimistic-delete pattern; undo creates a new rule (different id) rather than restoring the old one — acceptable.
