# ADR 013 — NL Entry & LLM Config

**Status:** Accepted

## Context

Issue #11: natural language transaction parsing via a local OpenAI-compatible inference server, plus config persistence (`~/.stow/config`) and a test-connection endpoint used by the Settings AI/LLM panel.

## Decisions

### LLM Client — pydantic-ai

Use `pydantic_ai.Agent` with `OpenAIChatModel` + `OpenAIProvider` from the `pydantic-ai` package. This gives typed structured output via a Pydantic result model without manual JSON parsing.

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

model = OpenAIChatModel(
    model_name,
    provider=OpenAIProvider(base_url=base_url, api_key=api_key or "not-needed"),
)
agent = Agent(model, result_type=ParsedTransaction, system_prompt="...")
```

The agent is constructed in `stow/ai_agent.py` and injected via a FastAPI dependency so tests can override it.

### Configuration (priority order)

1. Env vars `STOW_LLM_BASE_URL`, `STOW_LLM_MODEL`, `STOW_LLM_API_KEY`
2. `~/.stow/config` TOML file (read via stdlib `tomllib`; written via `tomli-w`)
3. Defaults: empty strings

`GET /ai/config` reads in priority order. `POST /ai/config` always writes to the TOML file; env vars are never mutated.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ai/config` | Returns `{base_url, model}` |
| `POST` | `/ai/config` | Writes `{base_url, model}` to `~/.stow/config` |
| `POST` | `/ai/test-connection` | Sends a minimal ping; returns `{ok, model, latency_ms}` or `{ok: false, error}` |
| `POST` | `/ai/parse-transaction` | Returns structured pre-filled transaction dict (never auto-posts) |

### Prompt construction

- System prompt on the `Agent`: role + JSON field descriptions for `ParsedTransaction`
- User prompt per call: full account list (id, name, group, type) + last 10 posted transactions + current date + raw user text
- Amount in paise in both examples and response
- Dates resolved relative to current date (backend resolves, not frontend)

### ParsedTransaction result type

```python
class ParsedTransaction(BaseModel):
    type: Literal["payment", "receipt", "journal", "contra"]
    date: date
    amount: int          # paise
    narration: str
    from_account_id: UUID
    to_account_id: UUID
    confidence: float
```

### Error handling

- `POST /ai/test-connection`: catches `httpx.ConnectError`, `ModelHTTPError`, any exception → `{ok: false, error: str}`
- `POST /ai/parse-transaction`: propagates LLM errors as HTTP 502

### File structure

```
stow/ai_config.py          — read_config(), write_config() (TOML I/O)
stow/ai_agent.py           — build_agent(), ParsedTransaction, get_ai_agent() dependency
stow/routers/ai.py         — router with all 4 endpoints
tests/test_ai.py           — all tests
```

### TDD slices (implementation order)

1. `GET /ai/config` returns env-var values
2. `POST /ai/config` persists to TOML; `GET` picks it up
3. `POST /ai/test-connection` — happy path (mock agent)
4. `POST /ai/test-connection` — connection failure
5. `POST /ai/parse-transaction` — returns structured dict (agent mocked)
6. Amount/date/account resolution edge cases

## Rejected Alternatives

- **Raw httpx for LLM calls**: pydantic-ai gives typed structured output and cleaner test mocking
- **pydantic-ai with cloud providers**: local OpenAI-compatible endpoint only (ADR 003)
- **Config in DB**: TOML file matches the issue spec and avoids a new migration
- **Pydantic settings only (no file persistence)**: doesn't satisfy `POST /ai/config` writing to disk
