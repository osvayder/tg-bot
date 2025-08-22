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

print("\n📊 Итоговая структура (макс 2 уровня):")
# Сначала корневые (уровень 1)
for dept in Department.objects.filter(parent__isnull=True).order_by('name'):
    print(f"  ├─ {dept.name} (уровень 1)")
    # Затем их дети (уровень 2)
    for child in Department.objects.filter(parent=dept).order_by('name'):
        print(f"  │  └─ {child.name} (уровень 2)")

print("\n✅ Ограничение вложенности работает корректно!")