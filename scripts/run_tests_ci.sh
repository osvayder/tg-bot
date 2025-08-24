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
    export PYTHONPATH="${PYTHONPATH:-.}:$(pwd):$(pwd)/admin"
    export DJANGO_SETTINGS_MODULE="admin.settings"
    echo "Environment setup:"
    echo "  PYTHONPATH=$PYTHONPATH"
    echo "  DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE"
    echo "  Working directory: $(pwd)"
    echo "Installing unit test dependencies..."
    pip install -q -r admin/requirements-test.txt 2>/dev/null || pip install -q pytest pytest-asyncio==0.21.0 pytest-django
    echo "Running unit tests..."
    python -m pytest tests/unit -vv -rA --maxfail=1 --disable-warnings || {
      echo "Tests failed with exit code $?"
      echo "Retrying with minimal config..."
      python -m pytest tests/unit -vv -rA --maxfail=1 --disable-warnings --no-cov -p no:django || true
      exit 1
    }
    ;;
  integration)
    echo "Installing integration test dependencies..."
    pip install -q -r admin/requirements-test.txt 2>/dev/null || pip install -q pytest pytest-django pytest-playwright
    python -m playwright install --with-deps
    echo "Running integration tests..."
    python -m pytest tests/integration tests/e2e/admin -v
    ;;
  e2e-telegram)
    : "${ENABLE_E2E_TELEGRAM:=0}"
    [ "$ENABLE_E2E_TELEGRAM" = "1" ] || { echo "E2E Telegram disabled"; exit 0; }
    echo "Installing E2E dependencies..."
    pip install -q -r admin/requirements-test.txt 2>/dev/null || pip install -q pytest pytest-django pyrogram
    echo "Running E2E Telegram tests..."
    python -m pytest tests/e2e/telegram -v
    ;;
  *)
    echo "Unknown target: $target"
    exit 1
    ;;
esac

echo "Tests completed: $target"