# ADR 017 — Transactions List & Entry Sheet

**Status:** Draft  
**Issue:** #15  
**Date:** 2026-05-15

---

## Context

Issue #15 covers two tightly coupled concerns: the transaction list screen and `<TransactionEntrySheet />`, which is also consumed by the Dashboard (NL confirmation flow). Both are driven by the same mockups (`02-transactions.html`, `03-transaction-entry.html`).

---

## Decisions

### 1. Transaction list — full-width, date-grouped, inline row expansion

**Layout:** Full-width content area (`max-w-7xl mx-auto px-6 py-6`). Sticky page header with title + "New Transaction" button.

**Filter bar (always visible):**
- Search input (narration text match, client-side)
- Period quick-select pills: Today / This week / This month / Last month / This FY / All time
- `[Filters ▾]` button expands a panel with type checkboxes (Payment / Receipt / Journal / Contra) and a tag input

**Filter state:** React `useState` only — no URL sync. All filtering is client-side against the full fetched transaction list. `GET /transactions` is called once with no params and cached; filter changes don't trigger re-fetches.

**Date grouping:** Transactions sorted by date descending, grouped by date header ("14 May 2025"). Each group shows its rows below the header.

**Row:** date (within group, shown as day-of-month only) | narration | `<TxnBadge>` | `<MonoAmount>` (credit positive, debit negative) | account name (primary entry)

**Inline expansion:** Clicking a row expands it in-place (CSS grid `0fr → 1fr`). Only one row open at a time. Expanded panel shows:
- Entries table (Account | Dr | Cr) with `<MonoAmount>`
- Tags as chips
- Transaction number (`PAY-2026-001`) — not the DB id
- Edit and Delete action buttons
- Audit log accordion (collapses by default, fetches `GET /transactions/{id}/audit-log` on open)

**Two empty states:**
- No transactions at all: "Your ledger is patiently waiting." + icon
- Filters active, no results: "Nothing matches — try adjusting your filters."

---

### 2. `<TransactionEntrySheet />` — standalone shared component

Lives at `components/TransactionEntrySheet.tsx`. Accepts:

```ts
interface TransactionEntrySheetProps {
  open: boolean
  onClose: () => void
  prefill?: Partial<TransactionDraft>  // from NL parse result
  editTxn?: TransactionOut             // edit mode
  onSaved: () => void                  // called after successful save
}
```

Used by: Dashboard (Manual entry + NL confirmation), Transactions list ("New Transaction" + row Edit).

---

### 3. Entry amount convention — From = −X, To = +X

For Payment, Receipt, and Contra, two accounts are selected: **From** and **To**.

| Type | From label | To label | From entry amount | To entry amount |
|---|---|---|---|---|
| Payment | From account (bank) | To account (expense) | −amount (credit) | +amount (debit) |
| Receipt | From account (income) | To account (bank) | −amount (credit) | +amount (debit) |
| Contra | From account (bank) | To account (bank) | −amount (credit) | +amount (debit) |

The "From" account is always credited (money leaves it), the "To" account is always debited (money arrives). This is consistent across all three types.

For **Journal**, the user directly enters Dr/Cr amounts per entry. Dr → positive amount, Cr → negative amount.

---

### 4. Journal mode — freeform entries with live balance indicator

When type = Journal:
- Amount field replaced by a multi-row entries table (Account | Dr | Cr)
- Narration and Date remain
- "+ Add entry" appends a blank row
- Live balance: `sum(all entry amounts)`. If 0 → "Perfectly balanced, as all things should be." (emerald). If ≠ 0 → "Something doesn't add up — literally. ₹X short." (red with the difference amount)
- Save button disabled when unbalanced

---

### 5. Recurring — two-step save

When repeat ≠ "none":
1. `POST /transactions` → get `transaction.id`
2. `POST /recurring/schedules` with `{ template_transaction_id: id, frequency, first_due_date, end_date? }`

`first_due_date` is derived from the transaction date + frequency offset (e.g. Monthly + 1st → next 1st of month after the transaction date). The "On day" selector maps to `day_of_period`.

If step 2 fails, show an error but keep the transaction (don't roll back — the user can set up recurrence from settings).

---

### 6. Backend: add `account_name` to `EntryOut`

Currently `EntryOut` has `account_id` and `amount` only. Displaying entry rows in the UI requires joining against the accounts list client-side, which is awkward.

**Decision:** Add `account_name: str` to `EntryOut` in `transactions.py`. The router already fetches entries from the session; adding a session lookup for the account name at that point adds one query per entry but keeps the frontend simple. This is acceptable for a local single-user app.

---

### 7. Edit mode

When `editTxn` is provided:
- Sheet title: "Edit Transaction"
- All fields pre-filled from the transaction
- Footer: Cancel | Save (no "More details" toggle — details always expanded in edit mode)
- Save calls `PUT /transactions/{id}`
- Audit log link shown if `GET /transactions/{id}/audit-log` returns any entries

---

## Consequences

- All filtering is client-side; for a single-user local app with < 10,000 transactions this is fine.
- `<TransactionEntrySheet />` is now the canonical entry point for all transaction creation — the stub in Dashboard's review sheet is replaced.
- `account_name` in `EntryOut` is a small backend change that avoids a client-side join on every transaction row render.
