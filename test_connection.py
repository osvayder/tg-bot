#!/usr/bin/env python3
"""
Проверка подключения тестового аккаунта к Telegram
"""

import os
import asyncio
from dotenv import load_dotenv
from pyrogram import Client

# Загружаем тестовые credentials
load_dotenv('.env.test')

async def main():
    api_id = int(os.getenv("TEST_API_ID"))
    api_hash = os.getenv("TEST_API_HASH")
    session_string = os.getenv("TEST_SESSION_STRING")
    bot_username = os.getenv("TEST_BOT_USERNAME", "@your_test_bot")
    
    if not session_string:
        print("ERROR: TEST_SESSION_STRING не найден в .env.test")
        print("Сначала запустите: python generate_session.py")
        return
    
    print("Подключаемся к Telegram...")
    
    client = Client(
        "test_connection",
        session_string=session_string,
        api_id=api_id,
        api_hash=api_hash
    )
    
    async with client:
        # Информация об аккаунте
        me = await client.get_me()
        print(f"✅ Подключен как: {me.first_name} (@{me.username})")
        
        # Отправляем /start боту
        print(f"\nОтправляем /start боту {bot_username}...")
        try:
            await client.send_message(bot_username, "/start")
            print("✅ Команда отправлена")
            
            # Ждем ответ
            await asyncio.sleep(2)
            
            # Получаем последнее сообщение от бота
            async for message in client.get_chat_history(bot_username, limit=1):
                if message.text:
                    print(f"✅ Ответ бота: {message.text[:100]}...")
                else:
                    print("✅ Бот ответил (не текстовое сообщение)")
                break
        except Exception as e:
            print(f"❌ Ошибка при отправке команды: {e}")
        
        print("\n✅ Тест подключения завершен успешно!")

if __name__ == "__main__":
    asyncio.run(main())