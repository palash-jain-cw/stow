from __future__ import annotations

from datetime import datetime

from pydantic_ai import Agent, RunContext
from subagents_pydantic_ai import SubAgentCapability, SubAgentConfig

from agent.activity import emit
from agent.deps import StowDeps


async def _get_current_datetime(ctx: RunContext[StowDeps]) -> dict:
    """Return the current date and time. Call this whenever you need to know today's date."""
    await emit("Checking date")
    now = datetime.now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "day": now.strftime("%A"),
        "display": now.strftime("%d %b %Y"),
        "time": now.strftime("%H:%M"),
    }


async def _get_merchant_rules(ctx: RunContext[StowDeps]) -> list[dict]:
    """Return merchant matching rules for UPI/payment account pre-fill.

    Each rule has a pattern (case-insensitive substring, e.g. "zomato") and an account_id.
    Call this when processing a payment screenshot to check if the merchant name matches
    any rule and pre-fill the account before delegating to transaction_agent.
    """
    await emit("Looking up merchant rules")
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/merchant-rules")
    r.raise_for_status()
    return r.json()
from agent.subagents.account import build_account_agent
from agent.subagents.import_agent import build_import_agent
from agent.subagents.investment import build_investment_agent
from agent.subagents.recurring import build_recurring_agent
from agent.subagents.report import build_report_agent
from agent.subagents.transaction import build_transaction_agent

_SYSTEM_PROMPT = """\
You are Stow, a conversational personal finance assistant for Indian users.
You help record transactions, import bank statements, answer financial queries,
and manage investments — entirely through conversation.

## Your role
- Understand user intent from natural language, forwarded screenshots, or PDF uploads.
- If intent is ambiguous or required information is missing, ask ONE focused question
  before delegating. Do not guess. Do not ask multiple questions at once.
- Once you have everything you need, delegate to the appropriate subagent via task().
- Present subagent results back to the user clearly, with a proposal card when applicable.

## Clarifying question examples
- Ambiguous account: "Which account did you pay from?"
- Missing date: "When did this happen?"
- Ambiguous amount: "Did you mean ₹500 or ₹5,000?"

## Vision (UPI screenshots / payment receipts)
When the user sends an image, analyze it to extract:
  - Amount (in INR/paise)
  - Merchant / payee name
  - Date of transaction
  - UPI ID or reference number (if visible)
Then call get_merchant_rules and check if any rule's pattern is a case-insensitive substring
of the merchant name. If a match is found, include that account_id in the structured input
to transaction_agent so the account is pre-filled.
If the image is not a payment screenshot, respond with a brief, friendly message.
Pass all extracted details to transaction_agent as structured input.

## Bank statement import
When you see a prompt starting with [IMPORT_BATCH:{id}:{filename}]:
- Extract the batch id (integer after the first colon).
- Delegate to import_agent with: "Batch id is {id}. Please review and confirm the import."
- Do NOT ask the user anything first — import_agent will ask for the bank account.

## Subagent routing
- Transaction entry / queries → transaction_agent
- Account lookup / management → account_agent
- Bank statement PDF import (after PDF is parsed into a batch) → import_agent
- Financial reports (trial balance, P&L, balance sheet, cash flow, balances, spending) → report_agent
- Investments (FDs, MFs, stocks, capital gains, portfolio) → investment_agent
- Recurring transactions → recurring_agent

## CRITICAL routing rules
- ANY mention of "buy", "purchase", "invest", "mutual fund", "MF", "SIP", "NAV", "fixed deposit",
  "FD", "stock", "shares", "units" in the context of purchasing/creating investments → investment_agent
- NEVER route investment purchases to transaction_agent; investment_agent handles all money movement for investments

## Proposal cards
When transaction_agent returns a parsed transaction proposal, emit a PROPOSAL line
as the very first line of your response, followed by the human-readable card:

PROPOSAL:{"type":"<type>","date":"<ISO date>","amount_paise":<int>,"narration":"<text>","from_account_id":<int>,"from_account_name":"<name>","to_account_id":<int>,"to_account_name":"<name>","fy_id":<int>}

Then show the card and ask the user to confirm, edit, or decline.
Example card:
  💸 Payment · ₹500.00
  📅 16 May 2026
  HDFC Bank → Electricity
  Narration: Electricity bill

  Reply "confirm" to post, "decline" to discard, or describe a change.

On "confirm": delegate to transaction_agent with the message
  "confirm: <paste the full PROPOSAL JSON here>"
  and reply with the transaction number once created.
On "decline": reply with a friendly cancellation message.
On an edit request: update the relevant field, re-emit the PROPOSAL line, and re-render the card.

## Formatting
- Amounts: always display as ₹X,XX,XXX (Indian comma format)
- Dates: display as "DD Mon YYYY" (e.g. 16 May 2026)
- After posting a transaction, show a concise confirmation with the transaction number.
- Keep responses short and actionable.

## Slash commands
- /recurring → get today's pending recurring items and walk through them
- /balance → report_agent for account balances
- /import → prompt for a bank statement PDF
- /help → explain capabilities
"""


def build_orchestrator() -> Agent[StowDeps, str]:
    """Build the orchestrator agent with all subagents wired via SubAgentCapability."""
    from stow.ai_config import build_model
    model = build_model()

    subagent_configs: list[SubAgentConfig] = [
        SubAgentConfig(
            name="transaction_agent",
            description=(
                "Creates, queries, updates, and deletes transactions. "
                "Also parses natural language transaction descriptions. "
                "Use for: recording payments/receipts/journals, searching transactions."
            ),
            agent=build_transaction_agent(model),
        ),
        SubAgentConfig(
            name="account_agent",
            description=(
                "Lists, creates, and archives ledger accounts. "
                "Use for: looking up account IDs/names/balances, creating new accounts."
            ),
            agent=build_account_agent(model),
        ),
        SubAgentConfig(
            name="import_agent",
            description=(
                "Reviews and confirms a parsed bank statement import batch. "
                "Use for: after a PDF is parsed into a batch — reviewing rows, "
                "handling duplicates, and posting confirmed transactions."
            ),
            agent=build_import_agent(model),
        ),
        SubAgentConfig(
            name="report_agent",
            description=(
                "Generates trial balance, profit & loss, balance sheet, and cash flow reports. "
                "Use for: financial queries, balance checks, spending analysis."
            ),
            agent=build_report_agent(model),
        ),
        SubAgentConfig(
            name="investment_agent",
            description=(
                "Manages FDs, mutual fund and stock lots, and portfolio/capital gains queries. "
                "Use for: creating FDs, recording buy/sell trades, checking portfolio value."
            ),
            agent=build_investment_agent(model),
        ),
        SubAgentConfig(
            name="recurring_agent",
            description=(
                "Processes recurring transaction schedules due today. "
                "Use for: /recurring command, confirming or skipping due items."
            ),
            agent=build_recurring_agent(model),
        ),
    ]

    return Agent(
        model=model,
        deps_type=StowDeps,
        instructions=_SYSTEM_PROMPT,
        tools=[_get_current_datetime, _get_merchant_rules],
        capabilities=[
            SubAgentCapability(
                subagents=subagent_configs,
                default_model=model,
                include_general_purpose=False,
                max_nesting_depth=0,
            )
        ],
    )
