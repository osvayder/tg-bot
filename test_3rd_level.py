#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

from django.core.exceptions import ValidationError
from core.models import Department, Project

print("🧪 Тестируем создание 3-го уровня вложенности...")

# Получаем поддепартамент 2-го уровня
dept_animation = Department.objects.get(name="Анимация")
print(f"  Поддепартамент: {dept_animation.name} (уровень {dept_animation.get_level()})")

# Пытаемся создать 3-й уровень
project = Project.objects.get(name="Геленджик")
try:
    dept_3rd = Department(
        project=project,
        name="Cinematics",
        parent=dept_animation  # Родитель уже 2-го уровня!
    )
    dept_3rd.full_clean()  # Вызовет clean() и проверит валидацию
    dept_3rd.save()
    print("❌ ОШИБКА: 3-й уровень создался! Это не должно было произойти!")
except ValidationError as e:
    print(f"✅ Правильно! Получена ошибка валидации: {e.message_dict.get('parent', e)}")
    print("   3-й уровень вложенности успешно заблокирован!")

print("\n📊 Итоговая структура:")
for dept in Department.objects.all().order_by('get_level', 'name'):
    indent = "  " * (dept.get_level() - 1)
    parent_name = f" (в {dept.parent.name})" if dept.parent else ""
    print(f"  {indent}- {dept.name} (уровень {dept.get_level()}){parent_name}")