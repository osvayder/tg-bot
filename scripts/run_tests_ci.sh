#!/usr/bin/env bash
set -Eeuo pipefail

# Simple CI test runner that runs inside container
# Usage: docker compose exec admin bash scripts/run_tests_ci.sh <target>

export PYTHONPATH="${PYTHONPATH:-.}:/app:/app/admin"

target="${1:-unit}"

echo "Running tests: $target"
echo "Python path: $PYTHONPATH"
echo "Current directory: $(pwd)"

# Find requirements file (try multiple locations)
REQ_FILE=""
for c in requirements-test.txt test-requirements.txt admin/requirements-test.txt; do
  if [ -f "$c" ]; then
    REQ_FILE="$c"
    echo "Found requirements file: $REQ_FILE"
    break
  fi
done

if [ -z "$REQ_FILE" ]; then
  echo "No requirements file found, will use minimal dependencies"
fi

case "$target" in
  unit)
    # Django env for pytest-django - CRITICAL CONFIG
    export PYTHONPATH="/app:/app/admin:${PYTHONPATH:-.}"
    export DJANGO_SETTINGS_MODULE="settings"
    
    echo "=== Environment setup ==="
    echo "  PYTHONPATH=$PYTHONPATH"
    echo "  DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE"
    echo "  Working directory: $(pwd)"
    echo "  Python version: $(python --version)"
    
    echo "=== Installing dependencies ==="
    # Try to use unified requirements file first
    if [ -f "admin/requirements-test.txt" ]; then
      echo "Installing from admin/requirements-test.txt..."
      pip install -q -r admin/requirements-test.txt
    elif [ -f "requirements-test.txt" ]; then
      echo "Installing from requirements-test.txt..."
      pip install -q -r requirements-test.txt
    else
      echo "Installing minimal dependencies..."
      pip install -q pytest pytest-asyncio==0.21.0 pytest-django
    fi
    
    # Verify Django setup
    echo "=== Verifying Django setup ==="
    python -c "import sys; print('Python path:', sys.path[:3])" || true
    python -c "import django; print(f'Django {django.__version__} OK')" || echo "Django import failed"
    python -c "from django.conf import settings; print(f'Settings module: {settings.SETTINGS_MODULE if hasattr(settings, \"SETTINGS_MODULE\") else \"OK\"}')" || echo "Settings not configured"
    
    echo "=== Running unit tests ==="
    cd /app && python -m pytest tests/unit -vv -rA --maxfail=1 --tb=short --disable-warnings
    ;;
    
  integration)
    echo "Installing integration test dependencies..."
    if [ -n "$REQ_FILE" ]; then 
      pip install -q -r "$REQ_FILE"
    else 
      pip install -q pytest pytest-django pytest-playwright
    fi
    
    # Browsers and system deps for Playwright (required, no error ignore)
    echo "Installing Playwright browsers..."
    python -m playwright install --with-deps
    
    echo "Running integration tests..."
    python -m pytest tests/integration tests/e2e/admin -v
    ;;
    
  e2e-telegram)
    : "${ENABLE_E2E_TELEGRAM:=0}"
    [ "$ENABLE_E2E_TELEGRAM" = "1" ] || { echo "E2E Telegram disabled"; exit 0; }
    
    echo "Installing E2E dependencies..."
    if [ -n "$REQ_FILE" ]; then 
      pip install -q -r "$REQ_FILE"
    else 
      pip install -q pytest pytest-django pyrogram
    fi
    
    echo "Running E2E Telegram tests..."
    python -m pytest tests/e2e/telegram -v
    ;;
    
  *)
    echo "Unknown target: $target"
    exit 1
    ;;
esac

echo "Tests completed: $target"