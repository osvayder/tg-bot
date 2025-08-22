#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

from django.contrib.auth.models import User
from core.models import Project, Role, Department

# Создаем суперпользователя
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin')
    print("✅ Суперпользователь создан (admin/admin)")

# Создаем проект
project = Project.objects.create(name="Геленджик", status="active")
print(f"✅ Проект '{project.name}' создан")

# Создаем роли
role_ceo = Role.objects.create(name="CEO", can_assign=True, can_close=True)
role_animator = Role.objects.create(name="Аниматор", can_assign=False, can_close=False)
role_producer = Role.objects.create(name="Продюсер", can_assign=True, can_close=True)
print("✅ Роли созданы: CEO, Аниматор, Продюсер")

# Создаем корневые департаменты (уровень 1)
dept_prod = Department.objects.create(
    project=project, 
    name="Производство", 
    lead_role=role_producer
)
dept_mgmt = Department.objects.create(
    project=project, 
    name="Менеджмент", 
    lead_role=role_ceo
)
print("✅ Корневые департаменты созданы: Производство, Менеджмент")

# Создаем поддепартаменты (уровень 2 - МАКСИМУМ!)
dept_anim = Department.objects.create(
    project=project, 
    name="Анимация", 
    parent=dept_prod,
    lead_role=role_animator
)
dept_render = Department.objects.create(
    project=project, 
    name="Рендер", 
    parent=dept_prod,
    lead_role=role_animator
)
print("✅ Поддепартаменты созданы: Анимация, Рендер")

# Проверим уровни
print("\n📊 Проверка уровней вложенности:")
for dept in Department.objects.all():
    print(f"  - {dept.name}: уровень {dept.get_level()}")

print("\n✅ Структура успешно создана!")
print("🔑 Админка: http://localhost:8000/admin/ (admin/admin)")