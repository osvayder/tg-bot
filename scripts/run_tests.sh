#!/usr/bin/env bash
set -Eeuo pipefail

compose="docker-compose"
svc="admin"

usage() {
  cat <<'EOF'
Usage: scripts/run_tests.sh <pre-commit|unit|integration|e2e-telegram|all>

  pre-commit   - быстрые unit (≤30 сек)
  unit         - все unit
  integration  - интеграция + E2E админка (Playwright)
  e2e-telegram - реальные Telegram E2E (нужен .env.test)
  all          - unit + integration (+ e2e-telegram если ENABLE_E2E_TELEGRAM=1 и .env.test найден)
EOF
}

ensure_deps() {
  $compose exec -T $svc python -m pip install -r requirements-test.txt
}

ensure_playwright() {
  $compose exec -T $svc python -m playwright install --with-deps || true
}

run_pytest() {
  $compose exec -T $svc python -m pytest "$@"
}

load_env_test() {
  if [[ ! -f .env.test ]]; then
    echo "Нет .env.test — заполните по шаблону .env.test.example"; exit 2
  fi
  # Экспортим пары KEY=VALUE из .env.test
  export $(grep -v '^#' .env.test | xargs -d '\n' -I{} echo {})
}

case "${1:-}" in
  pre-commit)
    run_pytest tests/unit -q
    ;;
  unit)
    ensure_deps
    run_pytest tests/unit -q
    ;;
  integration)
    ensure_deps
    ensure_playwright
    run_pytest tests/integration tests/e2e/admin -v
    ;;
  e2e-telegram)
    ensure_deps
    load_env_test
    run_pytest tests/e2e/telegram -v
    ;;
  all)
    ensure_deps
    run_pytest tests/unit -q
    ensure_playwright
    run_pytest tests/integration tests/e2e/admin -v
    if [[ "${ENABLE_E2E_TELEGRAM:-0}" == "1" && -f .env.test ]]; then
      load_env_test
      run_pytest tests/e2e/telegram -v
    else
      echo "Telegram E2E пропущены (ENABLE_E2E_TELEGRAM!=1 или нет .env.test)"
    fi
    ;;
  *)
    usage; exit 1;;
esac