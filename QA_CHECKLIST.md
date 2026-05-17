# Stow — QA Checklist

> **Instructions**: Work through each section top to bottom. Mark each item `[x]` when passing, `[!]` for a bug found (add a note inline), and `[-]` to skip. Retest `[!]` items after fixes.
>
> **Prerequisites**: Docker stack running (`docker compose up`), oMLX server running at port 8001, Telegram bot token configured.

---

## 1. Onboarding

> Entry point for new users. Navigate to the app with no existing data.

### 1.1 Welcome Screen
- [ ] Welcome screen renders on first load (no existing FY)
- [ ] "Skip to home" link works and lands on Dashboard
- [ ] "Get started" button advances to Step 2

### 1.2 Financial Year Selection (Step 2)
- [ ] Three year options are displayed with correct date ranges
- [ ] Current FY is marked with a "Current" badge
- [ ] Selecting a year and clicking Next advances to Step 3
- [ ] Selected year is visually highlighted

### 1.3 Bank Accounts Entry (Step 3)
- [ ] At least one account row is shown by default
- [ ] "Add another account" adds a new input row
- [ ] Removing a row removes it from the list (not allowed if only one remains)
- [ ] "Cash-in-hand" checkbox creates a cash account
- [ ] Account names are required — blank names show validation error
- [ ] Duplicate account names show an error
- [ ] Clicking Next with valid accounts advances to Step 4

### 1.4 Opening Balances (Step 4)
- [ ] All accounts created in Step 3 appear as rows
- [ ] Amount inputs accept numeric values
- [ ] Blank/zero values are accepted (optional balances)
- [ ] Amounts display with ₹ symbol
- [ ] Clicking Next saves balances and advances to Step 5

### 1.5 AI / LLM Configuration (Step 5)
- [ ] Server URL, Model name, and API key fields are present
- [ ] "Test connection" button tests the current inputs
- [ ] Success state shows green indicator with latency
- [ ] Failure state shows red indicator with error hint
- [ ] "Skip" advances to Step 6 without saving
- [ ] Saving and continuing advances to Step 6

### 1.6 Completion Summary (Step 6)
- [ ] FY dates shown correctly
- [ ] Account count matches what was created
- [ ] AI status reflects whether config was saved or skipped
- [ ] "Go to dashboard" navigates to `/`
- [ ] "Enter first transaction" opens the transaction entry sheet

---

## 2. Dashboard

### 2.1 Header & Financial Year Banner
- [ ] Greeting changes with time of day (morning / afternoon / evening)
- [ ] Active FY name and dates are displayed correctly
- [ ] FY badge is visible and correctly styled

### 2.2 Summary Cards
- [ ] Net worth = total assets − total liabilities (verify against manual calc)
- [ ] Cash position shows sum of all bank + cash accounts
- [ ] Values update after adding a transaction

### 2.3 Needs Attention Zone
- [ ] Section is collapsible and remembers state on reload
- [ ] **FD maturity alerts**: shows FDs maturing within 30 days with principal, rate, and days remaining
- [ ] **Recurring due today**: shows all recurring transactions due today with narration and amount
- [ ] **GST net payable**: shows correct GST liability net (output − input)
- [ ] If nothing needs attention, section shows an empty/clear state (not a broken UI)

### 2.4 Recent Activity Zone
- [ ] Section is collapsible
- [ ] Shows last 10 transactions grouped by date (descending)
- [ ] Each row shows: type badge, narration, account, amount
- [ ] "See all transactions" link navigates to `/transactions`
- [ ] After deleting a transaction, the list refreshes

### 2.5 Quick Entry
- [ ] "New transaction" button opens the transaction entry sheet
- [ ] Transaction created from dashboard appears in Recent Activity

---

## 3. Transactions

### 3.1 Transaction List
- [ ] All transactions load and are grouped by date (newest first)
- [ ] Each row shows: type badge, narration, primary account, amount
- [ ] Expanding a row shows the full Dr/Cr entry table, tags, transaction number
- [ ] Edit and Delete buttons are visible in the expanded row
- [ ] Audit log section shows timestamped edit history (if the transaction has been edited)

### 3.2 Filters
- [ ] **Search**: typing in narration search filters the list in real-time (case-insensitive)
- [ ] **Period pills**: Today / This week / This month / Last month / This FY / All time — each filters correctly
- [ ] **Type checkboxes**: Payment / Receipt / Journal / Contra — toggling filters the list
- [ ] Combining search + period + type filters works (AND logic)
- [ ] Clearing all filters restores the full list
- [ ] Filter state persists across page refresh (or resets cleanly — document expected behavior)

### 3.3 Creating a Transaction (Manual)
- [ ] "New Transaction" button opens the entry sheet
- [ ] Type dropdown offers: Payment, Receipt, Journal, Contra
- [ ] Date picker defaults to today
- [ ] Narration field is required — blank shows error
- [ ] Account selectors (from/to) show searchable account list
- [ ] Amount field accepts decimal (converts to paise internally)
- [ ] Submitting creates the transaction and closes the sheet
- [ ] New transaction appears at the top of the list
- [ ] Transaction is assigned a unique sequential number
- [ ] Tags field accepts free-form tags

### 3.4 Editing a Transaction
- [ ] Edit button in expanded row opens the sheet pre-filled with existing data
- [ ] All fields are editable
- [ ] Saving the edit updates the transaction in the list
- [ ] An audit log entry is created (visible in expanded row)
- [ ] Editing amount correctly recalculates running balances in account ledgers

### 3.5 Deleting a Transaction
- [ ] Delete button shows a confirmation modal
- [ ] Cancelling the modal keeps the transaction
- [ ] Confirming deletes the transaction and removes it from the list
- [ ] Deleted transaction no longer appears in account ledgers
- [ ] Running balances in affected accounts update correctly

### 3.6 Edge Cases
- [ ] Transaction with zero amount is rejected
- [ ] Entries that don't balance (Dr ≠ Cr) are rejected by the API
- [ ] Very long narration renders without layout breaking
- [ ] Transactions on FY boundary dates (first and last day) are accepted

---

## 4. Accounts

### 4.1 Account Tree (Left Panel)
- [ ] All account groups load (Bank Accounts, Cash-in-Hand, investments, etc.)
- [ ] Groups are collapsible/expandable
- [ ] Account balances display next to account names
- [ ] Investment subtype badges appear (MF, STK, FD, PPF)
- [ ] Search filters account list in real-time
- [ ] "See more" / "See less" toggle works for large groups
- [ ] Archived accounts are visually distinguished or hidden (document expected behavior)

### 4.2 Account Ledger (Right Panel)
- [ ] Clicking an account in the tree loads its ledger
- [ ] Account header shows: name, group, nature, archive status
- [ ] Summary stats: current balance, opening balance, cash flow tag
- [ ] Ledger table shows: Date, Narration, Dr amount, Cr amount, Running balance
- [ ] Running balance is correct for each row (verify first 3 manually)
- [ ] Ledger is empty for a new account (clean state, no error)

### 4.3 Creating an Account
- [ ] "New Account" button opens the account creation sheet
- [ ] Name, Group, and Nature fields are required
- [ ] Group dropdown lists all existing account groups
- [ ] Investment subtype field appears for asset-type accounts
- [ ] Depreciation rate field is present
- [ ] Submitting creates the account and it appears in the tree
- [ ] Duplicate account names are rejected with an error

### 4.4 Editing an Account
- [ ] Edit button opens the sheet pre-filled
- [ ] All fields are editable
- [ ] Saving updates the account in the tree and ledger header

### 4.5 Archiving / Unarchiving
- [ ] Archive button shows a confirmation banner/modal
- [ ] Archived account is visually marked (badge or greyed out)
- [ ] Unarchive button restores the account
- [ ] Archiving an account with a non-zero balance is handled gracefully (warn or block)

### 4.6 View Transactions Button
- [ ] "View Transactions" in the account panel navigates to `/transactions` filtered by that account

---

## 5. Reports

### 5.1 Period Selector
- [ ] FY dropdown lists all financial years
- [ ] Switching FY reloads all report tabs with correct data
- [ ] Active FY is pre-selected by default

### 5.2 Profit & Loss
- [ ] Income groups and accounts display with correct amounts
- [ ] Expense groups and accounts display with correct amounts
- [ ] Total Income, Total Expenses, and Net Profit rows are correct
- [ ] Groups are collapsible
- [ ] Net Profit matches manual calculation (Total Income − Total Expenses)
- [ ] Verify against at least one known transaction

### 5.3 Balance Sheet
- [ ] Assets section lists all asset accounts with balances
- [ ] Liabilities & Equity section is correct
- [ ] Total Assets = Total Liabilities + Equity (balance check indicator passes)
- [ ] Imbalance indicator shows correctly when BS doesn't balance
- [ ] Groups are collapsible
- [ ] Opening balances are included

### 5.4 Trial Balance
- [ ] All accounts listed with Debit and Credit columns
- [ ] Total Debit = Total Credit (balance check)
- [ ] Imbalance shown if totals don't match
- [ ] Accounts with zero balances included or excluded consistently (document)

### 5.5 Cash Flow
- [ ] Operating, Investing, and Financing sections display
- [ ] Each section is collapsible
- [ ] Net Change in Cash is calculated correctly
- [ ] Opening Cash & Bank Balance matches prior-year closing (or opening balance)
- [ ] Closing = Opening + Net Change

### 5.6 Capital Gains
- [ ] STCG section lists lots held < 12 months
- [ ] LTCG section lists lots held ≥ 12 months
- [ ] Each row: units, buy NAV, sale date, gain/loss
- [ ] Total STCG and Total LTCG are correct
- [ ] LTCG exemption (₹1.25L) applied before tax calculation
- [ ] Tax rates correct: STCG (equity), LTCG @ 12.5% above exemption

### 5.7 PDF Export
- [ ] Export button present on P&L, BS, TB, Cash Flow tabs
- [ ] Clicking export triggers a download
- [ ] Downloaded PDF contains the correct report and FY
- [ ] PDF is readable and not corrupted

---

## 6. Portfolio

### 6.1 Allocation Bar
- [ ] Bar shows correct segments for MF, Stock, FD with correct percentages
- [ ] Segment labels show amount and percentage
- [ ] Total invested amount is correct
- [ ] Bar renders when only one asset type is present
- [ ] Bar renders cleanly when portfolio is empty

### 6.2 Equity MF Tab
- [ ] All MF holdings listed with: fund name, units held, NAV, invested, current value, unrealized gain
- [ ] CG type pill shows STCG / LTCG / Mixed correctly
- [ ] Expanding a row shows FIFO lot detail (lot #, units, buy NAV, buy date, age, unrealized gain, CG type)
- [ ] Total row aggregates correctly across all funds
- [ ] Unrealized gain is positive/negative/zero rendered correctly

### 6.3 Stocks Tab
- [ ] Same structure as MF tab — verify independently
- [ ] Stock-specific tax rules applied (STCG at 20%, LTCG at 12.5% above exemption)

### 6.4 Fixed Deposits Tab
- [ ] All FDs listed: name, principal, interest rate, start date, maturity date, accrued interest, status badge
- [ ] Expanding a row shows: tenure, compounding method, maturity amount, days to maturity
- [ ] Status badges: Active (future maturity), Matures in Xd (≤ 30 days), Matured (past date) — each shows correctly
- [ ] Accrued interest calculation is correct (verify one manually)
- [ ] Maturity amount is correct for both simple and compound interest

---

## 7. Settings

### 7.1 Financial Years Panel
- [ ] All FYs listed with correct dates and status badges (Active / Open / Locked)
- [ ] Net profit shown for locked years
- [ ] "New FY" button opens the creation modal with suggested date range
- [ ] Creating a FY with overlapping dates is rejected
- [ ] "Opening balances" button appears only for the active FY
- [ ] Opening balances modal shows all asset/liability/equity accounts
- [ ] Setting opening balances saves and is reflected in account ledgers
- [ ] "Lock year" button appears only for the active FY
- [ ] Pre-lock check runs and shows warnings for unposted depreciation
- [ ] Locking a year transfers net profit and sets status to "locked"
- [ ] Locked year no longer allows new transactions (verify at API level)
- [ ] "View reports" button on a locked year navigates to Reports with that FY selected

### 7.2 Recurring Transactions Panel
- [ ] All recurring schedules listed: narration, frequency badge, next due date, until date
- [ ] Edit button opens modal with frequency dropdown and end date input
- [ ] Saving an edit updates the schedule in the list
- [ ] Frequency options: daily, weekly, monthly, yearly — all selectable
- [ ] Delete button shows confirmation modal
- [ ] Confirming delete removes the schedule from the list
- [ ] Deleted schedule's future queue items are also cleaned up

### 7.3 Merchant Rules Panel
- [ ] All rules listed: merchant pattern, maps-to account, account type
- [ ] Edit button allows inline editing with Save/Cancel
- [ ] Saving an edit updates the rule
- [ ] `*` wildcard in pattern matches correctly (test via chat/import flow)
- [ ] Pattern matching is case-insensitive (test via chat/import flow)
- [ ] Delete button shows confirmation (or undo toast)
- [ ] Undo toast appears within 3-second window and restores the rule
- [ ] New rule creation works (button + modal or inline)

### 7.4 AI / LLM Panel
- [ ] Server URL, Model name, and API key fields pre-fill with saved config
- [ ] API key field masked (password input)
- [ ] "Test connection" hits the configured server and shows result
- [ ] Success: green indicator with latency value
- [ ] Failure (wrong URL or key): red indicator with error message
- [ ] "Save" button persists config (verify on page reload)
- [ ] Help box describes available AI use cases

---

## 8. AI Chat — Web Interface

### 8.1 Chat UI
- [ ] Chat input is accessible from all pages (sidebar toggle or persistent panel)
- [ ] Messages send on Enter or button click
- [ ] Bot responses stream token-by-token (not a single lump)
- [ ] User messages and bot responses are visually distinguished
- [ ] Chat history persists within the session
- [ ] Chat history clears on page reload (or document expected persistence behavior)

### 8.2 Natural Language Transaction Entry
- [ ] "Paid ₹500 at Swiggy" → orchestrator returns a PROPOSAL card
- [ ] Proposal card shows: narration, accounts, amount, date
- [ ] Confirming the proposal creates the transaction (visible in Transactions page)
- [ ] Declining the proposal does not create a transaction
- [ ] Editing the proposal (modifying amount or account) before confirming is reflected in the created transaction
- [ ] Ambiguous input prompts a clarifying question
- [ ] Multi-entry transaction ("split bill — ₹200 food, ₹150 transport") creates entries correctly
- [ ] Receipt ("received ₹5000 salary from HDFC") creates a receipt-type transaction

### 8.3 UPI Screenshot (Vision)
- [ ] Attach a UPI payment screenshot in chat
- [ ] Orchestrator extracts: merchant name, amount, reference number
- [ ] Merchant rules pre-fill the payee account if a matching rule exists
- [ ] Proposal card shows the extracted details
- [ ] Confirming creates the transaction correctly
- [ ] Non-payment image (e.g., a selfie) returns a graceful "not a payment" response

### 8.4 Bank Statement PDF Import (Web Chat)
- [ ] Attach a bank statement PDF in chat
- [ ] PDF is uploaded and a batch is created (orchestrator delegates to import_agent)
- [ ] Import agent begins row-by-row review
- [ ] Each staging row shows: date, narration, amount (Dr or Cr)
- [ ] Merchant rules auto-fill account for matching narrations
- [ ] User can correct an account for a row
- [ ] User can correct an amount for a row
- [ ] User can correct a narration for a row
- [ ] AI suggests an account for unmapped rows when asked
- [ ] Confirming the batch creates all transactions in bulk
- [ ] Transactions appear in the Transactions page after confirmation
- [ ] Cancelling/abandoning an import does not create partial transactions
- [ ] Large PDF (50+ rows) handles gracefully (no timeout or crash)

### 8.5 Account Queries via Chat
- [ ] "What's my HDFC balance?" returns correct balance
- [ ] "List all accounts" returns account list
- [ ] "Show transactions for last month in ICICI" returns filtered results

### 8.6 Report Queries via Chat
- [ ] "What's my P&L for this year?" returns a readable summary
- [ ] "Show my net worth" returns assets minus liabilities

---

## 9. Telegram Bot

### 9.1 Bot Setup & Commands
- [ ] `/start` — bot replies with welcome message; user is registered
- [ ] `/start` again — session history is cleared, welcome message shown
- [ ] `/help` — bot replies with command list and usage examples
- [ ] `/balance` — bot returns account balances (matches dashboard)
- [ ] `/recurring` — bot returns today's recurring transactions (matches Needs Attention)

### 9.2 Natural Language Transaction Entry
- [ ] Sending "paid 200 at BigBasket" → bot returns a PROPOSAL card
- [ ] Confirm button on proposal card creates the transaction
- [ ] Decline button dismisses without creating a transaction
- [ ] Editing the proposed amount before confirming is reflected in the created transaction
- [ ] Proposal amount and accounts match what the web chat would produce for the same input
- [ ] Conversation history allows follow-up ("make it ₹250 instead")

### 9.3 UPI Screenshot (Vision)
- [ ] Send a UPI payment screenshot as a photo message
- [ ] Bot extracts merchant name, amount, reference number from the image
- [ ] Proposal card generated; confirming creates the transaction
- [ ] Non-payment image returns a graceful fallback response

### 9.4 Bank Statement PDF Import (Telegram)
- [ ] `/import` command prepares the bot for PDF upload
- [ ] Sending a PDF after `/import` uploads it and starts the import flow
- [ ] Import_agent guides through row review via Telegram messages
- [ ] Confirming batch via Telegram creates all transactions

### 9.5 Per-User Isolation
- [ ] Two different Telegram users see only their own conversation history
- [ ] Transactions created by User A are visible to User B in the web app (shared data model — verify this is expected behavior)

---

## 10. Recurring Transactions (End-to-End)

- [ ] Create a recurring schedule from Settings → Recurring (requires an existing template transaction)
- [ ] Schedule appears in the list with correct next_due_date
- [ ] On the due date (or by advancing system time): queue item appears on Dashboard "Needs Attention"
- [ ] "Confirm" on the queue item creates a new transaction with today's date
- [ ] Transaction number is assigned; transaction appears in Transactions page
- [ ] Confirmed item disappears from Needs Attention
- [ ] "Skip" on the queue item dismisses it without creating a transaction
- [ ] Next_due_date advances correctly after confirm or skip (e.g., monthly → next month)
- [ ] Schedule with an end_date stops generating queue items after that date
- [ ] Deleting a schedule removes future queue items

---

## 11. Investment Flows

### 11.1 Fixed Deposits
- [ ] Create an FD via chat ("create an FD — ₹1L at 7.5% from Jan 1 to Dec 31")
- [ ] FD appears in Portfolio → Fixed Deposits tab
- [ ] Accrued interest is computed correctly (simple and compound cases)
- [ ] Dashboard alert appears when maturity ≤ 30 days
- [ ] Status badge transitions: Active → Matures in Xd → Matured

### 11.2 Equity MF / Stocks — Buy
- [ ] Record a buy via chat ("bought 100 units of Axis Bluechip at NAV 45")
- [ ] Holding appears in Portfolio with correct cost basis
- [ ] Lot is created with correct acquisition date and units

### 11.3 Equity MF / Stocks — Sell (Partial)
- [ ] Record a partial sell ("sold 50 units of Axis Bluechip at NAV 55")
- [ ] FIFO lots are consumed correctly (oldest first)
- [ ] Capital gain entry created with correct gain amount
- [ ] Remaining 50 units still show in holdings
- [ ] STCG / LTCG classification is correct based on holding period

### 11.4 Capital Gains Report
- [ ] Capital Gains tab in Reports shows all sale entries for the FY
- [ ] STCG and LTCG totals are correct
- [ ] LTCG exemption (₹1.25L) applied before tax calculation
- [ ] Tax payable figures are correct

---

## 12. Financial Year Lifecycle

- [ ] Create a new FY (Settings → Financial Years → New FY)
- [ ] New FY suggested dates are one year after the active FY end
- [ ] Overlapping FY dates are rejected
- [ ] Set opening balances for the new FY (reflects prior-year closing balances)
- [ ] Run pre-lock check — unposted depreciation warnings show
- [ ] Lock the active FY — net profit transferred to equity, status → locked
- [ ] After locking, creating a transaction in the locked FY is blocked
- [ ] New FY becomes active; transactions can be created in it
- [ ] Reports for the locked FY remain accessible and correct

---

## 13. Cross-Cutting Concerns

### 13.1 Data Integrity
- [ ] All monetary values stored and displayed in paise (no floating-point rounding errors)
- [ ] Double-entry is always balanced (Dr sum = Cr sum per transaction)
- [ ] Deleting a transaction that is part of a recurring schedule does not break the schedule
- [ ] Archiving an account does not corrupt its historical transactions

### 13.2 Error & Edge-Case Handling
- [ ] API returns 422 for missing required fields — UI shows a user-friendly error
- [ ] API returns 404 for unknown resource — UI shows a not-found state (not a crash)
- [ ] Network disconnect during streaming chat — graceful error, not a spinner forever
- [ ] Uploading a non-PDF file in the import flow — friendly error message
- [ ] Uploading a PDF that is not a bank statement — import agent handles gracefully
- [ ] Empty states: no transactions, no accounts, no FDs — each page renders without errors

### 13.3 Performance
- [ ] Transaction list with 500+ rows loads within 3 seconds
- [ ] Account ledger with 200+ entries loads within 3 seconds
- [ ] Reports render within 5 seconds for a full FY
- [ ] Chat responses begin streaming within 3 seconds of send

### 13.4 UI Consistency
- [ ] Currency amounts always display with ₹ symbol and comma separators (e.g., ₹1,00,000)
- [ ] Negative amounts styled distinctly (red or brackets)
- [ ] Dates display in DD MMM YYYY format consistently
- [ ] Loading spinners appear during all async operations
- [ ] Form validation errors display inline (not just console errors)
- [ ] Modals/sheets close on Escape key and backdrop click
- [ ] Mobile viewport (< 768px): check for overflow, unusable tap targets

### 13.5 Settings Persistence
- [ ] AI/LLM config survives container restart (stored in DB, not memory)
- [ ] Merchant rules persist across sessions
- [ ] Recurring schedules persist across sessions

---

## Bug Log

Use this section to record bugs found during QA.

| # | Section | Description | Severity (P1/P2/P3) | Status |
|---|---------|-------------|----------------------|--------|
| 1 | | | | Open |

> **Severity guide**: P1 = data loss or broken core flow; P2 = feature broken but workaround exists; P3 = cosmetic or minor UX issue.
