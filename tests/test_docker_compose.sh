#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
docker compose config --quiet
echo "docker compose config: OK"
