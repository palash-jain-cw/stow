# Stow — Design System Master

> When building a specific page, first check `design-system/stow/pages/[page-name].md`.
> If that file exists, its rules **override** this Master. If not, follow this file exclusively.

---

## Design Principles (Non-Negotiable)

1. **Frictionless data entry** — The minimum viable transaction is: amount + narration. Everything else (account, date, tags, attachments) can be added later or enriched by AI. Never block the user from saving an incomplete entry.
2. **Progressive disclosure** — Show only what is needed for the current task. Advanced options, secondary fields, and AI suggestions expand on demand. Never show everything at once.
3. **Playful empty & loading states** — Loading spinners and empty states use warm, friendly copy (see Tone section). No "No data found." ever.
4. **Tooltips everywhere** — Every piece of accounting terminology, every field that could confuse a non-accountant, gets a `?` tooltip with a plain English explanation.
5. **No technical IDs on screen** — User-facing references use Transaction Numbers (`PAY-2025-001`), Account names, or human dates. Database UUIDs never appear in the UI.

---

## Visual Language

### Color Palette

| Role | Light Mode | Dark Mode | Usage |
|------|-----------|-----------|-------|
| Background | `#FAFAFA` (zinc-50) | `#09090B` (zinc-950) | Page background |
| Surface | `#FFFFFF` | `#18181B` (zinc-900) | Cards, panels, sidebar |
| Border | `#E4E4E7` (zinc-200) | `#27272A` (zinc-800) | Dividers, input borders |
| Text Primary | `#09090B` (zinc-950) | `#FAFAFA` (zinc-50) | Headings, labels |
| Text Muted | `#71717A` (zinc-500) | `#A1A1AA` (zinc-400) | Subtitles, helper text |
| Accent / CTA | `#2563EB` (blue-600) | `#3B82F6` (blue-500) | Buttons, links, focus rings |
| Income / Credit | `#059669` (emerald-600) | `#10B981` (emerald-500) | Positive amounts |
| Expense / Debit | `#DC2626` (red-600) | `#EF4444` (red-500) | Negative amounts |
| Warning | `#D97706` (amber-600) | `#F59E0B` (amber-500) | FD maturity, year-end tasks |
| GST | `#7C3AED` (violet-600) | `#8B5CF6` (violet-500) | GST-related accounts |
| Investments | `#0891B2` (cyan-600) | `#06B6D4` (cyan-500) | Investment accounts |

**Color semantics:**
- Amount > 0 (credit / income) → emerald
- Amount < 0 (debit / expense) → red
- Neutral / transfer → zinc text
- Never use color as the only indicator — always pair with a label or icon

### Typography

| Role | Font | Weight | Size |
|------|------|--------|------|
| Page title | IBM Plex Sans | 700 | 24px |
| Section header | IBM Plex Sans | 600 | 18px |
| Card header | IBM Plex Sans | 600 | 16px |
| Body / labels | IBM Plex Sans | 400 | 14px |
| Helper / muted | IBM Plex Sans | 400 | 12px |
| **Financial figures** | **IBM Plex Mono** | **500** | **14px** |
| **Large KPI numbers** | **IBM Plex Mono** | **700** | **28px** |

> IBM Plex Mono is mandatory for all monetary amounts, account balances, and numeric report data. Monospaced digits align in tables and look precise — this is a trust signal in financial software.

**Google Fonts import:**
```css
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');
```

### Spacing Scale

| Token | Value | Usage |
|-------|-------|-------|
| `space-1` | 4px | Tight icon gaps |
| `space-2` | 8px | Inline spacing, badge padding |
| `space-3` | 12px | Input padding |
| `space-4` | 16px | Card inner padding |
| `space-6` | 24px | Section padding |
| `space-8` | 32px | Page section gap |

### Shadows

| Level | Value | Usage |
|-------|-------|-------|
| `shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle card lift |
| `shadow-md` | `0 4px 6px rgba(0,0,0,0.07)` | Panels, dropdowns |
| `shadow-lg` | `0 10px 15px rgba(0,0,0,0.1)` | Modals, sheets |

---

## Layout Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  SIDEBAR (240px, collapsible to 56px)                           │
│  ┌──────┐ ┌─────────────────────────────────────────────────┐  │
│  │ Nav  │ │ HEADER (56px): Breadcrumb | FY badge | + button │  │
│  │      │ ├─────────────────────────────────────────────────┤  │
│  │      │ │                                                 │  │
│  │      │ │  MAIN CONTENT (fluid, max-w-7xl, px-6)          │  │
│  │      │ │                                                 │  │
│  └──────┘ └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

- Sidebar width: 240px expanded / 56px icon-only (toggle button at bottom)
- Header: sticky, 56px tall, shows current page title + FY badge + primary CTA
- Content: `max-w-7xl mx-auto px-6 py-6`
- Mobile (< 768px): sidebar becomes a bottom sheet or hamburger drawer

### Sidebar Navigation Structure

```
● Dashboard

  BOOKKEEPING
  ├── Transactions
  └── Accounts

  IMPORT
  └── Bank Import

  REPORTS
  ├── Trial Balance
  ├── Balance Sheet
  ├── Profit & Loss
  ├── Cash Flow
  └── Capital Gains

  INVESTMENTS
  └── Portfolio

  SETTINGS (bottom, separated)
  ├── Financial Years
  ├── Merchant Rules
  └── AI & Import
```

---

## Component Library (shadcn/ui based)

### Transaction Type Badges

```
PAY  → red-100 text-red-700 (Payment — money out)
REC  → emerald-100 text-emerald-700 (Receipt — money in)
JNL  → blue-100 text-blue-700 (Journal — adjustment)
CTR  → zinc-100 text-zinc-700 (Contra — transfer)
```

### Amount Display

Always use IBM Plex Mono. Prefix with `₹`. Align right in tables.
- Positive (credit/income): emerald color
- Negative (debit/expense): red color
- Neutral: zinc primary

### Status Badges (Staging Area)

```
pending     → amber-100 text-amber-700
confirmed   → emerald-100 text-emerald-700
discarded   → zinc-100 text-zinc-500 line-through
reconciled  → blue-100 text-blue-700
duplicate   → red-100 text-red-700 + warning icon
```

### FY Badge (Header)

Pill showing current FY: `FY 2025–26` in blue-50 text-blue-700. Clickable to switch.

---

## Screen Designs

### 1. Dashboard

**Purpose:** At-a-glance financial health. The home base.

**Layout:**
```
┌─ Header: "Good morning" | FY 2025-26 | [+ Add Transaction] ──────┐
│                                                                    │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────┐  │
│ │Net Worth │ │ Income   │ │ Expenses │ │   GST Liability      │  │
│ │(this FY) │ │(30 days) │ │(30 days) │ │ Output − Input GST   │  │
│ └──────────┘ └──────────┘ └──────────┘ └──────────────────────┘  │
│                                                                    │
│ ┌─── Monthly Overview (bar chart) ────┐ ┌─── Quick Entry ──────┐ │
│ │ Income vs Expenses by month (12mo)  │ │ "What happened?" ... │ │
│ │ Recharts BarChart, emerald/red bars │ │ [Interpret with AI]  │ │
│ └─────────────────────────────────────┘ └─────────────────────-┘ │
│                                                                    │
│ ┌─── Recent Transactions ─────────────────────────────────────┐  │
│ │ Date | Narration | Type | Amount | Account           [View]  │  │
│ │ (last 8, truncated, click row → detail sheet)               │  │
│ └─────────────────────────────────────────────────────────────┘  │
│                                                                    │
│ ┌── Upcoming ─────────────────┐  ┌── Bank Accounts ───────────┐  │
│ │ FD maturities (amber)       │  │ Account name | Balance      │  │
│ │ Year-end tasks (if near)    │  │ (all Bank Accounts group)   │  │
│ └─────────────────────────────┘  └────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

**Stat cards:** Large KPI number (IBM Plex Mono 28px/700), label below (12px muted), trend arrow vs last month.

**Quick Entry box:** Single textarea. Placeholder: *"e.g. paid electricity bill ₹2400 from HDFC"*. On submit shows spinner, then slides open the confirm sheet.

**Empty state:** *"Your books are a blank canvas. Add your first transaction to get started."*

---

### 2. Transactions

**Purpose:** Browse, search, and manage all transactions.

**Layout:**
```
┌─ Transactions ──────────────────────────── [+ New Transaction ▾] ┐
│                                                                    │
│ [Search narration...]  [Date range ▾]  [Type ▾]  [Account ▾]  [Tags ▾] │
│                                                                    │
│ □ | Date     | Narration            | Type | Amount    | Account  │
│ ─────────────────────────────────────────────────────────────────  │
│ □ | 12 May   | Electricity bill     | PAY  | ₹2,400 ↓ | HDFC Bank│
│ □ | 11 May   | Salary credit        | REC  | ₹85,000 ↑| HDFC Bank│
│ □ | 10 May   | Transfer to savings  | CTR  | ₹20,000   | Axis Bank│
│ ...                                                                │
│                                                                    │
│ [Bulk action bar — appears on selection: Delete | Add Tag]        │
└────────────────────────────────────────────────────────────────────┘
```

**New Transaction dropdown:** `Manual Entry` | `Describe it to AI`

**Row click:** Opens a right-side sheet showing full transaction detail (entries table, tags, attachment, audit log link).

**Empty state:** *"Nothing here yet — your ledger is patiently waiting."*

**Amount display:** `₹` prefix, right-aligned, emerald for credit/income, red for debit/expense.

**No technical IDs:** Transaction number (`PAY-2025-001`) shown instead of DB ID.

---

### 3. Transaction Entry — Manual

**Progressive disclosure in 3 steps:**

```
Step 1 (always visible):
┌────────────────────────────────────────────────┐
│ What kind of transaction?                      │
│ [Payment] [Receipt] [Journal] [Contra]         │
│                                                │
│ ₹ [Amount...............]  [Date: today ▾]    │
│ Narration: [.................................]  │
│                                               │
│                          [Quick Save] [More ▾] │
└────────────────────────────────────────────────┘

Step 2 (expand "More"):
┌────────────────────────────────────────────────┐
│ Accounts                                       │
│ From: [HDFC Bank ▾ ?]  To: [Electricity ▾ ?]  │
│                                                │
│ Tags: [freelance ×] [+ add tag]                │
│ Attach: [+ Add receipt]                        │
│                                               │
│                         [Save] [Cancel]        │
└────────────────────────────────────────────────┘

Step 3 (Journal only — multi-leg entries):
┌────────────────────────────────────────────────┐
│ Entries           Account        Dr      Cr    │
│ ─────────────────────────────────────────────  │
│ 1. [Account ▾]    Electricity  2,400           │
│ 2. [Account ▾]    HDFC Bank           2,400    │
│ [+ Add entry]                                  │
│                                                │
│ Balance: ✓ Balanced         [Save] [Cancel]    │
└────────────────────────────────────────────────┘
```

**Tooltip example on "From" field:** *"The account money is leaving — usually your bank or cash account"*

**Quick Save:** Saves with sensible defaults (today's date, last used accounts). User can enrich later.

**Balance indicator:** Real-time. Shows `✓ Balanced` in emerald or `⚠ ₹400 short` in red.

---

### 4. Transaction Entry — Natural Language (AI)

```
┌─ Describe your transaction ────────────────────────────────────┐
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ paid electricity bill 2400 from hdfc last tuesday        │   │
│  │                                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                    [Interpret →]               │
│                                                                 │
│  ── AI understood this as ────────────────────────────────     │
│  Type: Payment       Date: 13 May 2025                         │
│  Amount: ₹2,400      Narration: Electricity bill               │
│  From: HDFC Bank     To: Electricity Expense                   │
│                                                                 │
│  [Edit any field]                  [Confirm & Save]            │
└─────────────────────────────────────────────────────────────────┘
```

**Loading state copy:** *"Thinking... making sense of your words"*

**Error state:** *"Hmm, I got a bit confused. Could you be a little more specific?"*

---

### 5. Accounts

**Layout: two-panel**

```
┌─ Accounts ──────────────────────────── [+ New Account] ──────┐
│                                                               │
│ LEFT: Account Group Tree          RIGHT: Account Detail       │
│ ───────────────────────           ─────────────────────────  │
│ ▼ Current Assets                  HDFC Bank                  │
│   ● HDFC Bank        ←selected    Group: Bank Accounts        │
│   ● Axis Bank                     Balance: ₹1,24,500         │
│   ● Cash in Hand                  Cash Flow: Operating       │
│ ▶ Fixed Assets                    Transactions: 142           │
│ ▶ Investments                                                 │
│ ▼ Income                          [View Transactions]         │
│   ● Salary                        [Edit Account]             │
│   ● Freelance                     [Archive Account]          │
│ ...                                                           │
└───────────────────────────────────────────────────────────────┘
```

**New Account sheet (progressive):**
- Required: Name + Group
- Optional (revealed by group type):
  - Fixed Asset → depreciation rate field + tooltip
  - Investment → sub-type picker (Equity MF / Stock / FD / PPF)
  - Any → cash flow tag (pre-filled from group default)

**Empty state:** *"No accounts yet — your chart of accounts is wide open."*

---

### 6. Bank Import

**3-step wizard (one focus per step):**

```
Step 1 — Upload
┌────────────────────────────────────────────────┐
│ Which bank?                                    │
│ [HDFC] [Axis] [BOI] [AU SFB] [Union Bank]     │
│                                                │
│ ┌──────────────────────────────────────────┐  │
│ │   Drop your statement here               │  │
│ │   PDF or CSV — we'll figure it out       │  │
│ │   [Browse files]                         │  │
│ └──────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘

Step 2 — Review (staging area)
┌────────────────────────────────────────────────┐
│ Found 47 transactions · 2 possible duplicates  │
│                                                │
│ □ Date    | Description    | Amt    | Account  │
│ ─────────────────────────────────────────────  │
│ ✓ 1 May   | SALARY CR      |+85,000 | Salary ? │
│ ⚠ 3 May   | HDFC CC PMT    |−15,000 | ? Dup?  │
│ ✓ 4 May   | AMAZON         |−1,299  | Shopping │
│ ...                                            │
│                                                │
│ [Confirm All Clean] [Review Duplicates First]  │
└────────────────────────────────────────────────┘

Step 3 — Confirm
┌────────────────────────────────────────────────┐
│ Ready to post 44 transactions                  │
│ Skipping 2 duplicates · 1 discarded            │
│                                                │
│          [Post to Books]                       │
└────────────────────────────────────────────────┘
```

**Loading state:** *"Reading your statement... this takes a moment"*
**Empty state after import:** *"All caught up! Your books are as fresh as this morning's chai."*

---

### 7. Reports

**Layout:**

```
┌─ Reports ────────────────────────────────────────────────────┐
│                                                              │
│ [Trial Balance] [Balance Sheet] [P&L] [Cash Flow] [Cap Gains]│
│                          ← tab bar                          │
│ Date: [1 Apr 2025] to [today ▾]    [Filter by tag ▾]        │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐    │
│ │  PROFIT & LOSS — FY 2025-26 (1 Apr – 14 May 2025)   │    │
│ │  ────────────────────────────────────────────────    │    │
│ │  INCOME                                              │    │
│ │    Direct Income                        ₹85,000      │    │
│ │      Salary                             ₹85,000      │    │
│ │  TOTAL INCOME                           ₹85,000      │    │
│ │                                                      │    │
│ │  EXPENSES                                            │    │
│ │    Indirect Expenses                    ₹12,450      │    │
│ │      Electricity                         ₹2,400      │    │
│ │      ...                                             │    │
│ │  TOTAL EXPENSES                         ₹12,450      │    │
│ │  ────────────────────────────────────────────────    │    │
│ │  NET PROFIT                             ₹72,550      │    │
│ └──────────────────────────────────────────────────┘  [↓ PDF]│
└──────────────────────────────────────────────────────────────┘
```

**Empty state:** *"No data for this period yet — add some transactions and come back."*

**Account names in reports are clickable** → navigates to that account's transaction list.

---

### 8. Portfolio (Investments)

**Tab bar:** `Equity MFs` | `Stocks` | `FDs` | `PPF`

**Equity MF / Stocks tab:**
```
┌─ Equity Mutual Funds ─────────────────── [+ Add Purchase] ──┐
│                                                              │
│ Fund / Stock     | Units  | Avg Cost | Invested  | P&L      │
│ Mirae Asset Lg.  | 150.25 | ₹52.40  | ₹7,873    | —        │
│ HDFC Top 100     | 80.00  | ₹892.00 | ₹71,360   | —        │
│                                                              │
│ Capital Gains Summary (FY 2025-26)                          │
│   STCG: ₹12,400  LTCG: ₹8,200  Exempt: ₹1,25,000          │
│                                         [View Full Report]  │
└──────────────────────────────────────────────────────────────┘
```

**FD tab:**
```
┌─ Fixed Deposits ─────────────────────── [+ Add FD] ─────────┐
│ Bank      | Principal | Rate  | Maturity     | Status        │
│ HDFC Bank | ₹1,00,000 | 7.1%  | 12 Jun 2025  | ⚠ Maturing  │
│ Axis Bank | ₹50,000   | 7.4%  | 14 Jan 2026  | Active       │
└──────────────────────────────────────────────────────────────┘
```

---

### 9. Settings

**Tabs:** `Financial Years` | `Merchant Rules` | `AI & Import` | `Depreciation`

**Financial Years:**
```
FY 2025–26   Active   [Lock Year]
FY 2024–25   Locked   [View]
[+ New Financial Year]
```

**AI & Import:**
```
LLM Endpoint  [http://localhost:11434/v1     ]  [?]
Model Name    [qwen3:7b                      ]  [?]
              [Test Connection]
```

---

## Tone & Copy Guidelines

| Situation | Copy |
|---|---|
| Loading data | *"Crunching the numbers..."* |
| Loading AI | *"Thinking... making sense of your words"* |
| Importing statement | *"Reading your statement... this takes a moment"* |
| No transactions | *"Your ledger is patiently waiting."* |
| No accounts | *"Your chart of accounts is wide open."* |
| Import complete | *"All caught up! Fresh as morning chai."* |
| FY locked | *"This year is sealed. History preserved."* |
| Balance error | *"Something doesn't add up — literally."* |
| Balanced | *"Perfectly balanced, as all things should be."* |
| Saving | *"Saving..."* |
| Saved | *"Saved."* |

---

## Accessibility

- All monetary fields: `aria-label="Amount in rupees"`
- Tooltip trigger: `aria-describedby` pointing to tooltip content
- Transaction type badges: include text, not just color
- Reports: provide `<table>` with proper `<th scope>` headers
- All inputs: `<label>` elements, never placeholder-only
- Focus rings: `ring-2 ring-blue-500 ring-offset-2`
- Skip to main content link at top of every page

---

## Anti-Patterns (Never Do)

- No database UUIDs visible anywhere in the UI
- No "No data found" — use the playful copy above
- No placeholder-only inputs (no label = no go)
- No color as the only differentiator (always pair with icon or label)
- No auto-posting AI suggestions — always confirm first
- No technical accounting jargon without a tooltip
- No modals for multi-step flows — use sheets/drawers
- No emojis as icons — use Lucide icons throughout
