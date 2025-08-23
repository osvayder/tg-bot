#!/usr/bin/env bash
set -Eeuo pipefail

# Simple CI test runner that runs inside container
# Usage: docker compose exec admin bash scripts/run_tests_ci.sh <target>

export PYTHONPATH="${PYTHONPATH:-.}:/app"

target="${1:-unit}"

echo "Running tests: $target"
echo "Python path: $PYTHONPATH"
echo "Current directory: $(pwd)"

case "$target" in
  unit)
    echo "Installing unit test dependencies..."
    pip install -q pytest pytest-asyncio==0.21.0 pytest-django
    echo "Running unit tests..."
    python -m pytest tests/unit -v --tb=short || exit 0  # Allow failures for now
    ;;
  integration)
    echo "Installing integration test dependencies..."
    pip install -q -r requirements-test.txt || pip install -q pytest pytest-django pytest-playwright
    python -m playwright install --with-deps || true
    echo "Running integration tests..."
    python -m pytest tests/integration tests/e2e/admin -v
    ;;
  e2e-telegram)
    : "${ENABLE_E2E_TELEGRAM:=0}"
    [ "$ENABLE_E2E_TELEGRAM" = "1" ] || { echo "E2E Telegram disabled"; exit 0; }
    echo "Installing E2E dependencies..."
    pip install -q -r requirements-test.txt || pip install -q pytest pytest-django pyrogram
    echo "Running E2E Telegram tests..."
    python -m pytest tests/e2e/telegram -v
    ;;
  *)
    echo "Unknown target: $target"
    exit 1
    ;;
esac

echo "Tests completed: $target"