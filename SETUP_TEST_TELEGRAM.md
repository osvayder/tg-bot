# 📱 Настройка тестового Telegram для E2E тестирования

## ⚠️ Важно по безопасности (решение координатора)

1. **Используйте ТОЛЬКО тестовый аккаунт** - никогда не используйте основной
2. **session_string дает полный доступ** - храните в .env.test (в .gitignore)
3. **Регулярно обновляйте session** - каждые 2-3 месяца
4. **E2E тесты запускаются только с флагом** - ENABLE_E2E_TELEGRAM=1

## 📋 Шаг 1: Создание тестового аккаунта

### Вариант A: Виртуальный номер ($0.20)
1. Зайдите на https://sms-activate.org или аналог
2. Пополните баланс на $1
3. Купите номер для Telegram (обычно $0.20)
4. Зарегистрируйте аккаунт в Telegram

### Вариант B: Второй номер (если есть)
1. Используйте запасную SIM-карту
2. Зарегистрируйте новый аккаунт Telegram

## 📋 Шаг 2: Получение API credentials

1. Войдите на https://my.telegram.org с тестового аккаунта
2. Перейдите в "API development tools"
3. Создайте приложение:
   - **App title**: TG Bot Tests
   - **Short name**: tgbot_tests
   - **Platform**: Other
4. Сохраните:
   - **api_id**: (число)
   - **api_hash**: (строка)

## 📋 Шаг 3: Генерация session string

### Установите Pyrogram:
```bash
pip install pyrogram tgcrypto
```

### Создайте скрипт generate_session.py:
```python
from pyrogram import Client

api_id = input("Введите api_id: ")
api_hash = input("Введите api_hash: ")
phone = input("Введите номер телефона (с кодом страны): ")

with Client("test_session", api_id=int(api_id), api_hash=api_hash) as app:
    session_string = app.export_session_string()
    print("\nВаш session string:")
    print(session_string)
    print("\n⚠️ ВАЖНО: Сохраните его в .env.test и НИКОГДА не коммитьте!")
```

### Запустите и следуйте инструкциям:
```bash
python generate_session.py
# Введите api_id, api_hash, номер
# Введите код из Telegram
# Получите session_string
```

## 📋 Шаг 4: Создание тестового бота

1. Откройте @BotFather в Telegram
2. Отправьте `/newbot`
3. Имя: `Test Production Bot`
4. Username: `test_production_bot` (или другой свободный)
5. Сохраните токен бота

## 📋 Шаг 5: Создание тестовых групп

### Обычная группа:
1. Создайте группу "Test Production"
2. Добавьте тестового бота
3. Сделайте бота администратором
4. Получите ID группы (через @userinfobot или /whoami от бота)

### Супергруппа с топиками:
1. Создайте группу "Test Forum"
2. Настройки → Тип группы → Сделать общедоступной
3. Настройки → Темы → Включить темы
4. Добавьте бота и дайте права администратора
5. Создайте несколько топиков для тестов

## 📋 Шаг 6: Создание .env.test

```bash
# Telegram Test Credentials
TEST_API_ID=12345678
TEST_API_HASH=abcdef1234567890abcdef1234567890
TEST_SESSION_STRING=AQAOMTIzNDU2Nzg5...очень_длинная_строка...
TEST_PHONE=+79991234567

# Test Bot
TEST_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TEST_BOT_USERNAME=@test_production_bot

# Test Groups
TEST_GROUP_ID=-1001234567890
TEST_FORUM_GROUP_ID=-1001234567891
TEST_TOPIC_ID=5

# Test Database (для интеграционных тестов)
TEST_DB_HOST=localhost
TEST_DB_PORT=5433
TEST_DB_NAME=test_botdb
TEST_DB_USER=test_bot
TEST_DB_PASSWORD=test_pass

# Test Redis
TEST_REDIS_HOST=localhost
TEST_REDIS_PORT=6380
TEST_REDIS_DB=1
```

## 📋 Шаг 7: Добавление в .gitignore

```gitignore
# Test credentials - NEVER commit!
.env.test
*.session
*.session-journal
test_session.session
```

## 🚀 Запуск E2E тестов

### Только с флагом (согласно решению координатора):
```bash
# Включаем E2E Telegram тесты
export ENABLE_E2E_TELEGRAM=1

# Запускаем
./scripts/run_tests.sh e2e
```

### Без флага тесты пропускаются:
```bash
# По умолчанию E2E Telegram отключены
./scripts/run_tests.sh e2e
# Выполнятся только Playwright тесты админки
```

## 🔧 Отладка

### Проверка подключения:
```python
from pyrogram import Client
import os

client = Client(
    "test",
    session_string=os.getenv("TEST_SESSION_STRING")
)

async def test():
    async with client:
        me = await client.get_me()
        print(f"✅ Подключен как: {me.first_name} (@{me.username})")

import asyncio
asyncio.run(test())
```

### Проблемы и решения:

**Session expired**:
- Перегенерируйте session_string
- Убедитесь что аккаунт активен

**FloodWait error**:
- Добавьте задержки между запросами
- Используйте retry с exponential backoff

**ChatWriteForbidden**:
- Проверьте что бот добавлен в группу
- Проверьте права администратора

## 📊 Метрики успеха

- [ ] Тестовый аккаунт создан
- [ ] API credentials получены
- [ ] Session string сгенерирован
- [ ] Тестовый бот создан
- [ ] Группы настроены
- [ ] .env.test заполнен
- [ ] .gitignore обновлен
- [ ] Тест подключения пройден
- [ ] E2E тесты запускаются с флагом

## ⚠️ Безопасность - критически важно!

1. **НИКОГДА не коммитьте .env.test**
2. **НИКОГДА не используйте основной аккаунт**
3. **ВСЕГДА используйте флаг ENABLE_E2E_TELEGRAM=1**
4. **Регулярно проверяйте git status перед push**
5. **Используйте pre-commit hook для проверки**

## 📝 Pre-commit hook для безопасности

Создайте `.git/hooks/pre-commit`:
```bash
#!/bin/bash
# Проверка на случайный коммит sensitive данных

if git diff --cached --name-only | grep -E "\.env\.test|\.session|session_string"; then
    echo "❌ ОШИБКА: Попытка закоммитить sensitive файлы!"
    echo "Файлы .env.test и *.session должны быть в .gitignore"
    exit 1
fi

# Проверка на session_string в коде
if git diff --cached | grep -i "session_string" | grep -v "TEST_SESSION_STRING"; then
    echo "⚠️ ВНИМАНИЕ: Найден session_string в коде!"
    echo "Убедитесь что это не реальные данные"
    read -p "Продолжить? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Запуск быстрых тестов
./scripts/run_tests.sh precommit
```

Сделайте исполняемым:
```bash
chmod +x .git/hooks/pre-commit
```

---

**После настройки**: Вы готовы к полноценному E2E тестированию! 🎉