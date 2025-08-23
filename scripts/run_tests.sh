#!/usr/bin/env bash
set -Eeuo pipefail

# Set PYTHONPATH for module imports
export PYTHONPATH="${PYTHONPATH:-.}:$(pwd)"

# autodetect docker compose CLI
if command -v docker compose >/dev/null 2>&1; then
  compose="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  compose="docker-compose"
else
  echo "docker compose/docker-compose not found"; exit 127
fi

svc="admin"

# Wait for service to be ready
wait_for_service() {
  echo "Waiting for $svc service to be ready..."
  for i in {1..30}; do
    if $compose exec -T $svc python -c "print('Service ready')" 2>/dev/null; then
      echo "Service $svc is ready"
      return 0
    fi
    echo "Waiting... ($i/30)"
    sleep 2
  done
  echo "Service $svc failed to become ready"
  return 1
}

usage() {
  cat <<'EOF'
Usage: scripts/run_tests.sh <pre-commit|unit|integration|e2e-telegram|all>
EOF
}

install_unit_deps() {
  $compose exec -T $svc python -m pip install -q pytest pytest-asyncio==0.21.0 pytest-django
}

install_full_deps() {
  $compose exec -T $svc python -m pip install -r requirements-test.txt
}

ensure_playwright() {
  $compose exec -T $svc python -m playwright install --with-deps || true
}

run_pytest() {
  $compose exec -T $svc python -m pytest "$@"
}

load_env_test() {
  [[ -f .env.test ]] || { echo "Нет .env.test"; exit 2; }
  export $(grep -v '^#' .env.test | xargs -d '\n' -I{} echo {})
}

cmd="${1:-}"; shift || true

# Ensure service is ready before running tests
wait_for_service || exit 1

case "$cmd" in
  pre-commit)
    install_unit_deps
    run_pytest tests/unit -q
    ;;
  unit)
    install_unit_deps
    run_pytest tests/unit -q
    ;;
  integration)
    install_full_deps
    ensure_playwright
    run_pytest tests/integration tests/e2e/admin -v
    ;;
  e2e-telegram)
    install_full_deps
    load_env_test
    run_pytest tests/e2e/telegram -v
    ;;
  all)
    install_unit_deps
    run_pytest tests/unit -q
    install_full_deps
    ensure_playwright
    run_pytest tests/integration tests/e2e/admin -v
    if [[ "${ENABLE_E2E_TELEGRAM:-0}" == "1" && -f .env.test ]]; then
      load_env_test
      run_pytest tests/e2e/telegram -v
    else
      echo "Telegram E2E пропущены"
    fi
    ;;
  *) usage; exit 1;;
esac