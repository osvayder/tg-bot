#!/usr/bin/env python3
"""
Скрипт для проверки конфигурации бота
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

def check_config():
    """Проверка конфигурации"""
    print("🔍 Проверка конфигурации Ninja Osvayder Bot")
    print("=" * 50)
    
    errors = []
    warnings = []
    
    # Проверка Python версии
    python_version = sys.version_info
    print(f"✅ Python версия: {python_version.major}.{python_version.minor}.{python_version.micro}")
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 8):
        errors.append("❌ Требуется Python 3.8 или выше")
    
    # Проверка Telegram токена
    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if telegram_token and telegram_token != 'YOUR_TELEGRAM_BOT_TOKEN_HERE':
        print(f"✅ Telegram токен: {'*' * 10}{telegram_token[-4:]}")
    else:
        errors.append("❌ Telegram токен не настроен в .env файле")
    
    # Проверка Google credentials
    google_creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'google-credentials.json')
    if Path(google_creds).exists():
        print(f"✅ Google credentials: {google_creds}")
    else:
        errors.append(f"❌ Google credentials файл не найден: {google_creds}")
    
    # Проверка Gemini API ключа
    gemini_key = os.getenv('GEMINI_API_KEY')
    if gemini_key:
        print(f"✅ Gemini API ключ: {'*' * 10}{gemini_key[-4:]}")
    else:
        warnings.append("⚠️  Gemini API ключ не настроен (потребуется для будущих функций)")
    
    # Проверка ffmpeg
    import subprocess
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            ffmpeg_version = result.stdout.split('\n')[0]
            print(f"✅ ffmpeg: установлен")
        else:
            warnings.append("⚠️  ffmpeg не работает корректно")
    except FileNotFoundError:
        warnings.append("⚠️  ffmpeg не установлен (нужен для работы с видео)")
    
    # Проверка директорий
    temp_dir = Path('temp_files')
    transcripts_dir = Path('transcripts')
    
    if not temp_dir.exists():
        temp_dir.mkdir(exist_ok=True)
        print("✅ Создана директория temp_files/")
    else:
        print("✅ Директория temp_files/ существует")
    
    if not transcripts_dir.exists():
        transcripts_dir.mkdir(exist_ok=True)
        print("✅ Создана директория transcripts/")
    else:
        print("✅ Директория transcripts/ существует")
    
    # Проверка зависимостей
    print("\n📦 Проверка Python пакетов:")
    required_packages = [
        'telegram',
        'google.cloud.speech_v1',
        'dotenv',
        'pydub',
        'moviepy',
        'aiofiles'
    ]
    
    for package in required_packages:
        try:
            __import__(package.split('.')[0])
            print(f"  ✅ {package}")
        except ImportError:
            errors.append(f"  ❌ Пакет {package} не установлен")
    
    # Вывод результатов
    print("\n" + "=" * 50)
    
    if errors:
        print("\n❌ ОШИБКИ (требуют исправления):")
        for error in errors:
            print(f"  {error}")
    
    if warnings:
        print("\n⚠️  ПРЕДУПРЕЖДЕНИЯ:")
        for warning in warnings:
            print(f"  {warning}")
    
    if not errors:
        print("\n✅ Конфигурация готова! Можно запускать бота.")
        print("\nЗапустите бота командой:")
        print("  python3 bot.py")
        print("\nили")
        print("  ./run.sh")
    else:
        print("\n❌ Исправьте ошибки перед запуском бота.")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(check_config())
