#!/usr/bin/env python3
"""
Генератор Session String для Pyrogram
Используется для создания тестового аккаунта E2E
"""

import os
from pyrogram import Client

def main():
    print("=== Генерация Session String для E2E тестов ===")
    print("ВНИМАНИЕ: Используйте только ТЕСТОВЫЙ аккаунт!\n")
    
    # Можем взять из .env.test если есть
    try:
        from dotenv import load_dotenv
        load_dotenv('.env.test')
        api_id = os.getenv('TEST_API_ID', '')
        api_hash = os.getenv('TEST_API_HASH', '')
        phone = os.getenv('TEST_PHONE', '')
    except:
        api_id = ''
        api_hash = ''
        phone = ''
    
    # Запрашиваем данные
    if not api_id:
        api_id = input("API_ID [29972470]: ") or "29972470"
    if not api_hash:
        api_hash = input("API_HASH [58edbecd1f1924396f81f95a600efba7]: ") or "58edbecd1f1924396f81f95a600efba7"
    if not phone:
        phone = input("PHONE (с кодом страны, например +7...): ")
    
    api_id = int(api_id)
    
    print(f"\nПодключаемся с API_ID={api_id}, телефон {phone}")
    print("Вам придет код подтверждения в Telegram...")
    
    with Client("test_account", api_id=api_id, api_hash=api_hash, phone_number=phone) as app:
        session_string = app.export_session_string()
        print("\n=== SESSION STRING СГЕНЕРИРОВАН ===")
        print("Добавьте в .env.test:")
        print(f"TEST_SESSION_STRING={session_string}")
        
        # Сохраняем в файл для удобства
        with open("session_string.txt", "w") as f:
            f.write(f"TEST_SESSION_STRING={session_string}\n")
        print("\nТакже сохранено в session_string.txt")
        
        # Показываем информацию об аккаунте
        me = app.get_me()
        print(f"\nАвторизован как: {me.first_name} (@{me.username})")

if __name__ == "__main__":
    main()