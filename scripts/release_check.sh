#!/usr/bin/env bash
set -euo pipefail

echo "==> Python compile check"
python -m compileall backend cli

echo "==> pytest"
pytest

echo "==> frontend build"
(
  cd frontend
  npm run build
)

echo "==> docker compose config"
docker compose config >/dev/null

echo "==> CLI version"
python -m dailychewer.cli version

echo "==> CLI doctor"
python -m dailychewer.cli doctor

if docker info >/dev/null 2>&1; then
  echo "==> Docker daemon detected, building Python images"
  docker compose build dailychewer backend
else
  echo "==> Docker daemon not available, skipping docker compose build"
fi

echo "PASS"
