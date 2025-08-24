#!/usr/bin/env python3
"""
Быстрая генерация Session String с предзаполненными данными
"""

import asyncio
from pyrogram import Client

async def main():
    print("=== Генерация Session String для E2E тестов ===")
    print("Используем данные из .env.test")
    
    api_id = 29972470
    api_hash = "58edbecd1f1924396f81f95a600efba7"
    phone = "+995593564642"
    
    print(f"\nAPI_ID: {api_id}")
    print(f"API_HASH: {api_hash[:10]}...")
    print(f"Phone: {phone}")
    
    print("\n⚠️  ВАЖНО: Вам придет код подтверждения в Telegram")
    print("Введите его когда появится запрос\n")
    
    client = Client(
        "test_session",
        api_id=api_id,
        api_hash=api_hash,
        phone_number=phone
    )
    
    await client.start()
    
    session_string = await client.export_session_string()
    
    print("\n" + "="*60)
    print("✅ SESSION STRING УСПЕШНО СГЕНЕРИРОВАН!")
    print("="*60)
    print("\nДобавьте эту строку в .env.test:")
    print(f"\nTEST_SESSION_STRING={session_string}\n")
    print("="*60)
    
    # Сохраняем в файл
    with open("session_string.txt", "w") as f:
        f.write(f"TEST_SESSION_STRING={session_string}\n")
    print("\n📝 Также сохранено в файл: session_string.txt")
    
    # Показываем инфо об аккаунте
    me = await client.get_me()
    print(f"\n✅ Авторизован как: {me.first_name} (ID: {me.id})")
    if me.username:
        print(f"   Username: @{me.username}")
    
    await client.stop()

if __name__ == "__main__":
    print("Запуск...")
    asyncio.run(main())