# ADR-006: Simplify Agent Architecture — Merge Subagents into Unified Agent

**Status:** Implemented
**Date:** 2026-05-25

## Problem Statement

The subagent architecture overcomplicated the system. The orchestrator made an LLM classification call for every user message, routing to a subagent that then made another LLM call to execute. This added latency, cost, and a failure mode (misclassification).

## Decision

Replace the 6-subagent system (orchestrator + transaction/account/import/investment/recurring/report agents) with a **single unified agent** that exposes all tools at the top level.

## Rationale

### Why subagents were overkill for Stow

1. **Single user, single context** — No multi-tenancy, no different user roles. A single LLM call with well-described tools is simpler and more reliable.
2. **Classification errors** — The orchestrator's LLM-based routing can misclassify intents (e.g., "buy HDFC stock" → transaction_agent → refusal). Direct tool access eliminates this failure mode.
3. **2× LLM calls** — Every user message triggers: orchestrator (classify) → subagent (execute). The unified agent needs only 1 call.
4. **No cross-agent coordination** — Subagents don't know about each other. The old `transaction_agent` couldn't use merchant rules; `import_agent` couldn't create rules. A single agent has all tools available.

### Why a single agent works

Modern LLMs are excellent at tool selection when tools have **rich descriptions**. The key insight: instead of giving the LLM a routing prompt + 6 specialized prompts, give it **one comprehensive prompt** + **well-described tools**.

## Implementation

### Files Changed

| File | Change |
|---|---|
| `agent/agent.py` | **NEW** — Unified agent with all 40+ tools, consolidated system prompt |
| `agent/orchestrator.py` | Replaces old orchestrator — re-exports `build_agent` for backwards compat |
| `agent/deps.py` | Simplified — removed `subagents` field and `clone_for_subagent()` |
| `agent/subagents/` | **REMOVED** — All 6 subagent modules deleted |
| `tests/test_agent_orchestrator.py` | Updated to test unified agent |
| `scripts/chat.py` | Updated to use `build_agent()` |
| `stow/ai_config.py` | Added `"agent"` role to `_ROLE_MAX_TOKENS` |

### New Agent Structure

```
agent/agent.py (single file, ~400 lines)
├── _SYSTEM_PROMPT (comprehensive, ~100 lines)
│   ├── Core Domain Knowledge (amounts, double entry, investments, etc.)
│   ├── Clarifying Questions guidance
│   ├── Error Recovery rules
│   ├── Tool Caching guidance
│   └── Formatting rules
├── Shared Tools (~5)
│   ├── get_current_datetime
│   ├── get_active_fy / get_fy_for_date / get_financial_years
├── Account Tools (~7)
│   ├── list_accounts, get_account, create_account, archive_account
│   ├── get_account_ledger, get_opening_balance, set_opening_balance
├── Transaction Tools (~9)
│   ├── parse_natural_language, create_transaction, list_transactions
│   ├── get_transaction, update_transaction, delete_transaction
│   ├── get_depreciation_summary
├── Investment Tools (~12)
│   ├── create_fd, mature_fd, list_fds, buy_investment, sell_investment
│   ├── get_holdings, get_portfolio, get_capital_gains
│   ├── list_investment_accounts, fetch_prices, get_tax_rules
├── Import Tools (~7)
│   ├── match_bank_account, review_staging, confirm_staging
│   ├── match_staging_row, update_staging_row, get_batch
│   ├── apply_merchant_rules
├── Recurring Tools (~4)
│   ├── get_recurring_due, confirm_recurring, skip_recurring, list_schedules
├── Report Tools (~4)
│   ├── get_trial_balance, get_profit_loss, get_balance_sheet, get_cash_flow
├── UPI/Merchant Tools (~4)
│   ├── get_merchant_rules, resolve_upi_accounts
│   ├── create_merchant_rule, delete_merchant_rule
├── Proposal Tools (~1)
│   ├── post_confirmed_proposal
└── build_agent() — returns Agent[StowDeps, str]
```

### Key System Prompt Sections

The unified `_SYSTEM_PROMPT` consolidates all domain knowledge:

1. **Core Domain Knowledge** — Amounts (paise), double entry rules, transaction types, financial years, investments (milliunits, FIFO, STCG/LTCG), depreciation, GST/TDS, import workflow, UPI screenshots, recurring transactions.
2. **Clarifying Questions** — When to ask, how to ask (ONE question at a time).
3. **Error Recovery** — How to handle tool errors (read, fix, retry, or ask).
4. **Tool Caching** — Remember results of `list_accounts`, `list_fds`, `get_active_fy` across the conversation.
5. **Formatting** — Indian comma format, date format, keep responses short.

### New Tools Added (were missing before)

| Tool | Endpoint |
|---|---|
| `get_depreciation_summary` | `GET /depreciation/summary` |
| `get_opening_balance` / `set_opening_balance` | `GET/PUT /accounts/{id}/opening-balance` |
| `fetch_prices` | `POST /prices/fetch` |
| `get_tax_rules` | `GET /tax-rules` |
| `create_merchant_rule` / `delete_merchant_rule` | `POST/DELETE /merchant-rules` |
| `apply_merchant_rules` | `POST /imports/{id}/rows/apply-rules` |

## Benefits

| Metric | Before (Subagents) | After (Unified) |
|---|---|---|
| LLM calls per message | 2 (route + execute) | 1 |
| Failure modes | Misclassification + tool errors | Tool errors only |
| Code complexity | 6 subagent files + orchestrator | 1 file |
| Tool access | Restricted per subagent | All tools available |
| Domain knowledge | Split across 6 prompts | Consolidated in 1 prompt |
| Files in `agent/` | 10+ files | 5 files |

## Trade-offs

- **Larger system prompt** — The unified prompt is ~100 lines vs ~20 lines per subagent. But this is a one-time cost; the LLM handles it fine.
- **No tool isolation** — Any tool can be called by the agent. Mitigated by tool descriptions that specify when to use each tool.
- **No incremental rollout** — This is a breaking change to the agent internals. The HTTP API is unaffected.

## Backwards Compatibility

- `build_orchestrator()` is re-exported from `agent.py` for any code that imports it.
- The WebSocket transport and Telegram handlers call `build_orchestrator()` which now delegates to `build_agent()`.
- No changes to the HTTP API endpoints.

## Future Work

1. **Agent caching** — Add a `_cache` dict to `StowDeps` to avoid repeated `list_accounts` calls within a conversation.
2. **Tool descriptions** — Continuously improve tool docstrings based on LLM behavior observations.
3. **Performance monitoring** — Track LLM call count and latency to validate the simplification.
