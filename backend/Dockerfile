FROM python:3.12-slim AS base

RUN pip install uv

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN uv sync --no-dev

CMD ["uv", "run", "uvicorn", "stow.main:app", "--host", "0.0.0.0", "--port", "8000"]
