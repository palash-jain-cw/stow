"""Fixtures for live LLM integration tests."""
from __future__ import annotations

import logging
import traceback

import httpx
import pytest
from sqlmodel import select

from stow.ai_config import read_config
from stow.models import Account, AccountGroup, FinancialYear, MerchantRule

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def llm_config() -> dict[str, str]:
    cfg = read_config()
    assert cfg["base_url"], (
        "STOW_LLM_BASE_URL is not set. Add it to the repo .env or export it before running "
        "pytest tests/integration/ --run-integration"
    )
    assert cfg["model"], "STOW_LLM_MODEL is not set."
    return cfg


@pytest.fixture(scope="session")
async def llm_reachable(llm_config: dict[str, str]) -> dict[str, str]:
    """Fail fast if the configured inference server is unreachable."""
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    from stow.ai_config import resolve_llm_base_url

    base_url = resolve_llm_base_url(llm_config["base_url"])
    api_key = llm_config.get("api_key") or "not-needed"
    model = OpenAIChatModel(
        llm_config["model"],
        provider=OpenAIProvider(base_url=base_url, api_key=api_key),
    )
    agent = Agent(model)
    try:
        logger.info("Probing LLM at %s model=%s", base_url, llm_config["model"])
        await agent.run("Reply with exactly: pong")
    except Exception:
        logger.error("LLM probe failed: %s", traceback.format_exc())
        pytest.fail(
            f"Could not reach LLM at {base_url} (model={llm_config['model']}). "
            "Check STOW_LLM_* in .env and that the server is running."
        )
    return llm_config


@pytest.fixture()
async def agent_http_client(asgi_app, session):
    from stow.db import get_session

    asgi_app.dependency_overrides[get_session] = lambda: session
    transport = httpx.ASGITransport(app=asgi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=120.0) as client:
        yield client
    asgi_app.dependency_overrides.clear()


@pytest.fixture()
def agent_deps(agent_http_client):
    from agent.deps import StowDeps

    return StowDeps(base_url="http://test", http_client=agent_http_client)


@pytest.fixture()
def finance_setup(session):
    """Seed FY + common accounts used in agent scenarios."""
    fy = FinancialYear(
        start_date="2026-04-01",
        end_date="2027-03-31",
        status="active",
    )
    session.add(fy)
    session.flush()

    bank_group = session.exec(
        select(AccountGroup).where(AccountGroup.name == "Bank Accounts")
    ).one()
    expense_group = session.exec(
        select(AccountGroup).where(AccountGroup.name == "Indirect Expenses")
    ).one()

    hdfc = Account(name="HDFC Savings", group_id=bank_group.id, currency="INR")
    axis = Account(name="Axis Bank", group_id=bank_group.id, currency="INR")
    food = Account(name="Food & Dining", group_id=expense_group.id, currency="INR")
    pankhuri = Account(name="Pankhuri Jain", group_id=expense_group.id, currency="INR")
    session.add(hdfc)
    session.add(axis)
    session.add(food)
    session.add(pankhuri)
    session.flush()

    zomato_rule = MerchantRule(pattern="zomato", account_id=food.id)
    pankhuri_rule = MerchantRule(pattern="pankhuri", account_id=pankhuri.id)
    session.add(zomato_rule)
    session.add(pankhuri_rule)
    session.flush()

    return {
        "fy_id": fy.id,
        "hdfc": hdfc,
        "axis": axis,
        "food": food,
        "pankhuri": pankhuri,
    }
