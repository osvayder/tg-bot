#!/usr/bin/env python3
"""
Интерактивный человеко-подобный бот для ручного тестирования
"""

import os
import asyncio
from dotenv import load_dotenv
from pyrogram import Client
from datetime import datetime

# Загружаем тестовые credentials
load_dotenv(".env.test")

API_ID = int(os.getenv("TEST_API_ID"))
API_HASH = os.getenv("TEST_API_HASH")
SESSION = os.getenv("TEST_SESSION_STRING")
BOT = os.getenv("TEST_BOT_USERNAME", "@your_test_bot")
GROUP_ID = int(os.getenv("TEST_GROUP_ID", "0"))

async def main():
    if not SESSION:
        print("❌ TEST_SESSION_STRING не найден!")
        print("Запустите: python generate_session.py")
        return
    
    print("🚀 Подключаемся к Telegram...")
    
    async with Client("human", session_string=SESSION, api_id=API_ID, api_hash=API_HASH) as app:
        me = await app.get_me()
        print(f"✅ Авторизован как: {me.first_name} (@{me.username})")
        print(f"🤖 Тестируем бота: {BOT}")
        
        print("\n" + "="*50)
        print("КОМАНДЫ:")
        print("1) /start - начать диалог с ботом")
        print("2) /ping - проверка связи")
        print("3) /whoami - информация о пользователе")
        print("4) /newtask - создать задачу")
        print("5) /help - помощь")
        print("6) Отправить в группу")
        print("7) Произвольное сообщение боту")
        print("0) Выход")
        print("="*50 + "\n")
        
        while True:
            try:
                cmd = input("Выберите команду > ").strip()
                
                if cmd == "0":
                    print("👋 Выход...")
                    break
                    
                elif cmd == "1":
                    await app.send_message(BOT, "/start")
                    print("📤 Отправлено: /start")
                    
                elif cmd == "2":
                    await app.send_message(BOT, "/ping")
                    print("📤 Отправлено: /ping")
                    
                elif cmd == "3":
                    await app.send_message(BOT, "/whoami")
                    print("📤 Отправлено: /whoami")
                    
                elif cmd == "4":
                    title = input("Заголовок задачи: ")
                    desc = input("Описание (опционально): ")
                    msg = f"/newtask {title}"
                    if desc:
                        msg += f"\n{desc}"
                    await app.send_message(BOT, msg)
                    print(f"📤 Отправлено: создание задачи '{title}'")
                    
                elif cmd == "5":
                    await app.send_message(BOT, "/help")
                    print("📤 Отправлено: /help")
                    
                elif cmd == "6":
                    if GROUP_ID:
                        text = input("Текст для группы: ")
                        await app.send_message(GROUP_ID, text)
                        print(f"📤 Отправлено в группу: {text}")
                    else:
                        print("❌ TEST_GROUP_ID не настроен")
                        
                elif cmd == "7":
                    text = input("Текст сообщения: ")
                    await app.send_message(BOT, text)
                    print(f"📤 Отправлено: {text}")
                    
                else:
                    print("❓ Неизвестная команда")
                    continue
                
                # Ждем и показываем ответ бота
                await asyncio.sleep(2)
                
                print("\n📥 Последние сообщения от бота:")
                async for msg in app.get_chat_history(BOT, limit=3):
                    timestamp = msg.date.strftime("%H:%M:%S")
                    if msg.text:
                        # Обрезаем длинные сообщения
                        text = msg.text[:200]
                        if len(msg.text) > 200:
                            text += "..."
                        print(f"  [{timestamp}] {text}")
                    elif msg.photo:
                        print(f"  [{timestamp}] [Фото]")
                    elif msg.document:
                        print(f"  [{timestamp}] [Документ]")
                    else:
                        print(f"  [{timestamp}] [Другой тип сообщения]")
                print()
                
            except KeyboardInterrupt:
                print("\n👋 Прервано пользователем")
                break
            except Exception as e:
                print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())