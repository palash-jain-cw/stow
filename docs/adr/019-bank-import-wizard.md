# ADR 019 — Bank Import Wizard

**Status:** Accepted
**Issue:** #17
**Date:** 2026-05-16

---

## Context

Issue #17 covers the 3-step import wizard: Upload → Review → Confirm. The backend parses PDFs synchronously (`POST /imports` returns only when done), so no polling is needed. `POST /imports/{batch_id}/confirm` requires `bank_account_id` and `fy_id`.

---

## Decisions

### 1. Step 1 — Upload

Layout: centered max-w-lg, step indicator in page header.

**Order within step:**
1. **Bank account selector** (first — required before parse). Dropdown of all non-archived accounts. Pre-filters visually to asset-nature accounts but all are selectable. Parse button disabled until account is chosen AND file is picked.
2. **Drop zone** (PDF only). Drag-and-drop + "Browse file". Shows file chip after pick.
3. **"Parse statement" button** → disabled until both account and file are set.
4. **Progress states** — animated cycling messages while `POST /imports` is in-flight (Reading file… → Extracting text… → Identifying bank & format… → Parsing transactions… → Mapping accounts… → Done). Pure cosmetic timer; advance to Step 2 when response arrives.

Only PDF accepted (per backend constraint). Drop zone copy: "PDF · Axis Bank, HDFC, Bank of India, AU Small Finance, Union Bank".

### 2. Step 2 — Review

Sub-header (shrink-0): detected bank · statement period (from `BatchOut`).

Filter chips: **All N** / **New N** (pending, non-duplicate) / **Duplicates N** (possible_duplicate, any status) / **Matched N** (reconciled).

Table columns: Date | Description | Amount | Account dropdown | Status badge | Expand chevron.

Inline expansion (one open at a time, CSS grid 0fr → 1fr):
- **New rows:** narration input (pre-filled or description) + tags input; Accept / Ignore buttons. Accept disabled if no account selected. Accept sets status → confirmed, Ignore sets status → discarded.
- **Duplicate rows:** amber panel with warning + "Skip (it's a duplicate)" / "Import anyway".
- **Matched rows:** emerald note, no actions.

Row edits are optimistic: local state updated immediately, `PUT /imports/{batch_id}/rows/{row_id}` fires in the background. Narration and tags updates debounced on blur.

Merchant rule tracking: record `{description, accountId}` for any row where `originalAccountId` was null and user sets a non-null account.

Bottom bar: `N accepted · N ignored · N pending` counts. Back | **Review & confirm →** (always enabled).

### 3. Step 3 — Confirm

Summary card:
| Label | Value |
|---|---|
| New transactions | confirmed count |
| Matched (reconciled) | reconciled count |
| Skipped / ignored | discarded + pending count |
| Net inflow | sum of confirmed row amounts (MonoAmount) |

Merchant rule section (only if new mappings exist): checkboxes for each unique description→account pairing. All checked by default.

"Post N transactions" flow:
1. `POST /merchant-rules` for each checked rule
2. `POST /imports/{batch_id}/confirm` with `{ bank_account_id, fy_id: activeFy.id }`
3. → Done screen

### 4. Done screen

Emerald check circle + counts summary + two buttons: "Import another" (reset state to Step 1) + "View transactions" (Link to /transactions).

### 5. api.ts: add upload method

```ts
upload: <T>(path: string, formData: FormData) =>
  fetch(`${BASE}${path}`, { method: 'POST', body: formData })
    .then(res => { if (!res.ok) throw new Error(res.statusText); return res.json() as Promise<T> })
```

No Content-Type header — browser sets multipart boundary automatically.

### 6. State

All local in `Import.tsx`. No TanStack Query after initial rows fetch — rows are managed as `RowDraft[]` local state with optimistic updates.

Queries: `accounts` (for bank account selector + row account dropdowns) and `financialYears` (for active FY id).

---

## Consequences

- The progress bar is decorative (backend is synchronous). If the parse takes longer than the animation, the last step holds until the response arrives.
- Merchant rules are saved before confirm, so future imports benefit immediately.
- CSV import is not supported (backend constraint); the UI says PDF only.
