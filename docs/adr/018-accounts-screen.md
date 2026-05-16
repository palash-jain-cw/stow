# ADR 018 — Accounts Screen

**Status:** Accepted
**Issue:** #16
**Date:** 2026-05-16

---

## Context

Issue #16 covers the Accounts screen: a two-panel view (collapsible group tree left, detail pane right) plus a New/Edit account sheet. All backend endpoints already exist.

---

## Decisions

### 1. Two-panel layout, self-contained in `Accounts.tsx`

`AccountDetail.tsx` stub is deleted. No React Router sub-routes needed — the two panels live inside one component. Layout: `w-72 shrink-0` left tree + `flex-1` right pane, both with internal scroll, filling `h-full` inside the Shell.

### 2. Left tree — client-side grouping, collapsible, search-filtered

`GET /account-groups` + `GET /accounts` are each fetched once. Accounts are grouped client-side by `group_id`. Groups render in `sort_order` order. Collapse state is `Record<number, boolean>` in local state, default expanded.

Search filters account names (case-insensitive substring). Groups with zero matching accounts hide their rows but still show their header.

Account row: initial avatar chip (first letter, colored by `nature`) + name + `<MonoAmount balance>` right-aligned. Investment accounts replace the balance with a subtype chip (MF / STK / FD / PPF) in `text-cyan-600`.

Nature → chip color: `asset` → blue, `liability` → rose, `equity` → violet, `income` → emerald, `expense` → red.

### 3. Right pane — detail card or empty state

No account selected → `<EmptyState>` + "New Account" button.

Account selected → detail card with:
- Header: 40px avatar chip + name + `group_name · nature`
- 2-col stats: Current balance (`<MonoAmount>`) + "View transactions →" link (no count — avoids extra fetch)
- Detail rows: Cash flow tag (from account groups list), Opening balance (`<MonoAmount>`, lazy fetch)
- Conditional rows: Depreciation rate if set, investment subtype + price source if set
- Actions: View transactions (blue), Edit account, Archive/Unarchive (zinc-400)

Opening balance is fetched lazily via `GET /accounts/{id}/opening-balance?fy_id=…` only when an account is selected and an active FY is known.

### 4. Archive confirmation

Inline confirmation replaces the action row (no modal): "Archive [name]? Archived accounts are hidden from entry sheets." + Cancel / Archive (red) buttons.

### 5. AccountSheet component

New file `components/AccountSheet.tsx`. Handles both new and edit mode (prop: `account?: AccountOut`).

| Field | Default visible | Condition |
|---|---|---|
| Name | ✓ | |
| Group (select) | ✓ | |
| Cash flow tag | "More details" accordion | |
| Depreciation rate + presets | auto-expanded | group name contains "fixed" (case-insensitive) |
| Investment type pills | auto-expanded | group name contains "invest" (case-insensitive) |
| Opening balance | "More details" accordion | |

Depreciation presets: Computer 40%, Furniture 10%, Vehicle 15%, General 15%. Selecting a preset writes the rate input.

Save flow:
1. `POST /accounts` or `PUT /accounts/{id}`
2. If opening balance paise ≠ 0: `PUT /accounts/{id}/opening-balance`
3. Invalidate `queryKeys.accounts.list()`

### 6. Query keys

`queryKeys.accounts` already has `list()`, `detail()`, `ledger()`. Adding:
```ts
openingBalance: (id: number) => ['accounts', id, 'opening-balance'] as const
```

---

## Consequences

- `AccountDetail.tsx` is deleted; its route is removed from `App.tsx`.
- Transaction count is not shown in the detail card — the link to `/transactions?account_id=X` is sufficient.
- Opening balance fetch is one lazy request per account selection (small, local, acceptable).
