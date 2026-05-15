FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libgdk-pixbuf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN uv sync --no-dev

CMD ["uv", "run", "uvicorn", "stow.main:app", "--host", "0.0.0.0", "--port", "8000"]
