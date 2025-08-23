"""
Главный конфигурационный файл pytest
Настройки для всех типов тестов с учетом решения координатора
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import AsyncGenerator, Generator
import json

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

# Добавляем корневую папку в путь
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "bot"))
sys.path.insert(0, str(ROOT_DIR / "admin"))

# Настройки для asyncio
pytest_plugins = ['pytest_asyncio']


# ============= БАЗОВЫЕ ФИКСТУРЫ =============

@pytest.fixture(scope="session")
def event_loop():
    """Создаем event loop для всей сессии тестов"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_bot():
    """Мок Telegram бота"""
    bot = AsyncMock()
    bot.get_me = AsyncMock(return_value=MagicMock(
        id=123456789,
        username="test_bot",
        first_name="Test Bot"
    ))
    return bot


@pytest.fixture
def mock_message():
    """Мок сообщения Telegram"""
    msg = AsyncMock()
    msg.chat = MagicMock()
    msg.chat.id = -100123456789
    msg.chat.type = "supergroup"
    msg.from_user = MagicMock()
    msg.from_user.id = 987654321
    msg.from_user.username = "testuser"
    msg.from_user.is_bot = False
    msg.message_id = 1
    msg.text = "Test message"
    msg.message_thread_id = None  # топик
    return msg


# ============= БД ФИКСТУРЫ =============

@pytest.fixture
async def test_db_conn():
    """Подключение к тестовой БД"""
    import asyncpg
    
    # Используем тестовую БД на другом порту
    conn = await asyncpg.connect(
        user=os.getenv("TEST_DB_USER", "test_bot"),
        password=os.getenv("TEST_DB_PASSWORD", "test_pass"),
        database=os.getenv("TEST_DB_NAME", "test_botdb"),
        host=os.getenv("TEST_DB_HOST", "localhost"),
        port=int(os.getenv("TEST_DB_PORT", "5433")),
    )
    
    # Очищаем таблицы перед тестом
    await conn.execute("TRUNCATE core_task, core_user, core_role CASCADE")
    
    yield conn
    
    # Очищаем после теста
    await conn.execute("TRUNCATE core_task, core_user, core_role CASCADE")
    await conn.close()


@pytest.fixture
def django_settings():
    """Настройки Django для тестов"""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    
    # Переопределяем БД на тестовую
    from django.conf import settings
    settings.DATABASES['default'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv("TEST_DB_NAME", "test_botdb"),
        'USER': os.getenv("TEST_DB_USER", "test_bot"),
        'PASSWORD': os.getenv("TEST_DB_PASSWORD", "test_pass"),
        'HOST': os.getenv("TEST_DB_HOST", "localhost"),
        'PORT': os.getenv("TEST_DB_PORT", "5433"),
    }
    
    import django
    django.setup()


# ============= REDIS ФИКСТУРЫ =============

@pytest.fixture
async def test_redis():
    """Подключение к тестовому Redis"""
    import redis.asyncio as aioredis
    
    client = aioredis.Redis(
        host=os.getenv("TEST_REDIS_HOST", "localhost"),
        port=int(os.getenv("TEST_REDIS_PORT", "6380")),
        db=int(os.getenv("TEST_REDIS_DB", "1")),
        decode_responses=True,
    )
    
    # Очищаем БД
    await client.flushdb()
    
    yield client
    
    # Очищаем после теста
    await client.flushdb()
    await client.close()


# ============= PLAYWRIGHT (E2E админка) =============

@pytest.fixture(scope="session")
def playwright_browser():
    """Браузер для E2E тестов админки"""
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        # Используем headless Chrome
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        yield browser
        browser.close()


@pytest.fixture
def admin_page(playwright_browser):
    """Страница админки с авторизацией"""
    context = playwright_browser.new_context()
    page = context.new_page()
    
    # Логинимся
    page.goto("http://localhost:8000/admin/")
    page.fill("#id_username", "admin")
    page.fill("#id_password", "admin")
    page.click("input[type='submit']")
    
    # Ждем загрузки дашборда
    page.wait_for_selector("#site-name", timeout=5000)
    
    yield page
    
    context.close()


# ============= PYROGRAM (E2E Telegram) =============

@pytest.fixture(scope="session")
async def telegram_test_client():
    """Реальный Telegram клиент для E2E тестов"""
    # Проверяем флаг включения E2E тестов
    if not os.getenv("ENABLE_E2E_TELEGRAM", "").lower() in ("1", "true", "yes"):
        pytest.skip("E2E Telegram тесты отключены. Установите ENABLE_E2E_TELEGRAM=1")
    
    from pyrogram import Client
    
    # Эти переменные должны быть в .env.test
    api_id = os.getenv("TEST_API_ID")
    api_hash = os.getenv("TEST_API_HASH")
    session_string = os.getenv("TEST_SESSION_STRING")
    
    if not all([api_id, api_hash, session_string]):
        pytest.skip("Telegram test credentials not configured in .env.test")
    
    client = Client(
        "test_session",
        api_id=int(api_id),
        api_hash=api_hash,
        session_string=session_string
    )
    
    await client.start()
    yield client
    await client.stop()


# ============= ТЕСТОВЫЕ ДАННЫЕ =============

@pytest.fixture
def test_project_data():
    """Тестовые данные проекта"""
    return {
        "project": {"name": "Test Project", "status": "active"},
        "roles": [
            {"name": "Producer", "can_assign": True, "can_close": True},
            {"name": "Animator", "can_assign": False, "can_close": False},
        ],
        "departments": [
            {"name": "Production", "parent": None},
            {"name": "Animation", "parent": "Production"},
        ],
        "users": [
            {"username": "ivan", "telegram_id": 111111, "role": "Producer"},
            {"username": "maria", "telegram_id": 222222, "role": "Animator"},
        ]
    }


# ============= МАРКЕРЫ =============

def pytest_configure(config):
    """Регистрация маркеров"""
    config.addinivalue_line(
        "markers", "unit: быстрые unit-тесты (30 сек)"
    )
    config.addinivalue_line(
        "markers", "integration: интеграционные тесты с БД (2 мин)"
    )
    config.addinivalue_line(
        "markers", "e2e: end-to-end тесты (15 мин)"
    )
    config.addinivalue_line(
        "markers", "admin: тесты Django админки через Playwright"
    )
    config.addinivalue_line(
        "markers", "telegram: реальные Telegram тесты (требует ENABLE_E2E_TELEGRAM=1)"
    )
    config.addinivalue_line(
        "markers", "smoke: smoke тесты для быстрой проверки"
    )


# ============= ХУКИ =============

def pytest_collection_modifyitems(config, items):
    """Автоматически добавляем маркеры по путям файлов"""
    for item in items:
        # Добавляем маркеры по структуре папок
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
            
            if "admin" in str(item.fspath):
                item.add_marker(pytest.mark.admin)
            elif "telegram" in str(item.fspath):
                item.add_marker(pytest.mark.telegram)


# ============= ЛОГИРОВАНИЕ =============

@pytest.fixture(autouse=True)
def configure_logging():
    """Настройка логирования для тестов"""
    import logging
    
    logging.basicConfig(
        level=logging.DEBUG if os.getenv("DEBUG_TESTS") else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Отключаем логи от некоторых библиотек
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)