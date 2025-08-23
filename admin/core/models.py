from django.db import models, transaction


class Project(models.Model):
    STATUS_CHOICES = [
        ("active", "Активен"),
        ("inactive", "Неактивен"),
    ]
    name = models.CharField(max_length=128, verbose_name="Название")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active", verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Проект"
        verbose_name_plural = "Проекты"
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Role(models.Model):
    name = models.CharField(max_length=64, unique=True, verbose_name="Название")
    can_assign = models.BooleanField(default=False, verbose_name="Может назначать")
    can_close = models.BooleanField(default=False, verbose_name="Может закрывать")

    class Meta:
        verbose_name = "Роль"
        verbose_name_plural = "Роли"
        ordering = ['name']

    def __str__(self):
        return self.name


class GroupProfile(models.Model):
    name = models.CharField(max_length=64, unique=True, verbose_name="Название профиля")
    color = models.CharField(max_length=32, blank=True, verbose_name="Цвет")
    emoji = models.CharField(max_length=8, blank=True, default="", verbose_name="Эмодзи")
    is_template = models.BooleanField(default=False, verbose_name="Это шаблон")
    shadow_mode = models.BooleanField(
        default=True,
        verbose_name="Режим тени",
        help_text="Бот читает сообщения, но не отвечает"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")

    class Meta:
        verbose_name = "Профиль группы"
        verbose_name_plural = "Профили групп"
        ordering = ['name']

    def __str__(self):
        return f"{self.emoji} {self.name}".strip()


class TgGroup(models.Model):
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID группы")
    title = models.CharField(max_length=256, verbose_name="Название группы")
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        verbose_name="Проект"
    )
    profile = models.ForeignKey(
        GroupProfile, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Профиль группы"
    )
    # S1: маршрутизация клиент→продюсер
    forward_to = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='forward_sources',
        verbose_name="Пересылать в группу"
    )
    forward_topic_id = models.BigIntegerField(
        null=True, 
        blank=True,
        verbose_name="ID топика для пересылки"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Добавлена")

    class Meta:
        verbose_name = "Telegram группа"
        verbose_name_plural = "Telegram группы"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.telegram_id})"


class User(models.Model):
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    username = models.CharField(max_length=150, blank=True, db_index=True, verbose_name="Имя пользователя")
    first_name = models.CharField(max_length=150, blank=True, verbose_name="Имя")
    last_name = models.CharField(max_length=150, blank=True, verbose_name="Фамилия")
    status = models.CharField(
        max_length=16, 
        default="active",
        choices=[
            ('active', 'Активен'),
            ('inactive', 'Неактивен'),
        ],
        verbose_name="Статус"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата регистрации")

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ['-created_at']

    def _full_name(self) -> str:
        return " ".join(p for p in [self.first_name, self.last_name] if p).strip()

    def __str__(self):
        full = self._full_name()
        if self.username and full:
            return f"{self.username} ({full})"
        if self.username:
            return self.username
        if full:
            return f"({full})"
        return f"id:{self.telegram_id}"


class Department(models.Model):
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        null=True,
        blank=True,
        related_name="departments",
        verbose_name="Проект"
    )
    name = models.CharField(max_length=128, verbose_name="Название")
    parent = models.ForeignKey(
        "self", 
        null=True, 
        blank=True, 
        on_delete=models.CASCADE, 
        related_name="children",
        verbose_name="Родительский департамент"
    )
    lead_role = models.ForeignKey(
        Role, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        verbose_name="Ведущая роль"
    )

    class Meta:
        verbose_name = "Департамент"
        verbose_name_plural = "Департаменты"
        ordering = ['name']
        indexes = [
            models.Index(fields=["project", "parent"]),
        ]

    def get_level(self) -> int:
        """Возвращает уровень вложенности департамента (1 для корневого)"""
        level, p = 1, self.parent
        while p:
            level += 1
            p = p.parent
        return level

    def clean(self):
        """Валидация перед сохранением"""
        from django.core.exceptions import ValidationError
        
        # Проверка максимальной вложенности (2 уровня)
        if self.parent and self.parent.parent_id:
            raise ValidationError({'parent': 'Максимум 2 уровня: Родитель → Поддепартамент.'})
        
        # Для поддепартамента проект обязателен (берется от родителя)
        if self.parent_id:
            if self.parent and self.parent.project_id:
                # Автоматически устанавливаем проект от родителя
                self.project_id = self.parent.project_id
            else:
                raise ValidationError("У родительского департамента не задан проект")
        else:
            # Для корневого департамента проект обязателен
            if not self.project_id:
                raise ValidationError("Для корневого департамента необходимо выбрать проект")
        
        # ЗАПРЕТ менять родителя у существующего узла
        if self.pk:
            prev_parent_id = type(self).objects.only("parent_id").get(pk=self.pk).parent_id
            if self.parent_id != prev_parent_id:
                raise ValidationError({
                    "__all__": "Менять родителя нельзя. Создайте новый поддепартамент и перенесите участников."
                })

    def save(self, *args, **kwargs):
        """Автоматическое наследование проекта от родителя"""
        # Если есть родитель и нет проекта - наследуем
        if self.parent_id and not self.project_id:
            if self.parent and self.parent.project_id:
                self.project_id = self.parent.project_id
            else:
                # Если у родителя тоже нет проекта - ошибка
                from django.core.exceptions import ValidationError
                raise ValidationError("Родительский департамент должен иметь проект")
        
        # Если есть родитель - проект должен совпадать
        if self.parent_id and self.project_id and self.parent:
            if self.project_id != self.parent.project_id:
                from django.core.exceptions import ValidationError
                raise ValidationError("Проект поддепартамента должен совпадать с проектом родителя")
        
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProjectMember(models.Model):
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE,
        verbose_name="Пользователь"
    )
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE,
        verbose_name="Проект"
    )
    role = models.ForeignKey(
        Role, 
        on_delete=models.CASCADE,
        verbose_name="Роль"
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Департамент"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Назначен")

    class Meta:
        verbose_name = "Участник проекта"
        verbose_name_plural = "Участники проектов"
        # Убираем старое unique_together = ('project','user')
        # Новые ограничения уникальности
        constraints = [
            # 1) Проектный уровень (без департамента): одна запись на (user, project, role)
            models.UniqueConstraint(
                fields=['project', 'user', 'role'],
                condition=models.Q(department__isnull=True),
                name='pm_unique_role_project_level',
            ),
            # 2) Уровень поддепартамента: одна запись на (user, project, role, department)
            models.UniqueConstraint(
                fields=['project', 'user', 'role', 'department'],
                condition=models.Q(department__isnull=False),
                name='pm_unique_role_department_level',
            ),
        ]
        ordering = ['created_at']
    
    def clean(self):
        from django.core.exceptions import ValidationError
        base = ProjectMember.objects.exclude(pk=self.pk).filter(
            project=self.project, user=self.user, role=self.role
        )
        
        # Правило P1: блокируем создание "общей" записи, если уже есть разрез по департаментам
        if self.department_id is None and base.filter(department__isnull=False).exists():
            departments = base.filter(department__isnull=False).select_related('department')
            dept_names = ', '.join(pm.department.name for pm in departments[:3])
            if departments.count() > 3:
                dept_names += '...'
            raise ValidationError(
                f"Роль '{self.role}' уже назначена в департаментах: {dept_names}. "
                "Выберите конкретный департамент или удалите существующие назначения."
            )
        
        # Проверка уникальности на том же уровне (department или project)
        if self.department_id:
            if base.filter(department=self.department).exists():
                raise ValidationError("Эта роль уже назначена пользователю в этом поддепартаменте.")
        else:
            if base.filter(department__isnull=True).exists():
                raise ValidationError("Эта роль уже назначена пользователю на уровне проекта.")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
            # Если сохраняем запись по поддепартаменту — удаляем «общую», чтобы не было дублей
            if self.department_id is not None:
                ProjectMember.objects.filter(
                    project=self.project, 
                    user=self.user, 
                    role=self.role, 
                    department__isnull=True
                ).delete()

    def __str__(self):
        role_str = f" ({self.role.name})" if self.role else ""
        dept_str = f" in {self.department.name}" if self.department else ""
        return f"{self.user}{role_str} в {self.project}{dept_str}"


class Task(models.Model):
    STATUS_CHOICES = [
        ("TODO", "К выполнению"),
        ("IN_PROGRESS", "В работе"),
        ("ON_REVIEW", "На проверке"),
        ("DONE", "Выполнено"),
        ("ARCHIVED", "В архиве"),
    ]
    
    title = models.CharField(max_length=256, verbose_name="Заголовок")
    description = models.TextField(blank=True, verbose_name="Описание")
    responsible_user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        verbose_name="Ответственный",
        related_name='tasks'
    )
    responsible_username = models.CharField(
        max_length=64, 
        blank=True,
        verbose_name="Username ответственного"
    )
    author_user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='authored_tasks',
        verbose_name="Автор задачи"
    )
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        verbose_name="Проект"
    )
    deadline = models.DateField(null=True, blank=True, verbose_name="Дедлайн")
    # S0: следы источника (чат/сообщение/топик)
    source_chat_id = models.BigIntegerField(
        null=True, 
        blank=True,
        verbose_name="ID чата-источника"
    )
    source_message_id = models.BigIntegerField(
        null=True, 
        blank=True,
        verbose_name="ID сообщения"
    )
    source_topic_id = models.BigIntegerField(
        null=True, 
        blank=True,
        verbose_name="ID топика"
    )
    status = models.CharField(
        max_length=16, 
        choices=STATUS_CHOICES, 
        default="TODO",
        verbose_name="Статус"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'deadline']),
            models.Index(fields=['responsible_username']),
        ]

    def __str__(self):
        return f"#{self.id}: {self.title[:40]}"
    
    @property
    def is_overdue(self):
        if not self.deadline:
            return False
        from django.utils import timezone
        return self.deadline < timezone.now().date() and self.status != "DONE"
    
    @property
    def is_warning(self):
        if not self.deadline:
            return False
        from django.utils import timezone
        from datetime import timedelta
        warning_date = timezone.now().date() + timedelta(days=1)
        return self.deadline <= warning_date and self.status != "DONE" and not self.is_overdue


class ForumTopic(models.Model):
    """Автоматически создаваемая запись о топике в группе"""
    group = models.ForeignKey(
        'TgGroup', 
        on_delete=models.CASCADE, 
        related_name='topics',
        verbose_name="Группа"
    )
    topic_id = models.BigIntegerField(verbose_name="ID топика")
    title = models.CharField(max_length=256, blank=True, verbose_name="Название")
    first_seen = models.DateTimeField(auto_now_add=True, verbose_name="Впервые замечен")
    last_seen = models.DateTimeField(auto_now=True, verbose_name="Последнее сообщение")
    message_count = models.IntegerField(default=0, verbose_name="Сообщений")

    class Meta:
        verbose_name = "Топик"
        verbose_name_plural = "Топики"
        constraints = [
            models.UniqueConstraint(fields=['group', 'topic_id'], name='uniq_forum_topic')
        ]
        ordering = ['group', 'title', 'topic_id']

    def __str__(self):
        base = self.title or f"Topic {self.topic_id}"
        return f"{base} @ {self.group.title}"


class TopicRole(models.Model):
    """
    Привязка топика (message_thread_id) к департаменту/роли/пользователю внутри конкретной группы.
    При создании задач без явного @mention — берём отсюда ответственного.
    Приоритет: user > role > department.lead_role.
    """
    group = models.ForeignKey(
        'TgGroup', 
        on_delete=models.CASCADE, 
        related_name='topic_roles',
        verbose_name="Группа"
    )
    topic_id = models.BigIntegerField(verbose_name="ID топика")
    department = models.ForeignKey(
        'Department', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Департамент"
    )
    role = models.ForeignKey(
        'Role', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Роль"
    )
    user = models.ForeignKey(
        'User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Пользователь"
    )

    class Meta:
        verbose_name = "Привязка топика"
        verbose_name_plural = "Привязки топиков"
        constraints = [
            models.UniqueConstraint(fields=['group', 'topic_id'], name='uniq_group_topic')
        ]

    def __str__(self):
        return f"{self.group.title}#{self.topic_id}"


class TopicBinding(models.Model):
    """Связи топика: кто к нему относится и в каком порядке эскалации"""
    topic = models.ForeignKey('ForumTopic', on_delete=models.CASCADE, related_name='bindings', verbose_name="Топик")
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Департамент")
    role = models.ForeignKey('Role', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Роль")
    user = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Пользователь")
    priority = models.PositiveSmallIntegerField(default=1, verbose_name="Приоритет (эскалация)")
    is_primary = models.BooleanField(default=False, verbose_name="Основной")

    class Meta:
        ordering = ['priority', 'id']
        verbose_name = "Связка топика"
        verbose_name_plural = "Связки топика"
        constraints = [
            models.UniqueConstraint(fields=['topic', 'priority'], name='uniq_topic_priority')
        ]

    def __str__(self):
        who = self.user or self.role or (self.department and self.department.name) or "—"
        return f"[{self.priority}] {who}"


class DepartmentMember(models.Model):
    """Состав департамента с ролями и порядком"""
    department = models.ForeignKey('Department', on_delete=models.CASCADE, related_name='members', verbose_name="Департамент")
    user = models.ForeignKey('User', on_delete=models.CASCADE, verbose_name="Пользователь")
    role = models.ForeignKey('Role', on_delete=models.CASCADE, verbose_name="Роль")  # делаем обязательной
    order_index = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    is_lead = models.BooleanField(default=False, verbose_name="Ответственный за направление")
    is_tech = models.BooleanField(default=False, verbose_name="Технический ответственный")

    class Meta:
        ordering = ['order_index', 'user__username']
        constraints = [
            models.UniqueConstraint(fields=["department", "user"], name="uniq_department_user")
        ]
        indexes = [
            models.Index(fields=["department"]),
        ]
        verbose_name = "Состав департамента"
        verbose_name_plural = "Состав департамента"

    def __str__(self):
        return f"{self.user} — {self.role or 'без роли'}"


class RawUpdate(models.Model):
    """Логирование сырых обновлений от Telegram (таблица создается ботом)"""
    chat_id = models.BigIntegerField()
    message_id = models.BigIntegerField(null=True, blank=True)
    user_id = models.BigIntegerField(null=True, blank=True)
    username = models.CharField(max_length=255, null=True, blank=True)
    text = models.TextField(blank=True, default="")
    topic_id = models.BigIntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False  # Django не управляет этой таблицей
        db_table = 'raw_updates'
        ordering = ['-created_at']
        verbose_name = "Raw Update"
        verbose_name_plural = "Raw Updates"

    def __str__(self):
        return f"Update {self.chat_id} at {self.created_at}"