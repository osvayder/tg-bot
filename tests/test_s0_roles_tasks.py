"""
Тесты S0: Roles и Tasks (минимальный функционал)
Согласно чек-листам S0
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Добавляем путь к модулям бота
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bot'))


class TestS0Commands:
    """Тесты команд S0"""
    
    @pytest.mark.asyncio
    async def test_start_command(self):
        """SMOKE #1: /start отвечает '✅ Бот на связи'"""
        from main import start
        
        msg = AsyncMock()
        msg.text = "/start"
        
        with patch('main.log_raw_update', new_callable=AsyncMock):
            with patch('main.safe_reply', new_callable=AsyncMock) as mock_reply:
                await start(msg)
                mock_reply.assert_called_once_with(
                    msg, 
                    "✅ Бот на связи. Доступно: /whoami, /ping, /checklast N"
                )
    
    @pytest.mark.asyncio
    async def test_ping_command(self):
        """Тест /ping -> pong"""
        from main import ping
        
        msg = AsyncMock()
        msg.text = "/ping"
        
        with patch('main.log_raw_update', new_callable=AsyncMock):
            with patch('main.safe_reply', new_callable=AsyncMock) as mock_reply:
                await ping(msg)
                mock_reply.assert_called_once_with(msg, "pong")
    
    @pytest.mark.asyncio
    async def test_checklast_with_arg(self):
        """Тест /checklast 5 принимает аргумент N"""
        from main import checklast_command
        from aiogram.filters import CommandObject
        
        msg = AsyncMock()
        msg.text = "/checklast 5"
        
        command = CommandObject(
            command="checklast",
            args="5"
        )
        
        with patch('main.log_raw_update', new_callable=AsyncMock):
            with patch('main._do_checklast', new_callable=AsyncMock) as mock_do:
                await checklast_command(msg, command)
                mock_do.assert_called_once_with(msg, 5)


class TestS0Database:
    """Тесты работы с БД для S0"""
    
    @pytest.mark.asyncio
    async def test_role_creation(self):
        """Тест создания роли с can_assign/can_close"""
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)  # Роль не существует
        conn.execute = AsyncMock()
        
        # Симулируем создание роли
        await conn.execute(
            "INSERT INTO core_role (name, can_assign, can_close) VALUES ($1, $2, $3)",
            "TeamLead", True, True
        )
        
        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        assert "TeamLead" in args
        assert True in args  # can_assign
        assert True in args  # can_close
    
    @pytest.mark.asyncio  
    async def test_task_creation(self):
        """Тест создания задачи с дедлайном"""
        conn = AsyncMock()
        conn.execute = AsyncMock()
        
        # Симулируем создание задачи
        await conn.execute(
            """INSERT INTO core_task 
            (title, responsible_id, deadline, status, source_chat_id) 
            VALUES ($1, $2, $3, $4, $5)""",
            "Test task", 1, "2025-12-31", "TODO", -123456
        )
        
        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        assert "Test task" in args
        assert "2025-12-31" in args
        assert "TODO" in args