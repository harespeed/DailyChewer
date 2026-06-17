#!/usr/bin/env bash
set -euo pipefail

MODE="all"
BUILD="true"
OPEN_CLI="false"

usage() {
  cat <<'EOF'
Usage: scripts/start_dailychewer.sh [options]

Options:
  --all          Build images and start GUI backend/frontend. Default.
  --gui          Build images and start GUI backend/frontend.
  --cli          Build images, start shared backend, then enter CLI/TUI.
  --build-only   Only build images.
  --no-build     Skip build and only start/run services.
  --help         Show this help.

Examples:
  scripts/start_dailychewer.sh
  scripts/start_dailychewer.sh --cli
  scripts/start_dailychewer.sh --no-build --gui
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)
      MODE="all"
      ;;
    --gui)
      MODE="gui"
      ;;
    --cli)
      MODE="cli"
      OPEN_CLI="true"
      ;;
    --build-only)
      MODE="build-only"
      ;;
    --no-build)
      BUILD="false"
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
  shift
done

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

export COMPOSE_IGNORE_ORPHANS="${COMPOSE_IGNORE_ORPHANS:-true}"
export USE_CHINA_MIRROR="${USE_CHINA_MIRROR:-true}"
export APT_MIRROR="${APT_MIRROR:-http://mirrors.aliyun.com/debian}"
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple}"
export PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-mirrors.aliyun.com}"
export NPM_CONFIG_REGISTRY="${NPM_CONFIG_REGISTRY:-https://registry.npmmirror.com}"

GUI_COMPOSE=(docker compose -f docker-compose-gui.yml)
CLI_COMPOSE=(docker compose -f docker-compose-cli.yml)

build_images() {
  echo "==> Building backend/CLI image with domestic mirrors"
  "${CLI_COMPOSE[@]}" build cli backend

  echo "==> Building frontend image with domestic npm registry"
  "${GUI_COMPOSE[@]}" build frontend
}

start_gui() {
  echo "==> Starting GUI stack"
  "${GUI_COMPOSE[@]}" up -d backend frontend
  echo "GUI: http://localhost:5173"
  echo "API: http://localhost:8000"
}

start_backend_for_cli() {
  echo "==> Starting shared backend for CLI"
  "${CLI_COMPOSE[@]}" up -d backend
}

enter_cli() {
  echo "==> Entering DailyChewer CLI/TUI"
  "${CLI_COMPOSE[@]}" run --rm cli
}

if [[ "${BUILD}" == "true" ]]; then
  build_images
fi

case "${MODE}" in
  build-only)
    echo "Build completed."
    ;;
  all|gui)
    start_gui
    ;;
  cli)
    start_backend_for_cli
    enter_cli
    ;;
esac
