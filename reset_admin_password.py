#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

from django.contrib.auth.models import User

# Сбросим пароль для admin
try:
    admin = User.objects.get(username='admin')
    admin.set_password('admin')
    admin.save()
    print("✅ Пароль для пользователя 'admin' сброшен на 'admin'")
except User.DoesNotExist:
    # Создаем нового админа
    User.objects.create_superuser('admin', 'admin@example.com', 'admin')
    print("✅ Создан новый суперпользователь 'admin' с паролем 'admin'")

print("\n🔑 Данные для входа:")
print("   URL: http://localhost:8000/admin/")
print("   Логин: admin")
print("   Пароль: admin")