"""
Тесты для парсинга дедлайнов
"""

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bot'))

from services.datetime import parse_deadline


class TestDeadlineParsing:
    """Тесты парсинга дедлайнов с учетом временной зоны"""
    
    def test_full_datetime_format(self):
        """Тест формата YYYY-MM-DD HH:MM"""
        result = parse_deadline("2025-02-01 18:00", "Europe/Moscow")
        assert result is not None
        assert result.year == 2025
        assert result.month == 2
        assert result.day == 1
        assert result.hour == 18
        assert result.minute == 0
        assert result.tzinfo == ZoneInfo("Europe/Moscow")
    
    def test_date_only_format(self):
        """Тест формата YYYY-MM-DD (должно быть 23:59)"""
        result = parse_deadline("2025-02-01", "Europe/Moscow")
        assert result is not None
        assert result.year == 2025
        assert result.month == 2
        assert result.day == 1
        assert result.hour == 23
        assert result.minute == 59
    
    def test_time_only_today(self):
        """Тест формата HH:MM для времени в будущем сегодня"""
        tz = ZoneInfo("Europe/Moscow")
        now = datetime.now(tz)
        future_hour = (now.hour + 2) % 24
        
        result = parse_deadline(f"{future_hour:02d}:30", "Europe/Moscow")
        assert result is not None
        assert result.minute == 30
        
        # Если переход через полночь
        if future_hour < now.hour:
            assert result.day == (now + timedelta(days=1)).day
        else:
            assert result.day == now.day
    
    def test_time_only_tomorrow(self):
        """Тест формата HH:MM для прошедшего времени (должно быть завтра)"""
        tz = ZoneInfo("Europe/Moscow")
        now = datetime.now(tz)
        past_hour = max(0, now.hour - 2)
        
        result = parse_deadline(f"{past_hour:02d}:00", "Europe/Moscow")
        assert result is not None
        assert result.hour == past_hour
        assert result.minute == 0
        
        # Если время уже прошло, должно быть завтра
        test_time = now.replace(hour=past_hour, minute=0, second=0, microsecond=0)
        if test_time <= now:
            expected_day = (now + timedelta(days=1)).day
            assert result.day == expected_day
    
    def test_invalid_format(self):
        """Тест невалидного формата"""
        assert parse_deadline("invalid", "Europe/Moscow") is None
        assert parse_deadline("25:00", "Europe/Moscow") is None
        assert parse_deadline("2025-13-01", "Europe/Moscow") is None
        assert parse_deadline("", "Europe/Moscow") is None
    
    def test_different_timezone(self):
        """Тест с другой временной зоной"""
        result = parse_deadline("2025-02-01 12:00", "UTC")
        assert result is not None
        assert result.tzinfo == ZoneInfo("UTC")
        assert result.hour == 12