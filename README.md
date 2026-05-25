# Stow

Personal double-entry bookkeeping for India — GST, TDS, investments, financial reports, and natural-language entry via a local AI assistant.

Stow is built for a single user running everything on their own machine. It follows a Tally-inspired accounting model (accounts, vouchers, financial years) but uses plain language and drops features you do not need for personal books (no invoicing, inventory, or payroll).

For domain vocabulary, architecture, and design decisions, see [CONTEXT.md](CONTEXT.md).

## What it does

- Record transactions (Payment, Receipt, Journal, Contra) with double-entry validation
- Track GST and TDS obligations
- Manage investments — fixed deposits, mutual funds, and stocks with FIFO capital gains
- Generate reports (Trial Balance, Balance Sheet, P&L, Cash Flow, Capital Gains) with PDF export
- Import bank statement PDFs and review rows before posting
- Chat with an AI assistant (web UI or optional Telegram bot) to create transactions, query balances, and manage investments
- Process UPI payment screenshots — send a photo and the AI extracts merchant, amount, and account details

### AI Architecture

The AI assistant runs locally on your machine using any OpenAI-compatible inference server (oMLX, Ollama, LM Studio, vLLM). A single unified agent handles all intents — transaction entry, account management, bank imports, investments, recurring transactions, and financial reports — via ~40+ tools with a comprehensive domain prompt.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- A local **OpenAI-compatible LLM server** (oMLX, Ollama, LM Studio, vLLM, etc.) for AI features — the app will run without one, but chat and natural-language entry will not work until configured

## Setup

1. **Clone the repository**

   ```bash
   git clone <repo-url>
   cd stow
   ```

2. **Create environment file**

   ```bash
   cp .env.example .env
   ```

3. **Configure LLM settings** in `.env` to match your local inference server:

   ```env
   STOW_LLM_BASE_URL=http://host.docker.internal:8001/v1
   STOW_LLM_MODEL=your-model-name
   STOW_LLM_API_KEY=omlx
   ```

   `host.docker.internal` lets the backend container reach a server running on your Mac. Adjust the port and model name for your setup. You can also configure the LLM later in the app under **Settings → AI / LLM**.

4. **Optional — Telegram bot**

   Set `TELEGRAM_BOT_TOKEN` in your shell or add it to the backend service environment in `docker-compose.yml`, or paste the token in **Settings → Telegram** (stored in `~/.stow/config`). If unset, the bot is disabled and the web app works normally.

## Run

Start the full stack (Postgres, backend, frontend):

```bash
docker compose up
```

With the included `docker-compose.override.yml`, services run in **development mode** with hot reload:

| Service   | URL                          |
|-----------|------------------------------|
| Web app   | http://localhost:5173        |
| API       | http://localhost:8000        |
| API health| http://localhost:8000/health |

On first launch, complete the **onboarding wizard** (financial year, bank accounts, opening balances, optional LLM config).

To run a production-style build (nginx frontend on port 3000, no hot reload):

```bash
docker compose -f docker-compose.yml up --build
```

Then open http://localhost:3000 — the frontend proxies `/api/` to the backend.

### Optional: pgAdmin (dev profile)

```bash
docker compose --profile dev up
```

pgAdmin is available at http://localhost:5050 (login: `admin@stow.local` / `admin`).

## Development

### Backend tests

```bash
cd backend
uv sync --group dev
uv run pytest
```

### End-to-end tests

Requires the dev stack running (`docker compose up`):

```bash
cd e2e
npm ci
npm test
```

### Manual agent testing

With the backend running:

```bash
cd backend
uv run python scripts/chat.py
```

## Project structure

```
stow/
├── frontend/     Vite + React SPA
├── backend/      FastAPI application + AI agent
├── docs/adr/     Architecture decision records
├── e2e/          Playwright tests
└── CONTEXT.md    Full design documentation
```
