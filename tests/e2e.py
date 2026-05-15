#!/usr/bin/env python3
from __future__ import annotations
"""
End-to-end smoke test for the Stow backend.

Runs against a live server (default: http://localhost:8000).
Usage:
    python tests/e2e.py
    python tests/e2e.py http://localhost:8000

Exits 0 on success, 1 if any assertion fails.
"""

import json
import sys
import time
from typing import Any

import httpx

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"

# ── Helpers ────────────────────────────────────────────────────────────────

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
SECTION = "\033[1;34m"
RESET = "\033[0m"

_failures: list[str] = []


def section(name: str) -> None:
    print(f"\n{SECTION}── {name} ──{RESET}")


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  {PASS} {label}")
    else:
        msg = f"{label}" + (f": {detail}" if detail else "")
        print(f"  {FAIL} {msg}")
        _failures.append(msg)


def get(path: str, **params) -> dict:
    r = httpx.get(f"{BASE}{path}", params=params)
    return r.json()


def post(path: str, body: dict | None = None) -> tuple[int, dict]:
    r = httpx.post(f"{BASE}{path}", json=body)
    return r.status_code, r.json()


def put(path: str, body: dict) -> tuple[int, dict]:
    r = httpx.put(f"{BASE}{path}", json=body)
    return r.status_code, r.json()


def delete(path: str) -> int:
    r = httpx.delete(f"{BASE}{path}")
    return r.status_code


def find_group(groups: list[dict], name: str) -> int:
    for g in groups:
        if g["name"] == name:
            return g["id"]
    raise ValueError(f"Group not found: {name!r}")


# ── Journey 1: Health ──────────────────────────────────────────────────────

section("1. Health")
data = get("/health")
check("GET /health returns ok", data.get("status") == "ok", str(data))


# ── Journey 2: Financial year ──────────────────────────────────────────────

section("2. Financial year")
status, fy = post("/financial-years", {"start_date": "2026-04-01", "end_date": "2027-03-31"})
check("POST /financial-years → 201", status == 201, str(status))
check("FY has id", "id" in fy)
FY_ID = fy["id"]

# Also create FY 2023-24 for equity buy
_, fy_old = post("/financial-years", {"start_date": "2023-04-01", "end_date": "2024-03-31"})
FY_OLD_ID = fy_old["id"]


# ── Journey 3: Accounts ────────────────────────────────────────────────────

section("3. Accounts")
groups = get("/account-groups")
check("GET /account-groups returns list", isinstance(groups, list) and len(groups) > 0)

bank_grp_id = find_group(groups, "Bank Accounts")
exp_grp_id = find_group(groups, "Indirect Expenses")
inc_grp_id = find_group(groups, "Indirect Income")
inv_grp_id = find_group(groups, "Investments")

_, hdfc = post("/accounts", {"name": "HDFC Savings", "group_id": bank_grp_id})
check("Create HDFC Savings account", "id" in hdfc, str(hdfc))
HDFC_ID = hdfc["id"]

_, elec = post("/accounts", {"name": "Electricity", "group_id": exp_grp_id})
check("Create Electricity expense account", "id" in elec)
ELEC_ID = elec["id"]

_, salary = post("/accounts", {"name": "Salary", "group_id": inc_grp_id})
check("Create Salary income account", "id" in salary)
SALARY_ID = salary["id"]

_, mf_acc = post("/accounts", {"name": "Parag Parikh Flexi Cap", "group_id": inv_grp_id, "investment_subtype": "equity_mf"})
check("Create equity MF account", "id" in mf_acc)
MF_ID = mf_acc["id"]

_, fd_acc = post("/accounts", {"name": "HDFC FD 7.5%", "group_id": inv_grp_id, "investment_subtype": "fd"})
check("Create FD account", "id" in fd_acc)
FD_ACC_ID = fd_acc["id"]


# ── Journey 4: Transactions ────────────────────────────────────────────────

section("4. Transactions")

# Salary receipt ₹85,000
status, rec = post("/transactions", {
    "type": "receipt",
    "date": "2026-04-30",
    "narration": "April salary",
    "fy_id": FY_ID,
    "entries": [
        {"account_id": HDFC_ID, "amount": 8500000},
        {"account_id": SALARY_ID, "amount": -8500000},
    ],
})
check("POST salary receipt → 201", status == 201, str(status))
check("Transaction number starts with REC", rec.get("number", "").startswith("REC"))
REC_TXN_ID = rec["id"]

# Electricity bill ₹2,400
status, pay = post("/transactions", {
    "type": "payment",
    "date": "2026-05-05",
    "narration": "BESCOM electricity bill",
    "fy_id": FY_ID,
    "tags": ["utilities"],
    "entries": [
        {"account_id": ELEC_ID, "amount": 240000},
        {"account_id": HDFC_ID, "amount": -240000},
    ],
})
check("POST electricity payment → 201", status == 201, str(status))
check("Transaction number starts with PAY", pay.get("number", "").startswith("PAY"))
check("Tags preserved", pay.get("tags") == ["utilities"])
PAY_TXN_ID = pay["id"]

# Reject unbalanced entries
status, _ = post("/transactions", {
    "type": "payment",
    "date": "2026-05-05",
    "narration": "Unbalanced",
    "fy_id": FY_ID,
    "entries": [
        {"account_id": ELEC_ID, "amount": 100000},
        {"account_id": HDFC_ID, "amount": -99999},
    ],
})
check("Unbalanced entries rejected → 422", status == 422, str(status))

# List transactions
txns = get("/transactions", fy_id=FY_ID)
check("GET /transactions returns both transactions", len(txns) >= 2)


# ── Journey 5: Reports ─────────────────────────────────────────────────────

section("5. Reports")

tb = get("/reports/trial-balance", fy_id=FY_ID)
check("Trial balance: total_debit == total_credit",
      tb["total_debit"] == tb["total_credit"],
      f"debit={tb['total_debit']} credit={tb['total_credit']}")
check("Trial balance: debit total = 8,500,000",
      tb["total_debit"] == 8500000,
      str(tb["total_debit"]))

pl = get("/reports/profit-loss", fy_id=FY_ID)
check("P&L total income = 8,500,000", pl["total_income"] == 8500000, str(pl["total_income"]))
check("P&L total expenses = 240,000", pl["total_expenses"] == 240000, str(pl["total_expenses"]))
check("P&L net profit = 8,260,000", pl["net_profit"] == 8260000, str(pl["net_profit"]))

bs = get("/reports/balance-sheet", fy_id=FY_ID)
check("Balance sheet: assets == liabilities + equity",
      bs["total_assets"] == bs["total_liabilities_and_equity"],
      f"assets={bs['total_assets']} liab+eq={bs['total_liabilities_and_equity']}")


# ── Journey 6: Recurring schedule ─────────────────────────────────────────

section("6. Recurring schedules")

status, sched = post("/recurring/schedules", {
    "template_transaction_id": PAY_TXN_ID,
    "frequency": "monthly",
    "day_of_period": 5,
    "first_due_date": "2026-06-05",
})
check("POST /recurring/schedules → 201", status == 201, str(status))
check("Schedule has next_due_date", "next_due_date" in sched)
SCHED_ID = sched["id"]

schedules = get("/recurring/schedules")
check("GET /recurring/schedules lists schedule", any(s["id"] == SCHED_ID for s in schedules))

due = get("/recurring/due-today")
check("GET /recurring/due-today returns list", isinstance(due, list))


# ── Journey 7: Fixed deposits ──────────────────────────────────────────────

section("7. Fixed deposits")

status, fd = post("/investments/fds", {
    "account_id": FD_ACC_ID,
    "name": "HDFC FD 7.5%",
    "principal": 10000000,
    "interest_rate": 750,
    "start_date": "2026-04-01",
    "maturity_date": "2027-04-01",
    "compounding": "quarterly",
})
check("POST /investments/fds → 201", status == 201, str(status))
check("FD principal stored correctly", fd.get("principal") == 10000000)
check("FD status is active", fd.get("status") == "active")

fds = get("/investments/fds")
check("GET /investments/fds lists FD", any(f["principal"] == 10000000 for f in fds))

maturing = get("/investments/fds/maturing-soon", days=400)
check("GET /investments/fds/maturing-soon returns list", isinstance(maturing, list))


# ── Journey 8: Equity investments ─────────────────────────────────────────

section("8. Equity investments (lots, FIFO, LTCG)")

# Buy 100 units at ₹85/unit on 2024-01-15 (cost_per_unit in paise per milliunit)
status, lot = post(f"/investments/{MF_ID}/buy", {
    "units": 100000,
    "cost_per_unit": 8500,
    "date": "2024-01-15",
    "fy_id": FY_OLD_ID,
    "bank_account_id": HDFC_ID,
    "narration": "Buy PPFCF",
})
check("POST buy creates lot → 201", status == 201, str(status))
check("Lot units = 100,000", lot.get("units") == 100000)
check("Lot remaining_units = 100,000", lot.get("remaining_units") == 100000)

holdings = get(f"/investments/{MF_ID}/holdings")
check("Holdings shows open lot", len(holdings) > 0)
check("Holdings cost basis correct", holdings[0].get("cost_per_unit") == 8500)

# Sell 50 units at ₹105/unit on 2026-04-10 (held >12 months → LTCG)
status, gains = post(f"/investments/{MF_ID}/sell", {
    "units": 50000,
    "price_per_unit": 10500,
    "date": "2026-04-10",
    "fy_id": FY_ID,
    "bank_account_id": HDFC_ID,
    "narration": "Sell PPFCF partial",
})
check("POST sell returns capital gain entries → 201", status == 201, str(status))
check("Gain classified as LTCG (held >12 months)", gains[0].get("gain_type") == "ltcg")
check("LTCG gain = 100,000 paise (₹1,000)", gains[0].get("gain") == 100000,
      str(gains[0].get("gain")))

cap_gains = get(f"/investments/{MF_ID}/capital-gains", fy_id=FY_ID)
check("Capital gains report: total_ltcg = 100,000", cap_gains["total_ltcg"] == 100000)
check("Capital gains report: total_stcg = 0", cap_gains["total_stcg"] == 0)

# Remaining lot should have 50,000 units
holdings_after = get(f"/investments/{MF_ID}/holdings")
check("Remaining units = 50,000 after partial sale",
      holdings_after[0].get("remaining_units") == 50000,
      str(holdings_after[0].get("remaining_units")))


# ── Journey 9: AI config ───────────────────────────────────────────────────

section("9. AI config")

cfg = get("/ai/config")
check("GET /ai/config returns base_url and model",
      "base_url" in cfg and "model" in cfg)

status, cfg2 = post("/ai/config", {"base_url": "http://localhost:11434/v1", "model": "qwen3:8b"})
check("POST /ai/config → 200", status == 200, str(status))
# env vars take priority; config file write still succeeds — just verify the response has the fields
check("POST /ai/config response has base_url and model", "base_url" in cfg2 and "model" in cfg2)


# ── Journey 10: Merchant rules ─────────────────────────────────────────────

section("10. Merchant rules")

status, rule = post("/merchant-rules", {"pattern": "BESCOM*", "account_id": ELEC_ID})
check("POST /merchant-rules → 201", status == 201, str(status))
check("Rule pattern stored", rule.get("pattern") == "BESCOM*")
RULE_ID = rule["id"]

rules = get("/merchant-rules")
check("GET /merchant-rules lists rule", any(r["id"] == RULE_ID for r in rules))

status, updated = put(f"/merchant-rules/{RULE_ID}", {"pattern": "BESCOM_E*", "account_id": ELEC_ID})
check("PUT /merchant-rules/{id} updates pattern", updated.get("pattern") == "BESCOM_E*")

status = delete(f"/merchant-rules/{RULE_ID}")
check("DELETE /merchant-rules/{id} → 204", status == 204, str(status))

rules_after = get("/merchant-rules")
check("Rule removed after DELETE", not any(r["id"] == RULE_ID for r in rules_after))


# ── Journey 11: Scheduler ──────────────────────────────────────────────────

section("11. Scheduler")

jobs = get("/scheduler/jobs")
check("GET /scheduler/jobs returns 4 jobs", len(jobs) == 4, str(len(jobs)))
job_ids = {j["id"] for j in jobs}
for expected in ["fetch_prices_morning", "fetch_prices_evening", "generate_recurring", "auto_post"]:
    check(f"Job '{expected}' present", expected in job_ids)
check("All jobs unpaused", all(not j["paused"] for j in jobs))


# ── Summary ────────────────────────────────────────────────────────────────

print(f"\n{'─'*50}")
if _failures:
    print(f"\033[31m{len(_failures)} failure(s):\033[0m")
    for f in _failures:
        print(f"  • {f}")
    sys.exit(1)
else:
    total = sum(1 for line in open(__file__) if "check(" in line)
    print(f"\033[32mAll checks passed ({total} assertions)\033[0m")
    sys.exit(0)
