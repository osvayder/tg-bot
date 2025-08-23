#!/bin/bash

echo "🚀 Быстрый запуск Ninja Osvayder Bot"
echo "====================================="

# Установка зависимостей если нужно
if [ ! -d "venv" ]; then
    echo "📦 Первый запуск - установка зависимостей..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Запуск бота
echo "🤖 Запуск бота..."
python3 bot.py
