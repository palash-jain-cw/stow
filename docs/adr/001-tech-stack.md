# ADR 001 — Technology Stack

**Status:** Accepted

## Context

Single-user personal accounting application running locally on Apple Silicon Mac via Docker Compose.

## Decisions

### Backend: FastAPI + SQLModel + Alembic + PostgreSQL
- FastAPI for automatic OpenAPI docs and Pydantic validation
- SQLModel unifies Pydantic models and SQLAlchemy ORM, reducing boilerplate
- Alembic for migrations (SQLModel's built-in migration support is insufficient)
- PostgreSQL over SQLite for proper transaction isolation and constraint enforcement

### Frontend: Vite + React + shadcn/ui + React Query
- Vite for fast local dev server; no SSR needed for a local SPA
- shadcn/ui for accessible, customizable components without enterprise-app aesthetics
- React Query for server state management paired with REST endpoints

### AI: OpenAI-compatible local inference API
- Any server exposing an OpenAI-compatible API endpoint (oMLX, Ollama, LM Studio, vLLM, etc.)
- Configured via environment variables: `STOW_LLM_BASE_URL` and `STOW_LLM_MODEL`
- All inference on-device — no external API calls, no cost, no data leaving the machine
- PDF parsing via pdfplumber/pymupdf + LLM structured extraction (not vision)

### Deployment: Docker Compose
- Single `docker-compose.yml` at repo root
- Services: frontend (nginx), backend (uvicorn), postgres, ollama
- All data on named Docker volumes

## Rejected Alternatives

- **SQLite**: insufficient transaction isolation for accounting workloads
- **Next.js**: SSR overhead unnecessary for a local single-user SPA
- **GraphQL**: adds schema complexity without benefit for a simple REST CRUD app
- **Hardcoding Ollama**: too restrictive; user runs oMLX and may switch inference backends — OpenAI-compatible API is the common interface
