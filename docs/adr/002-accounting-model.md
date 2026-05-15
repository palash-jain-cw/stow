# ADR 002 — Accounting Model

**Status:** Accepted

## Context

Stow needs a bookkeeping model suited for a GST-registered Indian individual with salary and freelance income. The model must support standard financial reports and Indian tax obligations without the complexity of full ERP features.

## Decisions

### Double-Entry Enforcement
All transactions must have entries summing to zero. Enforced at application layer before posting; invalid transactions are rejected.

### Account Group Hierarchy
Seeded from Tally's standard Indian chart of accounts. Rationale: well-known, suits Indian tax structure, covers all use cases out of the box. Fully customizable after seeding.

### Vocabulary
Plain English terms used throughout (Account, Account Group, Transaction, Entry) rather than Tally jargon (Ledger, Group, Voucher). User is not familiar with Tally terminology.

### Indian Financial Year
April 1 – March 31. Each FY is a discrete entity in the database. Transactions cannot be posted to a locked FY. The lock is manual; see ADR 005 for the year-end closing model.

### GST Structure
Full Input/Output split for CGST, SGST, IGST — seeded under Duties & Taxes group. User is GST-registered for freelance work. No GST return generation; bookkeeping only.

### Cash Flow Tagging
Indirect method. Each account carries an Operating/Investing/Financing tag. Seed data provides sensible defaults; investment accounts are flagged at creation time.

## Rejected Alternatives

- **Single-entry bookkeeping**: insufficient for GST tracking and balance sheet generation
- **Tally vocabulary**: user is not familiar with it; plain English reduces cognitive load
- **Automatic FY lock**: user wants control over when the year is locked
- **Direct method cash flow**: indirect method is standard practice in India
