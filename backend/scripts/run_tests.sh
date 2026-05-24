#!/usr/bin/env bash
# Run backend pytest with a working Postgres backend.
#
# Modes (first match wins):
#   1. Docker socket accessible → testcontainers (default pytest behaviour)
#   2. STOW_TEST_DATABASE_URL set → use that database
#   3. localhost:5433 reachable → use docker-compose.test.yml Postgres
#   4. Start docker-compose.test.yml with sudo, then use localhost:5433
#
# Usage:
#   ./scripts/run_tests.sh                  # all tests
#   ./scripts/run_tests.sh tests/test_ai.py # one file

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(cd .. && pwd)"

DEFAULT_TEST_URL="postgresql://test:test@127.0.0.1:5433/test"
COMPOSE_FILE="$ROOT/docker-compose.test.yml"

docker_accessible() {
  docker info >/dev/null 2>&1
}

port_open() {
  python3 - <<'PY' "$1"
import socket, sys
host, port = sys.argv[1].rsplit(":", 1)
port = int(port.split("/")[0])
s = socket.socket()
s.settimeout(0.5)
try:
    s.connect((host, port))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
}

wait_for_postgres() {
  local url="$1"
  echo "Waiting for Postgres at $url ..."
  for _ in $(seq 1 30); do
    if uv run python - <<PY 2>/dev/null
from sqlalchemy import create_engine, text
engine = create_engine("$url", pool_pre_ping=True)
with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
PY
    then
      echo "Postgres is ready."
      return 0
    fi
    sleep 1
  done
  echo "Postgres did not become ready in time." >&2
  return 1
}

ensure_test_postgres() {
  if [[ -n "${STOW_TEST_DATABASE_URL:-}" ]]; then
    export STOW_TEST_DATABASE_URL
    wait_for_postgres "$STOW_TEST_DATABASE_URL"
    return
  fi

  if port_open "127.0.0.1:5433"; then
    export STOW_TEST_DATABASE_URL="$DEFAULT_TEST_URL"
    wait_for_postgres "$STOW_TEST_DATABASE_URL"
    return
  fi

  if docker_accessible; then
    echo "Docker socket available — pytest will use testcontainers."
    return
  fi

  echo "Docker socket not accessible; starting test Postgres via sudo ..."
  sudo docker compose -f "$COMPOSE_FILE" up -d --wait
  export STOW_TEST_DATABASE_URL="$DEFAULT_TEST_URL"
  wait_for_postgres "$STOW_TEST_DATABASE_URL"
}

ensure_test_postgres

if docker_accessible && [[ -z "${STOW_TEST_DATABASE_URL:-}" ]]; then
  echo "Running: uv run pytest (testcontainers)"
elif [[ $# -eq 0 ]]; then
  echo "Running with STOW_TEST_DATABASE_URL=$STOW_TEST_DATABASE_URL"
  echo "Running: uv run pytest tests/"
else
  echo "Running with STOW_TEST_DATABASE_URL=$STOW_TEST_DATABASE_URL"
  echo "Running: uv run pytest $*"
fi

if [[ $# -eq 0 ]]; then
  exec uv run pytest tests/
else
  exec uv run pytest "$@"
fi
