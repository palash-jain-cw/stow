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

### AI: Ollama + Qwen3.6 (local)
- All inference on-device — no external API calls, no cost, no data leaving the machine
- Qwen3.6 chosen by user (already in use)
- PDF parsing via pdfplumber/pymupdf + LLM structured extraction (not vision)

### Deployment: Docker Compose
- Single `docker-compose.yml` at repo root
- Services: frontend (nginx), backend (uvicorn), postgres, ollama
- All data on named Docker volumes

## Rejected Alternatives

- **SQLite**: insufficient transaction isolation for accounting workloads
- **Next.js**: SSR overhead unnecessary for a local single-user SPA
- **GraphQL**: adds schema complexity without benefit for a simple REST CRUD app
- **Claude API / OpenAI**: requires external calls; user prefers local inference
