# ADR 023 — First-run Onboarding Wizard

**Status:** Accepted
**Issue:** #22
**Date:** 2026-05-16

---

## Context

Issue #22 covers a first-run wizard shown when no financial year exists. All required backend endpoints are already implemented; this is a pure frontend change.

---

## Decisions

### 1. Trigger & route guard

`/onboarding` route sits outside the Shell (no sidebar). A `<RequireSetup>` wrapper component wraps the Shell routes: it fetches `GET /financial-years` and, if the result is empty, calls `navigate('/onboarding', { replace: true })`. Stale time is 0 so it always checks on mount.

Reverse guard inside `Onboarding.tsx`: if FYs already exist on load, `navigate('/', { replace: true })`.

### 2. Step state

All wizard state is local to `Onboarding.tsx` — no URL params. The flow is strictly linear (back button not supported; users can skip). State shape:

```ts
interface WizardState {
  step: 1 | 2 | 3 | 4 | 5 | 6
  selectedFyStartYear: number   // e.g. 2025 → Apr 1 2025 – Mar 31 2026
  fyId: number | null
  fyStartDate: string           // ISO, used for opening balance label
  fyLabel: string               // "FY 2025–26"
  bankNames: string[]           // one entry per bank input row
  addCash: boolean
  createdAccounts: Array<{ id: number; name: string }>
  llmConfigured: boolean
  llmModel: string
}
```

### 3. FY suggestion

```ts
const today = new Date()
const fyStartYear = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1
// Offer: fyStartYear, fyStartYear - 1, fyStartYear - 2
```

`POST /financial-years` body: `{ start_date: "{year}-04-01", end_date: "{year+1}-03-31", status: "active" }`.

### 4. Account groups

Fetch `GET /account-groups` at wizard start (cached). Find "Bank Accounts" and "Cash-in-Hand" groups by name for `POST /accounts`.

### 5. Opening balances step

Only rendered if `createdAccounts.length > 0`. No balance check (equity side unknown at first run). Individual `PUT /accounts/{id}/opening-balance` calls for non-zero amounts.

### 6. Layout

Full-screen white background, no shell. Centered card `max-w-lg`. Progress dots at top (6 dots). Step transitions are immediate (no animation needed).

---

## Files changed

- `src/pages/Onboarding.tsx` — new wizard component
- `src/components/RequireSetup.tsx` — route guard
- `src/App.tsx` — add `/onboarding` route, wrap shell routes with `<RequireSetup>`
