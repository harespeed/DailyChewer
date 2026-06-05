#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
FRONTEND_BASE_URL="${FRONTEND_BASE_URL:-http://localhost:5173}"
WITH_FRONTEND="false"

if [[ "${1:-}" == "--with-frontend" ]]; then
  WITH_FRONTEND="true"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not available"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is not available"
  exit 1
fi

echo "Starting postgres..."
docker compose up -d postgres

echo "Initializing database..."
docker compose run --rm dailychewer db init

echo "Starting backend..."
docker compose up -d backend

if [[ "${WITH_FRONTEND}" == "true" ]]; then
  echo "Starting frontend..."
  docker compose up -d frontend
fi

echo "Waiting for backend health..."
for _ in $(seq 1 30); do
  if curl -fsS "${API_BASE_URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -fsS "${API_BASE_URL}/api/health" >/dev/null

if [[ "${WITH_FRONTEND}" == "true" ]]; then
  echo "Waiting for frontend..."
  for _ in $(seq 1 30); do
    if curl -fsS "${FRONTEND_BASE_URL}" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  curl -fsS "${FRONTEND_BASE_URL}" >/dev/null
fi

echo "Registering users..."
curl -fsS -X POST "${API_BASE_URL}/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"user_a","password":"password123","display_name":"User A"}' >/dev/null || true
curl -fsS -X POST "${API_BASE_URL}/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"user_b","password":"password123","display_name":"User B"}' >/dev/null || true

echo "Logging in..."
TOKEN_A="$(
  curl -fsS -X POST "${API_BASE_URL}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"user_a","password":"password123"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])"
)"
TOKEN_B="$(
  curl -fsS -X POST "${API_BASE_URL}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"user_b","password":"password123"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])"
)"

echo "Checking auth/me..."
curl -fsS "${API_BASE_URL}/api/auth/me" -H "Authorization: Bearer ${TOKEN_A}" >/dev/null
curl -fsS "${API_BASE_URL}/api/auth/me" -H "Authorization: Bearer ${TOKEN_B}" >/dev/null

echo "Checking unauthenticated protection..."
HTTP_STATUS="$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE_URL}/api/reports")"
if [[ "${HTTP_STATUS}" != "401" ]]; then
  echo "Expected 401 for unauthenticated /api/reports, got ${HTTP_STATUS}"
  exit 1
fi

echo "Checking user-scoped /api/reports..."
REPORTS_A="$(curl -fsS "${API_BASE_URL}/api/reports" -H "Authorization: Bearer ${TOKEN_A}")"
REPORTS_B="$(curl -fsS "${API_BASE_URL}/api/reports" -H "Authorization: Bearer ${TOKEN_B}")"
python - <<'PY' "${REPORTS_A}" "${REPORTS_B}"
import json
import sys

reports_a = json.loads(sys.argv[1])
reports_b = json.loads(sys.argv[2])
assert isinstance(reports_a, list)
assert isinstance(reports_b, list)
print("Basic report scope checks passed.")
PY

echo "PASS"
