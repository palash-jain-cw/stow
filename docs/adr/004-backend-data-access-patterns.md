# ADR 004 — Backend Data Access Patterns

**Status:** Accepted

## Context

During issue #3 (Accounts & seed data), two architectural questions arose about how the backend manages database connections and data access logic.

## Decisions

### Engine initialisation: module-level singleton

The SQLAlchemy engine is created once at module import time in `stow/db.py`:

```python
engine: Engine = create_engine(Settings().database_url)
```

**Alternatives considered:**

- **Global `_engine` with `init_engine()`** — mutable global state, requires callers to remember to call `init_engine` before any DB use; rejected.
- **`app.state.engine` set in lifespan** — cleaner lifecycle, but the lifespan also runs seed logic, which means tests that create a `TestClient` would trigger a real DB connection attempt even when `get_session` is overridden. Adds unnecessary complexity.

**Why module-level is acceptable here:**
The engine is created exactly once at process start. Tests set a parseable placeholder `DATABASE_URL` via `os.environ.setdefault` at the top of `conftest.py` before any `stow` imports; since `get_session` is overridden in all tests, the placeholder URL is never actually connected to. This follows the pattern in the [SQLModel FastAPI tutorial](https://sqlmodel.tiangolo.com/tutorial/fastapi/session-with-dependency/).

---

### Data access: direct SQLModel queries for simple CRUD; Repository Pattern for complex modules

Route handlers in simple CRUD modules (Accounts, Account Groups, Opening Balances) query the DB directly via an injected `Session`. No repository layer.

```python
# Simple CRUD — repository would add zero value here
@router.get("")
def list_accounts(session: Session = Depends(get_session)):
    return session.exec(select(Account).where(Account.is_archived == False)).all()
```

**The Repository Pattern will be introduced selectively** in modules where it earns its keep:

| Module | Why a repository is justified |
|---|---|
| #5 Report engine | Complex multi-table aggregation queries; report types are interchangeable implementations behind a common interface |
| #6 Equity investments (FIFO) | Lot consumption logic is non-trivial; encapsulating it behind a `LotRepository` keeps route handlers readable |
| #12 Bank import / merchant rules | Rule matching logic belongs in a layer below the route handler |

**Why not everywhere:**
Thin repositories that wrap one-liners (`session.add`, `session.get`) are indirection without abstraction. They obscure the query, add boilerplate, and make the codebase harder to navigate. The test strategy (HTTP-layer integration tests via `TestClient`) does not require mocking repositories — so the testability argument for universal repositories does not apply here.

---

### Session dependency injection

`get_session` is a FastAPI generator dependency injected via `Depends()`. All route handlers receive a request-scoped session. Tests replace it with a test session using `app.dependency_overrides[get_session]`.

```python
def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
```
