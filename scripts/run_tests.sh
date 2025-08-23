#!/bin/bash
# Скрипт запуска тестов согласно решению координатора
# Поддерживает 3 уровня: unit (30с), integration (2м), e2e (15м)

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции вывода
print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[✓]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
print_error() { echo -e "${RED}[✗]${NC} $1"; }

# Проверка Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker не установлен!"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker не запущен!"
        exit 1
    fi
}

# Запуск тестовой инфраструктуры
start_test_env() {
    print_status "Запускаем тестовое окружение..."
    
    # Создаем docker-compose.test.yml если его нет
    if [ ! -f "docker-compose.test.yml" ]; then
        cat > docker-compose.test.yml << 'EOF'
version: '3.8'

services:
  test-db:
    image: postgres:15
    environment:
      POSTGRES_DB: test_botdb
      POSTGRES_USER: test_bot
      POSTGRES_PASSWORD: test_pass
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test_bot -d test_botdb"]
      interval: 5s
      timeout: 5s
      retries: 5
      
  test-redis:
    image: redis:7
    ports:
      - "6380:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
EOF
    fi
    
    # Запускаем контейнеры
    docker-compose -f docker-compose.test.yml up -d
    
    # Ждем готовности
    print_status "Ждем готовности БД..."
    sleep 5
    
    # Применяем миграции для тестовой БД
    print_status "Применяем миграции..."
    TEST_DB_PORT=5433 python admin/manage.py migrate --run-syncdb 2>/dev/null || true
}

# Остановка тестовой инфраструктуры
stop_test_env() {
    print_status "Останавливаем тестовое окружение..."
    docker-compose -f docker-compose.test.yml down
}

# Установка зависимостей для тестов
install_test_deps() {
    if [ ! -f ".test_deps_installed" ]; then
        print_status "Устанавливаем зависимости для тестов..."
        pip install -q -r requirements-test.txt
        
        # Playwright для E2E админки
        pip install -q playwright pytest-playwright
        playwright install chromium --with-deps
        
        # Опционально: Pyrogram для реальных Telegram тестов
        if [ -f ".env.test" ]; then
            pip install -q pyrogram tgcrypto
        fi
        
        touch .test_deps_installed
    fi
}

# Unit тесты (быстрые, 30 сек)
run_unit_tests() {
    print_status "Запускаем Unit тесты (цель: <30 сек)..."
    start_time=$(date +%s)
    
    pytest tests/unit/ -v --tb=short --timeout=10 \
        --cov=bot --cov=admin \
        --cov-report=term-missing:skip-covered \
        --cov-report=html:htmlcov/unit
    
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    
    if [ $duration -le 30 ]; then
        print_success "Unit тесты завершены за ${duration} сек ✅"
    else
        print_warning "Unit тесты заняли ${duration} сек (цель: 30 сек)"
    fi
}

# Integration тесты (2 минуты)
run_integration_tests() {
    print_status "Запускаем Integration тесты (цель: <2 мин)..."
    start_test_env
    start_time=$(date +%s)
    
    pytest tests/integration/ -v --tb=short --timeout=30 \
        --cov=bot --cov=admin \
        --cov-report=term-missing:skip-covered \
        --cov-report=html:htmlcov/integration
    
    local result=$?
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    
    stop_test_env
    
    if [ $duration -le 120 ]; then
        print_success "Integration тесты завершены за $((duration/60))м $((duration%60))с ✅"
    else
        print_warning "Integration тесты заняли $((duration/60))м $((duration%60))с (цель: 2 мин)"
    fi
    
    return $result
}

# E2E тесты (15 минут)
run_e2e_tests() {
    print_status "Запускаем E2E тесты (цель: <15 мин)..."
    
    # Проверяем запущен ли основной проект
    if ! docker ps | grep -q "tg-bot"; then
        print_warning "Основной проект не запущен. Запускаем..."
        docker-compose up -d
        sleep 10
    fi
    
    start_time=$(date +%s)
    
    # E2E админки (Playwright)
    print_status "E2E тесты админки..."
    pytest tests/e2e/admin/ -v --tb=short --timeout=60 \
        --cov=admin \
        --cov-report=term-missing:skip-covered
    
    # E2E Telegram (если включено)
    if [ "${ENABLE_E2E_TELEGRAM}" = "1" ]; then
        if [ -f ".env.test" ]; then
            print_status "E2E тесты Telegram (реальные)..."
            source .env.test
            pytest tests/e2e/telegram/ -v --tb=short --timeout=120 \
                --cov=bot \
                --cov-report=term-missing:skip-covered
        else
            print_warning ".env.test не найден, пропускаем реальные Telegram тесты"
        fi
    else
        print_warning "E2E Telegram тесты отключены (установите ENABLE_E2E_TELEGRAM=1)"
    fi
    
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    
    if [ $duration -le 900 ]; then
        print_success "E2E тесты завершены за $((duration/60))м $((duration%60))с ✅"
    else
        print_warning "E2E тесты заняли $((duration/60))м $((duration%60))с (цель: 15 мин)"
    fi
}

# Отчет о покрытии
generate_coverage_report() {
    print_status "Генерируем отчет о покрытии..."
    
    coverage combine 2>/dev/null || true
    coverage report
    coverage html
    
    total_coverage=$(coverage report | grep TOTAL | awk '{print $4}' | sed 's/%//')
    
    if [ "${total_coverage%.*}" -ge 80 ]; then
        print_success "Покрытие кода: ${total_coverage}% (цель: 80%) 🎉"
    elif [ "${total_coverage%.*}" -ge 60 ]; then
        print_warning "Покрытие кода: ${total_coverage}% (минимум: 60%, цель: 80%)"
    else
        print_error "Покрытие кода: ${total_coverage}% (ниже минимума 60%!)"
        exit 1
    fi
    
    print_status "HTML отчет: htmlcov/index.html"
}

# Smoke тесты (быстрая проверка)
run_smoke_tests() {
    print_status "Запускаем Smoke тесты..."
    pytest -v -m smoke --tb=short --timeout=5
    print_success "Smoke тесты пройдены"
}

# Pre-commit проверка (для git hook)
run_precommit() {
    print_status "Pre-commit проверка..."
    
    # Только быстрые unit тесты
    pytest tests/unit/ -q --tb=line --timeout=10
    
    # Линтеры (если установлены)
    if command -v black &> /dev/null; then
        black --check bot/ admin/
    fi
    
    if command -v flake8 &> /dev/null; then
        flake8 bot/ admin/ --max-line-length=120
    fi
    
    print_success "Pre-commit проверка пройдена"
}

# Главная функция
main() {
    check_docker
    install_test_deps
    
    case "${1:-all}" in
        unit)
            run_unit_tests
            ;;
        integration)
            run_integration_tests
            ;;
        e2e)
            run_e2e_tests
            ;;
        smoke)
            run_smoke_tests
            ;;
        precommit)
            run_precommit
            ;;
        coverage)
            run_unit_tests
            run_integration_tests
            generate_coverage_report
            ;;
        all)
            print_status "Запуск ВСЕХ тестов..."
            run_unit_tests
            run_integration_tests
            run_e2e_tests
            generate_coverage_report
            ;;
        *)
            echo "Использование: $0 {unit|integration|e2e|smoke|precommit|coverage|all}"
            echo ""
            echo "  unit         - Быстрые unit-тесты (<30 сек)"
            echo "  integration  - Интеграционные тесты с БД (<2 мин)"
            echo "  e2e          - End-to-end тесты (<15 мин)"
            echo "  smoke        - Быстрая проверка основного функционала"
            echo "  precommit    - Проверка перед коммитом"
            echo "  coverage     - Полный прогон с отчетом о покрытии"
            echo "  all          - Все тесты + отчет"
            echo ""
            echo "Переменные окружения:"
            echo "  ENABLE_E2E_TELEGRAM=1  - Включить реальные Telegram тесты"
            echo "  DEBUG_TESTS=1          - Подробное логирование"
            exit 1
            ;;
    esac
}

# Запуск
main "$@"