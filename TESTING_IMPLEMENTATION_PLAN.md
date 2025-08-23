# 📅 План внедрения системы тестирования

> Согласовано с координатором. Готов принять первые PR по "День 0" сегодня.

## 🎯 Цели и метрики

### Ключевые метрики:
- **Покрытие кода**: 60% → 80% за месяц
- **Время unit-тестов**: < 30 секунд
- **Время integration**: < 2 минут  
- **Время E2E**: < 15 минут
- **Стабильность**: 0 случайных падений

### Критичные пути (100% покрытие):
1. Создание задач через календарь
2. Резолвер TopicBinding с кэшем
3. Правило P1 для ProjectMember
4. Проверка прав (can_assign, can_close)
5. 2-уровневая иерархия департаментов
6. Fallback при пустом ProjectMember

---

## 📋 День 0 (СЕГОДНЯ): Инфраструктура + быстрый gate

### ✅ Задачи на сегодня:

#### 1. Структура тестов (30 мин)
```bash
mkdir -p tests/{unit,integration,e2e/{admin,telegram}}
mkdir -p tests/fixtures
mkdir -p scripts

# Копируем артефакты
# conftest.py → tests/conftest.py
# test_full_scenario.py → tests/e2e/test_full_scenario.py
# run_tests.sh → scripts/run_tests.sh
chmod +x scripts/run_tests.sh
```

#### 2. Установка зависимостей (15 мин)
```bash
pip install -r requirements-test.txt
playwright install chromium
```

#### 3. Базовые unit-тесты (1 час)
Написать/проверить обязательные тесты:
- [x] `test_datetime_parse.py` - парсинг дат ✅ (уже есть)
- [x] `test_s0_roles_tasks.py` - роли и права ✅ (уже есть)
- [x] `test_s1_topics.py` - TopicBinding ✅ (уже есть)
- [ ] `test_p1_rule.py` - правило P1 (новый)
- [ ] `test_department_levels.py` - ограничение 2 уровней (новый)
- [ ] `test_empty_projectmember.py` - fallback (новый)

#### 4. Pre-commit hook (15 мин)
```bash
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
echo "🔍 Pre-commit проверка..."

# Проверка на sensitive файлы
if git diff --cached --name-only | grep -E "\.env\.test|\.session"; then
    echo "❌ Попытка закоммитить тестовые credentials!"
    exit 1
fi

# Быстрые unit-тесты
./scripts/run_tests.sh precommit
EOF

chmod +x .git/hooks/pre-commit
```

#### 5. Первый PR
```bash
git checkout -b feature/testing-infrastructure
git add tests/ scripts/ requirements-test.txt
git commit -m "feat(tests): добавлена инфраструктура тестирования

- 3-уровневая система: unit/integration/e2e
- conftest.py с фикстурами
- run_tests.sh с поддержкой флагов
- pre-commit hook для unit-тестов
- базовые unit-тесты критичных путей

Согласно решению координатора"
git push origin feature/testing-infrastructure
```

---

## 📋 День 1: UI и интеграция

### Задачи:

#### 1. Docker Compose для тестов (30 мин)
```yaml
# docker-compose.test.yml
version: '3.8'
services:
  test-db:
    image: postgres:15
    ports: ["5433:5432"]
    environment:
      POSTGRES_DB: test_botdb
      POSTGRES_USER: test_bot
      POSTGRES_PASSWORD: test_pass
  
  test-redis:
    image: redis:7
    ports: ["6380:6379"]
```

#### 2. Playwright тесты админки (2 часа)
- `test_projects.py` - CRUD проектов
- `test_departments.py` - иерархия и ограничения
- `test_users.py` - назначение ролей

#### 3. Integration тесты (2 часа)
- `test_db_models.py` - Django модели
- `test_redis_cache.py` - TTL 5 минут
- `test_resolver.py` - полная логика резолвера

#### 4. CI настройка (опционально)
```yaml
# .github/workflows/tests.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run tests
        run: |
          ./scripts/run_tests.sh unit
          ./scripts/run_tests.sh integration
```

---

## 📋 День 2: Telegram E2E

### Задачи:

#### 1. Создание тестового аккаунта (30 мин)
- Купить виртуальный номер ($0.20)
- Зарегистрировать аккаунт
- Получить api_id/api_hash
- Сгенерировать session_string

#### 2. Настройка .env.test (15 мин)
```bash
cp .env.example .env.test
# Заполнить TEST_* переменные
# Добавить в .gitignore
```

#### 3. E2E тесты Pyrogram (2 часа)
- `test_real_commands.py` - команды бота
- `test_real_calendar.py` - выбор дат
- `test_real_topics.py` - работа с топиками

#### 4. Запуск с флагом
```bash
ENABLE_E2E_TELEGRAM=1 ./scripts/run_tests.sh e2e
```

---

## 📋 CI/CRON настройка

### GitHub Actions:
```yaml
# .github/workflows/nightly.yml
name: Nightly Tests
on:
  schedule:
    - cron: '0 2 * * *'  # 2:00 UTC ежедневно
jobs:
  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Integration tests
        run: ./scripts/run_tests.sh integration
```

### Pre-release:
```yaml
# .github/workflows/release.yml  
name: Release Tests
on:
  push:
    tags: ['v*']
jobs:
  full:
    runs-on: ubuntu-latest
    steps:
      - name: Full test suite
        env:
          ENABLE_E2E_TELEGRAM: ${{ secrets.ENABLE_E2E_TELEGRAM }}
          TEST_SESSION_STRING: ${{ secrets.TEST_SESSION_STRING }}
        run: ./scripts/run_tests.sh all
```

---

## 📊 Мониторинг прогресса

### Неделя 1:
- [ ] День 0: Базовая инфраструктура ✅
- [ ] День 1: UI/Integration тесты
- [ ] День 2: Telegram E2E
- [ ] Coverage > 60%

### Неделя 2:
- [ ] Дописать недостающие тесты
- [ ] Настроить CI/CD
- [ ] Coverage > 70%

### Неделя 3-4:
- [ ] Рефакторинг flaky тестов
- [ ] Оптимизация скорости
- [ ] Coverage > 80%
- [ ] Документация

---

## ✅ Чек-лист готовности к production

### Инфраструктура:
- [ ] 3-уровневая система тестов работает
- [ ] Pre-commit hook настроен
- [ ] CI/CD pipeline настроен

### Покрытие:
- [ ] Unit: все критичные функции
- [ ] Integration: БД и кэш
- [ ] E2E: основные сценарии

### Безопасность:
- [ ] .env.test в .gitignore
- [ ] Session string защищен
- [ ] Флаг ENABLE_E2E_TELEGRAM работает

### Качество:
- [ ] Покрытие ≥ 60% (старт)
- [ ] Время выполнения в пределах целей
- [ ] 0 flaky тестов
- [ ] Логирование настроено

---

## 🚀 Команды для старта

```bash
# Сегодня (День 0)
./scripts/run_tests.sh unit         # < 30 сек
git add . && git commit -m "..."    # pre-commit сработает
git push                             # Первый PR

# Завтра (День 1)  
./scripts/run_tests.sh integration  # < 2 мин

# Послезавтра (День 2)
ENABLE_E2E_TELEGRAM=1 ./scripts/run_tests.sh e2e  # < 15 мин

# Полный прогон
./scripts/run_tests.sh all
```

---

**Координатор готов принять PR сегодня. Начинаем! 🚀**