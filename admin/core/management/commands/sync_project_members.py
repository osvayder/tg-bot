from django.core.management.base import BaseCommand
from django.db.models import Q
from core.models import TgGroup, User, Project, ProjectMember, Role

class Command(BaseCommand):
    help = 'Синхронизировать участников групп с проектами'

    def handle(self, *args, **options):
        # Найти всех пользователей которые писали в группах проекта
        for project in Project.objects.filter(status='active'):
            self.stdout.write(f"Синхронизация проекта: {project.name}")
            
            # Все группы проекта
            group_ids = list(TgGroup.objects.filter(
                project=project
            ).values_list('telegram_id', flat=True))
            
            if not group_ids:
                self.stdout.write(f"  Нет групп в проекте")
                continue
                
            # Пользователи которые писали в этих группах
            from django.db import connection
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT DISTINCT user_id, 
                               payload->>'username' as username
                        FROM raw_updates 
                        WHERE chat_id = ANY(%s) 
                        AND user_id IS NOT NULL
                    """, [group_ids])
                    
                    user_data = cursor.fetchall()
            except Exception as e:
                self.stdout.write(f"  Ошибка чтения raw_updates: {e}")
                continue
            
            if not user_data:
                self.stdout.write(f"  Нет данных в raw_updates для групп проекта")
                continue
            
            # Получить или создать роль по умолчанию
            default_role, _ = Role.objects.get_or_create(
                name='Member',
                defaults={'can_assign': False, 'can_close': False}
            )
            
            # Для каждого пользователя из логов
            added = 0
            for user_id, username in user_data:
                # Найти или создать User
                user, user_created = User.objects.get_or_create(
                    telegram_id=user_id,
                    defaults={
                        'username': username or f'user_{user_id}',
                        'status': 'active'
                    }
                )
                
                if user_created:
                    self.stdout.write(f"  Создан пользователь: {user.username}")
                
                # Добавить в ProjectMember если еще нет (с обязательной ролью)
                pm, pm_created = ProjectMember.objects.get_or_create(
                    project=project,
                    user=user,
                    role=default_role,  # Роль обязательна!
                    defaults={}
                )
                
                if pm_created:
                    added += 1
                    self.stdout.write(f"  + {user.username} добавлен в проект")
            
            self.stdout.write(f"  Итого добавлено: {added} участников")
            self.stdout.write("")