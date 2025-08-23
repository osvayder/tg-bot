#!/usr/bin/env python3
"""
Скрипт для настройки прав доступа к файлам
"""

import os
import stat
from pathlib import Path

# Список файлов, которым нужны права на выполнение
executable_files = [
    'run.sh',
    'start.sh',
    'bot.py',
    'check_config.py',
    'setup_permissions.py'
]

print("🔧 Настройка прав доступа...")

for filename in executable_files:
    filepath = Path(filename)
    if filepath.exists():
        # Добавляем права на выполнение
        st = os.stat(filepath)
        os.chmod(filepath, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print(f"✅ {filename} - права на выполнение установлены")
    else:
        print(f"⚠️  {filename} - файл не найден")

print("\n✅ Готово! Теперь можно запускать бота командой:")
print("  ./start.sh")
print("\nили для полной проверки:")
print("  ./run.sh")
