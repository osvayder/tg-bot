"""Простой тест для проверки инфраструктуры"""

def test_simple_pass():
    """Тест который всегда проходит"""
    assert 1 + 1 == 2

def test_django_setup():
    """Проверка что Django настроен"""
    from django.conf import settings
    assert settings.DEBUG is not None