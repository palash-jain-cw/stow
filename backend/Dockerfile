FROM python:3.12-slim AS base

RUN pip install uv

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/

FROM base AS dev
RUN uv sync --no-dev
CMD ["uvicorn", "stow.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS prod
RUN uv sync --no-dev
CMD ["uvicorn", "stow.main:app", "--host", "0.0.0.0", "--port", "8000"]
