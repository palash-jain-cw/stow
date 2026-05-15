# ADR 016 — Dashboard

**Status:** Draft  
**Issue:** #14  
**Date:** 2026-05-15

---

## Context

The Dashboard is the primary entry point. Its job is recording a transaction; everything else is opt-in. The mockup (`/mockups/01-dashboard.html`) is the canonical visual reference.

---

## Decisions

### 1. Three-zone accordion — one open at a time, CSS grid animation

**Layout:** `max-w-2xl mx-auto px-6 py-10` (640px wide, single column, as per mockup). Three white rounded-2xl cards stacked vertically with `gap-3`.

**Zones (all collapsed by default):**

| Zone | Icon | Collapsed summary | Data source |
|---|---|---|---|
| "What happened?" | blue plus | "What happened? Record a transaction…" | User input |
| "Needs attention" | amber bell | Count badge of pending items | `GET /recurring/due-today`, `GET /investments/fds/maturing-soon?days=30`, account balances |
| "Recent activity" | zinc clock | Last added date + total count | `GET /transactions?limit=10` |

**Expand behaviour:** Click collapsed header → open that zone; if another zone was open, close it. CSS grid `grid-template-rows: 0fr → 1fr` transition (300ms ease) for smooth height animation. Chevron rotates 180° when open.

**"What happened?" zone special case:** clicking the collapsed line opens it in-place (no header toggle bar — the whole card is the click target). Clicking outside or Cancel closes it.

---

### 2. Data strategy — separate queries, account list does double duty

**Queries on mount:**
- `GET /financial-years` → active FY (for FY badge in header and `fy_id` for other calls)
- `GET /transactions?limit=10` → recent activity zone
- `GET /recurring/due-today` → needs-attention items
- `GET /investments/fds/maturing-soon?days=30` → needs-attention FD alerts
- `GET /accounts` → accounts list (used for net worth, cash balance, and GST liability — all computed client-side)

**Computed on client from accounts list:**
- **Net worth** = sum of all asset-type account balances − sum of all liability-type account balances
- **Cash & bank** = sum of accounts in "Bank Accounts" + "Cash in Hand" groups
- **GST net liability** = sum of Output GST account balances − sum of Input GST account balances (filter by account names containing "Output" / "Input" in "Duties & Taxes" group)

All queries use TanStack Query with `staleTime: 30_000`. Loading states per zone (skeleton rows), not a page-level spinner.

---

### 3. Header — time-based greeting + FY badge

```
Good morning, Palash          ← time-based: morning / afternoon / evening
Thursday, 15 May · FY 2025–26  ← day + date, FY badge in blue-50/blue-600
```

Greeting is computed from `new Date()` in IST (client-side, no API call). FY badge shows the active FY's label; clicking it does nothing for now (FY switching is a Settings concern).

---

### 4. "What happened?" zone — NL entry flow

1. User types in textarea, clicks **Interpret** → `POST /ai/parse-transaction` with `{ text }` body
2. Loading state: button spinner + "Thinking…" copy (per MASTER.md tone)
3. On success: open `<Sheet>` with the parsed transaction pre-filled for review → user confirms → `POST /transactions`
4. On error: inline error message below textarea ("Hmm, I got a bit confused. Could you be a little more specific?")
5. **Manual entry** button: opens the same `<Sheet>` with no pre-fill

The confirm Sheet is a local implementation for now (date, amount, narration, type display with a Confirm button). It will be replaced by the full `<TransactionEntrySheet>` from #15 without changing this zone's wiring.

---

### 5. "Needs attention" zone — item types

| Source | Colour | Icon | CTA |
|---|---|---|---|
| FD maturing ≤ 30 days | amber-50 / amber | clock | "View →" → `/portfolio` |
| Recurring due today | blue-50 / blue | repeat | "Review →" → `/transactions` |
| GST net payable > 0 | violet-50 / violet | receipt | "Record it →" opens entry zone |

Items sorted: FDs maturing soonest first, then recurring, then GST. If count is 0 the zone header shows no badge and "All clear" copy when expanded.

---

### 6. "Recent activity" zone

- Last 10 transactions: date (short format "14 May"), narration, `<TxnBadge>`, `<MonoAmount>`
- Clicking a row → navigate to `/transactions` (full list, no row-level sheet here)
- "See all N transactions →" link at bottom
- Empty state: "Your ledger is patiently waiting." (MASTER.md copy)

---

### 7. Footer — always visible, below the zones

Two figures, side by side, quiet:
- Left: "Net worth" label + IBM Plex Mono value
- Right: "Cash across N accounts" label + IBM Plex Mono value

No card/border — just text sitting below the zones with `pt-4`.

---

## Consequences

- All balance-derived metrics are computed client-side; they will be slightly wrong if account types are not correctly seeded, but this is acceptable for a local single-user app.
- `<TransactionEntrySheet>` from #15 is stubbed here; #15 replaces the stub without touching Dashboard logic.
- No chart on the Dashboard (the MASTER.md bar chart is deferred — it requires a charting library not yet installed).
