#!/bin/bash

# NinjaOsvayder Bot - Скрипт запуска для macOS

echo "🥷 NinjaOsvayder Bot - Запуск..."
echo "================================"

# Проверка наличия FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ FFmpeg не установлен!"
    echo "Установите с помощью: brew install ffmpeg"
    exit 1
fi

# Проверка наличия Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не установлен!"
    exit 1
fi

# Проверка наличия виртуального окружения
if [ ! -d "venv" ]; then
    echo "📦 Создание виртуального окружения..."
    python3 -m venv venv
fi

# Активация виртуального окружения
echo "🔧 Активация виртуального окружения..."
source venv/bin/activate

# Установка/обновление зависимостей
echo "📚 Проверка зависимостей..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Проверка наличия .env файла
if [ ! -f ".env" ]; then
    echo "⚠️  Файл .env не найден!"
    echo "Создайте его из .env.example и добавьте токен бота:"
    echo "cp .env.example .env"
    echo "Затем отредактируйте .env и добавьте BOT_TOKEN"
    exit 1
fi

# Проверка наличия service_account.json
if [ ! -f "service_account.json" ]; then
    echo "❌ Файл service_account.json не найден!"
    exit 1
fi

# Создание директории для временных файлов
mkdir -p temp_files

# Запуск бота
echo "================================"
echo "🚀 Запуск бота..."
echo "Для остановки нажмите Ctrl+C"
echo "================================"

python bot.py
