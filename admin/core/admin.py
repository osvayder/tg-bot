from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.contrib.admin import display
from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db import models
from django.forms.models import BaseInlineFormSet
from datetime import timedelta
import os
import requests
from .models import Project, GroupProfile, TgGroup, User, Role, Department, ProjectMember, Task, TopicRole, ForumTopic, TopicBinding, DepartmentMember

BOT_TOKEN = os.getenv("BOT_TOKEN")


# ===================== Формы для проекта =====================
class ProjectAttachForm(forms.ModelForm):
    # Группы: привязать существующие
    attach_groups = forms.ModelMultipleChoiceField(
        queryset=TgGroup.objects.none(), required=False,
        widget=FilteredSelectMultiple("Группы", is_stacked=False),
        label="Привязать существующие группы"
    )
    detach_missing_groups = forms.BooleanField(
        required=False, initial=False,
        label="Снять привязку с групп, не выбранных выше",
        help_text="Внимание: группы потеряют связь с проектом"
    )

    # Департаменты: привязать существующие/шаблонные
    attach_departments = forms.ModelMultipleChoiceField(
        queryset=Department.objects.none(), required=False,
        widget=FilteredSelectMultiple("Департаменты", is_stacked=False),
        label="Привязать существующие департаменты/шаблоны"
    )
    detach_missing_departments = forms.BooleanField(
        required=False, initial=False,
        label="Снять привязку с департаментов, не выбранных выше",
        help_text="Внимание: департаменты потеряют связь с проектом"
    )
    dept_attach_mode = forms.ChoiceField(
        choices=[('copy', 'Копировать шаблоны в проект'), ('move', 'Переназначить/переместить')],
        initial='copy', required=False, label="Режим привязки департаментов",
        help_text="Копирование сохраняет шаблоны для других проектов"
    )

    class Meta:
        model = Project
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        proj = self.instance if self.instance and self.instance.pk else None

        # Можно выбрать: уже привязанные к проекту + свободные (без проекта)
        self.fields["attach_groups"].queryset = TgGroup.objects.filter(
            models.Q(project__isnull=True) | models.Q(project=proj)
        ).order_by("title")
        self.fields["attach_groups"].initial = TgGroup.objects.filter(project=proj)

        self.fields["attach_departments"].queryset = Department.objects.filter(
            models.Q(project__isnull=True) | models.Q(project=proj)
        ).order_by("name")
        self.fields["attach_departments"].initial = Department.objects.filter(project=proj)


# ===================== Инлайны для проекта =====================
class TgGroupInline(admin.TabularInline):
    model = TgGroup
    extra = 0
    show_change_link = True
    fields = ("title", "telegram_id", "profile", "topics_total")
    readonly_fields = ("topics_total",)

    def topics_total(self, obj):
        return ForumTopic.objects.filter(group=obj).count()
    topics_total.short_description = "Топики"

class DepartmentInline(admin.TabularInline):
    model = Department
    extra = 0
    show_change_link = True
    fields = ("name", "parent", "lead_role")
    autocomplete_fields = ("parent", "lead_role")

class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 0
    autocomplete_fields = ("user", "role", "department")
    
    def get_queryset(self, request):
        from django.db.models import Q, Exists, OuterRef
        qs = super().get_queryset(request)
        # Проверяем, есть ли детальные записи для той же (user, project, role)
        sub = ProjectMember.objects.filter(
            project_id=OuterRef("project_id"),
            user_id=OuterRef("user_id"),
            role_id=OuterRef("role_id"),
            department__isnull=False,
        )
        qs = qs.annotate(has_children=Exists(sub))
        # Если есть детальные записи — общий уровень не показываем
        return qs.filter(~Q(department__isnull=True) | Q(has_children=False))


# ===================== Функции-хелперы =====================
def clone_department_tree(dep: Department, project: Project, parent: Department | None = None) -> Department:
    """Копирование департамента-шаблона в проект (с поддеревом и составом)."""
    new_dep = Department.objects.create(
        project=project, name=dep.name, parent=parent, lead_role=dep.lead_role
    )
    # состав
    for m in dep.members.all().order_by("order_index", "id"):
        DepartmentMember.objects.create(
            department=new_dep, user=m.user, role=m.role,
            order_index=m.order_index, is_lead=m.is_lead, is_tech=m.is_tech
        )
    # дети
    for ch in dep.children.all().order_by("id"):
        clone_department_tree(ch, project, new_dep)
    return new_dep


# ===================== Админка проекта =====================
@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    form = ProjectAttachForm
    list_display = ("name", "status", "groups_count", "members_count", "departments_count", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name",)
    inlines = [TgGroupInline, DepartmentInline, ProjectMemberInline]

    def groups_count(self, obj):
        return TgGroup.objects.filter(project=obj).count()
    groups_count.short_description = "Группы"
    
    def members_count(self, obj):
        return ProjectMember.objects.filter(project=obj).count()
    members_count.short_description = "Участники"
    
    def departments_count(self, obj):
        return Department.objects.filter(project=obj).count()
    departments_count.short_description = "Департаменты"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not form.is_valid():
            return

        # ГРУППЫ: привязать выбранные, отвязать — только если флажок отмечен
        groups = form.cleaned_data.get("attach_groups")
        if groups is not None:
            group_ids = list(groups.values_list("id", flat=True))
            TgGroup.objects.filter(id__in=group_ids).update(project=obj)
            if form.cleaned_data.get("detach_missing_groups"):
                TgGroup.objects.filter(project=obj).exclude(id__in=group_ids).update(project=None)

        # ДЕПАРТАМЕНТЫ: копировать шаблоны (по умолчанию) ИЛИ перемещать
        deps = form.cleaned_data.get("attach_departments")
        if deps is not None:
            mode = form.cleaned_data.get("dept_attach_mode") or "copy"
            dep_ids = list(deps.values_list("id", flat=True))

            if mode == "copy":
                for d in deps:
                    # шаблон = dep.project is None → копируем в проект (не трогаем исходник)
                    if d.project_id != obj.id:
                        clone_department_tree(d, obj, None)
            else:
                Department.objects.filter(id__in=dep_ids).update(project=obj)
                if form.cleaned_data.get("detach_missing_departments"):
                    Department.objects.filter(project=obj).exclude(id__in=dep_ids).update(project=None)


# ===================== Админка GroupProfile =====================
@admin.register(GroupProfile)
class GroupProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "emoji", "color", "shadow_mode", "is_template", "created_at")
    list_filter = ("shadow_mode", "is_template")
    search_fields = ("name", "emoji")


# ===================== Инлайны для топиков =====================
class TopicBindingInline(admin.TabularInline):
    model = TopicBinding
    extra = 1
    fields = ("priority", "department", "role", "user", "is_primary")
    autocomplete_fields = ("department", "role", "user")


class ForumTopicInline(admin.TabularInline):
    model = ForumTopic
    extra = 0
    show_change_link = True
    fields = ("topic_id", "title", "message_count", "last_seen")
    readonly_fields = ("topic_id", "message_count", "last_seen")


# ===================== Админка TgGroup =====================
from django.db import transaction, connection

@admin.register(TgGroup)
class TgGroupAdmin(admin.ModelAdmin):
    list_display = (
        "title", "telegram_id", "project", "profile_badge",
        "members_count", "departments_count", "topics_count", "created_at"
    )
    fields = (
        "title", "telegram_id", "project", "profile",
        "members_link", "departments_link", "topics_count", "created_at"
    )
    readonly_fields = ("members_link", "departments_link", "topics_count", "created_at")
    autocomplete_fields = ("project", "profile")
    list_filter = ("project", "profile", "created_at")
    search_fields = ("title", "telegram_id")
    inlines = [ForumTopicInline]
    actions = ["sync_members_from_logs"]
    
    def sync_members_from_logs(self, request, queryset):
        """Ручная синхронизация участников из логов"""
        total_synced = 0
        for group in queryset:
            if group.project_id and group.telegram_id:
                default_role, _ = Role.objects.get_or_create(
                    name="Member",
                    defaults={'can_assign': False, 'can_close': False}
                )
                count = self._sync_project_members_from_logs(
                    project_id=group.project_id,
                    chat_ids=[group.telegram_id],
                    default_role=default_role
                )
                total_synced += count
        self.message_user(request, f"Синхронизировано {total_synced} участников")
    sync_members_from_logs.short_description = "Синхронизировать участников из логов"

    def profile_badge(self, obj):
        return str(obj.profile) if obj.profile else "—"
    profile_badge.short_description = "Профиль"

    def members_count(self, obj):
        if not obj.project_id: return 0
        return ProjectMember.objects.filter(project_id=obj.project_id).count()
    members_count.short_description = "Участники"

    def departments_count(self, obj):
        if not obj.project_id: return 0
        return Department.objects.filter(project_id=obj.project_id).count()
    departments_count.short_description = "Департаменты"

    def topics_count(self, obj):
        return ForumTopic.objects.filter(group=obj).count()
    topics_count.short_description = "Топики"

    def members_link(self, obj):
        if not obj.project_id: return "—"
        url = reverse("admin:core_projectmember_changelist") + f"?project__id__exact={obj.project_id}"
        return format_html('<a href="{}">Открыть ({} шт.)</a>', url, self.members_count(obj))
    members_link.short_description = "Участники проекта"

    def departments_link(self, obj):
        if not obj.project_id: return "—"
        url = reverse("admin:core_department_changelist") + f"?project__id__exact={obj.project_id}"
        return format_html('<a href="{}">Открыть ({} шт.)</a>', url, self.departments_count(obj))
    departments_link.short_description = "Департаменты проекта"
    
    def _sync_project_members_from_logs(self, project_id: int, chat_ids: list[int], default_role: Role | None):
        if not chat_ids:
            return 0
        # 1) собрать tg user_id и username из логов
        try:
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT ru.user_id, ru.username
                    FROM raw_updates ru
                    WHERE ru.chat_id = ANY(%s)
                    AND ru.user_id IS NOT NULL
                """, (chat_ids,))
                user_data = cur.fetchall()
        except Exception:
            # Если таблица raw_updates не существует - пропускаем
            return 0

        if not user_data:
            return 0

        # 2) создать или найти пользователей
        created = 0
        with transaction.atomic():
            for tg_user_id, username in user_data:
                # Найти или создать User
                user, user_created = User.objects.get_or_create(
                    telegram_id=tg_user_id,
                    defaults={
                        'username': username or f'user_{tg_user_id}',
                        'status': 'active'
                    }
                )
                
                # Добавить в ProjectMember (роль обязательна!)
                if not default_role:
                    # Если роль не передана - создаем дефолтную
                    default_role, _ = Role.objects.get_or_create(
                        name='Member',
                        defaults={'can_assign': False, 'can_close': False}
                    )
                
                pm, was_created = ProjectMember.objects.get_or_create(
                    project_id=project_id,
                    user_id=user.id,
                    role=default_role,
                    defaults={}
                )
                    
                if was_created:
                    created += 1
        return created

    def save_model(self, request, obj: TgGroup, form, change):
        """Сохранение группы без обращения к несуществующим полям"""
        # Если есть FK на проект — обычное сохранение
        super().save_model(request, obj, form, change)

        # После сохранения: если у группы есть проект — подтянуть ProjectMember из логов
        if obj.project_id and obj.telegram_id:
            # Базовая роль по умолчанию - создаем если нет
            default_role, _ = Role.objects.get_or_create(
                name="Member",
                defaults={'can_assign': False, 'can_close': False}
            )
            created_count = self._sync_project_members_from_logs(
                project_id=obj.project_id,
                chat_ids=[obj.telegram_id],
                default_role=default_role
            )
            if created_count > 0:
                from django.contrib import messages
                messages.success(request, f"Синхронизировано {created_count} участников из группы")


# ===================== Инлайны для пользователей =====================
# Форма инлайна с каскадным выбором департаментов
class DepartmentMemberForm(forms.ModelForm):
    parent_department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        required=False,
        label="Департамент"
    )

    class Meta:
        model = DepartmentMember
        fields = ("parent_department", "department", "role")

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)  # пробрасываем из инлайна
        super().__init__(*args, **kwargs)
        # показываем только корневые департаменты проектов, где состоит пользователь
        if user:
            pids = list(ProjectMember.objects.filter(user=user)
                        .values_list("project_id", flat=True))
            self.fields["parent_department"].queryset = (
                Department.objects.filter(parent__isnull=True, project_id__in=pids)
                .order_by("project__name", "name")
            )
        # поддепартамент выбираем ПОСЛЕ родителя
        self.fields["department"].required = False
        self.fields["department"].label = "Поддепартамент"
        # предустановка при редактировании существующей записи
        if self.instance and self.instance.department_id:
            if self.instance.department.parent:
                self.fields["parent_department"].initial = self.instance.department.parent_id
            else:
                self.fields["parent_department"].initial = self.instance.department_id


class UserDepartmentMemberInline(admin.TabularInline):
    model = DepartmentMember
    fk_name = "user"
    form = DepartmentMemberForm
    fields = ("parent_department", "department", "role")
    extra = 0
    verbose_name = "Участие в департаменте"
    verbose_name_plural = "Участие в департаментах"

    def has_add_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    # оставляем только «глазик» у FK‑виджетов
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        ff = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name in ("parent_department", "department", "role"):
            w = getattr(ff, "widget", None)
            if w:
                setattr(w, "can_add_related", False)
                setattr(w, "can_change_related", False)
                setattr(w, "can_view_related", True)
        return ff

    # пробросим user в форму
    def get_formset(self, request, obj=None, **kwargs):
        Formset = super().get_formset(request, obj, **kwargs)
        class _FS(Formset):
            def _construct_form(self, i, **kw):
                kw["user"] = obj
                return super()._construct_form(i, **kw)
        return _FS


class UserProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    fk_name = "user"
    fields = ("project", "role", "department")
    extra = 0
    verbose_name = "Участие в проекте"
    verbose_name_plural = "Участие в проектах"

    def has_add_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    # оставляем только «глазик» у FK‑виджетов
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        ff = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name in ("project", "role", "department"):
            w = getattr(ff, "widget", None)
            if w:
                setattr(w, "can_add_related", False)
                setattr(w, "can_change_related", False)
                setattr(w, "can_view_related", True)
        return ff


# --- вспомогательная выборка групп по логам
def _groups_for_user_tgid(tg_user_id: int, only_projects: list[int] | None = None):
    """
    Возвращает список групп (id, title, telegram_id, project_id),
    в которых пользователь писал сообщения (по raw_updates).
    """
    if tg_user_id is None:
        return []
    try:
        with connection.cursor() as cur:
            # 1) получить chat_id, где писал пользователь
            cur.execute("""
                SELECT DISTINCT ru.chat_id
                FROM raw_updates ru
                WHERE ru.user_id = %s
            """, [tg_user_id])
            chat_ids = [r[0] for r in cur.fetchall()]
    except Exception:
        # Если таблица raw_updates не существует
        return []

    if not chat_ids:
        return []

    qs = TgGroup.objects.filter(telegram_id__in=chat_ids)
    if only_projects:
        qs = qs.filter(project_id__in=only_projects)
    return list(qs.values_list("id", "title", "telegram_id", "project_id"))


# ===================== Админка User =====================
from django.utils.html import format_html_join, mark_safe

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    # текущие поля оставляем; добавляем сводку
    readonly_fields = ("summary_html",)
    inlines = [UserProjectMemberInline, UserDepartmentMemberInline]

    fieldsets = (
        ("Профиль", {
            "fields": ("username", "first_name", "last_name", "telegram_id", "status")
        }),
        ("Сводка по участию", {
            "fields": ("summary_html",)
        }),
    )

    list_display = ("__str__", "telegram_id", "status")
    list_filter = ("status",)
    search_fields = ("username", "first_name", "last_name", "telegram_id")  # Важно для автокомплита!

    def summary_html(self, obj: User):
        # Проекты
        pm = (ProjectMember.objects
              .filter(user_id=obj.id)
              .select_related("project", "role", "department")
              .order_by("project__id"))

        projects = format_html_join(
            "\n", "<li><b>{}</b> ({}){}</li>",
            (
                (
                    p.project.name,
                    p.role.name if p.role_id else "без роли",
                    f" — департамент: {p.department.name}" if p.department_id else ""
                )
                for p in pm
            )
        ) or "—"

        # Список id проектов для фильтра групп
        project_ids = [p.project_id for p in pm] or None

        # Департаменты (прямые назначения)
        dm = (DepartmentMember.objects
              .filter(user_id=obj.id)
              .select_related("department__project", "role")
              .order_by("department__project__id", "department__id"))

        departments = format_html_join(
            "\n", "<li>{} → {}</li>",
            (
                (d.department.project.name if d.department and d.department.project else "—",
                 d.department.name if d.department else "—")
                for d in dm
            )
        ) or "—"

        # Группы по логам
        groups = _groups_for_user_tgid(obj.telegram_id, only_projects=project_ids)
        
        # Подготовим данные о проектах для групп
        group_projects = {}
        if groups:
            group_tg_ids = [g[2] for g in groups]
            for grp in TgGroup.objects.filter(telegram_id__in=group_tg_ids).select_related('project'):
                if grp.project:
                    group_projects[grp.telegram_id] = grp.project.name
        
        groups_html = format_html_join(
            "\n",
            "<li>{} <span style='opacity:.7'>(chat_id: {})</span>{}</li>",
            (
                (
                    title or "—",
                    tg_id,
                    f" — проект: {group_projects.get(tg_id, '')}" if group_projects.get(tg_id) else ""
                )
                for (_id, title, tg_id, pid) in groups
            )
        ) or "—"

        return mark_safe(
            "<div>"
            "<h4>Проекты</h4><ul>{}</ul>"
            "<h4>Департаменты</h4><ul>{}</ul>"
            "<h4>Группы (по активности)</h4><ul>{}</ul>"
            "</div>".format(projects, departments, groups_html)
        )

    summary_html.short_description = "Проекты / Департаменты / Группы"

    # правило сохранения: если выбран только родитель — назначить во все его поддепартаменты
    def save_formset(self, request, form, formset, change):
        # Обрабатываем только инлайн участий в департаментах
        if formset.model is DepartmentMember:
            # Подготовим объекты без коммита (и чтобы были cleaned_data/deleted_forms)
            formset.save(commit=False)

            with transaction.atomic():
                # 1) Удаления — через deleted_forms (надёжно в Django 5)
                for fdel in getattr(formset, "deleted_forms", []):
                    inst = getattr(fdel, "instance", None)
                    if inst and inst.pk:
                        inst.delete()

                # 2) Сохранения/автораспределение
                user = form.instance
                created_bulk = 0

                for f in formset.forms:
                    # пропускаем удалённые формы и пустые
                    if f in getattr(formset, "deleted_forms", []):
                        continue
                    if not hasattr(f, "cleaned_data"):
                        continue
                    if f.cleaned_data.get("DELETE"):
                        continue

                    parent = f.cleaned_data.get("parent_department")
                    dept   = f.cleaned_data.get("department")
                    role   = f.cleaned_data.get("role")

                    if parent and not dept:
                        # выбран только родитель → назначаем во все его поддепартаменты
                        children = Department.objects.filter(parent=parent)
                        if not children.exists():
                            from django.contrib import messages
                            messages.warning(request, f"У департамента «{parent.name}» нет поддепартаментов.")
                        for ch in children:
                            dm, was_created = DepartmentMember.objects.get_or_create(
                                user=user, department=ch, defaults={"role": role}
                            )
                            created_bulk += int(was_created)
                            # Создаем ProjectMember с привязкой к департаменту
                            ProjectMember.objects.get_or_create(
                                project=ch.project, user=user, role=role, department=ch
                            )
                        # Удаляем общий уровень для этой роли (правило P1)
                        ProjectMember.objects.filter(
                            project=parent.project, user=user, role=role, department__isnull=True
                        ).delete()
                        # Не сохраняем текущий «родительский» ряд как отдельную запись
                        continue

                    # Обычный случай — выбран конкретный поддепартамент
                    if dept:
                        obj = f.save(commit=False)
                        obj.user = user
                        obj.save()
                        # Создаем ProjectMember с привязкой к департаменту
                        if dept.project and role:
                            ProjectMember.objects.get_or_create(
                                project=dept.project, user=user, role=role, department=dept
                            )
                            # Удаляем общий уровень для этой роли (правило P1)
                            ProjectMember.objects.filter(
                                project=dept.project, user=user, role=role, department__isnull=True
                            ).delete()

                formset.save_m2m()

                if created_bulk:
                    from django.contrib import messages
                    messages.success(request, f"Назначено в {created_bulk} поддепартамент(а).")
            return

        # остальные инлайны — стандартно
        return super().save_formset(request, form, formset, change)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        
        if request.method == "POST" and request.user.is_superuser and object_id:
            if "_remove_from_all_departments" in request.POST:
                DepartmentMember.objects.filter(user_id=object_id).delete()
                self.message_user(request, "Пользователь удален из всех департаментов")
            if "_remove_from_all_projects" in request.POST:
                ProjectMember.objects.filter(user_id=object_id).delete()
                self.message_user(request, "Пользователь удален из всех проектов")
        
        # передаём дерево департаментов в шаблон пользователя (для JS‑каскада)
        if object_id:
            pids = list(ProjectMember.objects.filter(user_id=object_id).values_list("project_id", flat=True))
            dep_tree = list(Department.objects.filter(project_id__in=pids)
                            .values("id", "name", "parent_id", "project_id"))
            extra_context["dep_tree"] = dep_tree
        
        return super().changeform_view(request, object_id, form_url, extra_context)


# ===================== Админка Role =====================
@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "can_assign", "can_close")
    search_fields = ("name",)  # Необходимо для автокомплита


# ===================== Инлайны для департаментов =====================
class ChildDepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ("parent", "name", "lead_role")  # project не показываем
        widgets = {"parent": forms.HiddenInput()}

    def clean(self):
        cleaned = super().clean()
        parent = cleaned.get("parent")
        if parent:
            # гарантируем, что instance.project совпадает с проектом родителя
            self.instance.project_id = parent.project_id
        return cleaned

class ChildInlineFormSet(BaseInlineFormSet):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._new_objs = []
    def save_new(self, form, commit=True):
        obj = super().save_new(form, commit)
        self._new_objs.append(obj)
        return obj

class ChildDepartmentInline(admin.TabularInline):
    model = Department
    fk_name = "parent"
    fields = ("name", "lead_role")  # НЕ показываем project - он наследуется
    show_change_link = True
    extra = 0  # Убираем пустую форму - будем использовать кнопку "Добавить"
    can_delete = True
    verbose_name = "Поддепартамент"
    verbose_name_plural = "Поддепартаменты"
    
    # ВАЖНО: показываем только существующие поддепартаменты
    # Для создания новых используйте кнопку "Добавить поддепартамент"
    
    def get_formset(self, request, obj=None, **kwargs):
        """Передаем проект родителя в формы"""
        formset = super().get_formset(request, obj, **kwargs)
        
        class InlineFormSet(formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # Устанавливаем проект от родителя для всех форм
                if obj and obj.project_id:
                    for form in self.forms:
                        if not form.instance.pk:  # Только для новых объектов
                            form.instance.project_id = obj.project_id
                            form.instance.parent_id = obj.id
                        
            def save_new(self, form, commit=True):
                """При сохранении новых поддепартаментов"""
                instance = form.instance
                if self.instance and self.instance.project_id:
                    instance.project_id = self.instance.project_id
                    instance.parent_id = self.instance.id
                return super().save_new(form, commit)
                
        return InlineFormSet
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Убираем возможность редактировать FK поля"""
        f = super().formfield_for_foreignkey(db_field, request, **kwargs)
        # Убираем иконки добавления/изменения  
        # ВАЖНО: убираем иконку "+" чтобы не путать пользователя
        if hasattr(f.widget, 'can_add_related'):
            f.widget.can_add_related = False
        if hasattr(f.widget, 'can_change_related'):
            f.widget.can_change_related = False
        if hasattr(f.widget, 'can_delete_related'):
            f.widget.can_delete_related = False
        return f
    
    def has_add_permission(self, request, obj=None):
        """Разрешаем добавление только для департаментов 1-го уровня"""
        if obj and obj.parent_id is None:
            return True
        return False

# ---------- Редактируемый инлайн для листовых узлов ----------
from django.db import connection

class DepartmentMemberInline(admin.TabularInline):
    model = DepartmentMember
    fields = ("user", "role")
    extra = 0
    verbose_name_plural = "Состав департамента"

    def get_formset(self, request, obj=None, **kwargs):
        self._parent_obj = obj
        return super().get_formset(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        f = super().formfield_for_foreignkey(db_field, request, **kwargs)
        parent = getattr(self, "_parent_obj", None)

        if db_field.name == "user":
            if parent and parent.project_id:
                # Пробуем получить участников проекта
                project_members = User.objects.filter(
                    projectmember__project_id=parent.project_id
                ).distinct()
                
                # ВАЖНЫЙ FALLBACK: если участников нет - показываем ВСЕХ пользователей
                if project_members.exists():
                    f.queryset = project_members.order_by("username")
                else:
                    print(f"DEBUG: No ProjectMembers for project_id={parent.project_id}, showing ALL users")
                    f.queryset = User.objects.all().order_by("username")
            else:
                f.queryset = User.objects.all().order_by("username")

        if db_field.name == "role":
            # Аналогично — если надо сужать роли по проекту
            f.queryset = Role.objects.all().order_by("name")

        # выключим иконки добавления связей в инлайне
        for attr in ("can_add_related","can_change_related","can_view_related","can_delete_related"):
            if hasattr(f.widget, attr): 
                setattr(f.widget, attr, False)
        return f


from collections import defaultdict

# --- Инлайн-агрегатор на родителе (READ-ONLY, 1 строка на пользователя) ---
class AllMembersInline(admin.TabularInline):
    model = DepartmentMember
    fields = ("user", "roles_joined", "subdeps_joined")
    readonly_fields = ("user", "roles_joined", "subdeps_joined")
    extra = 0
    can_delete = False
    show_change_link = False
    verbose_name_plural = "Сводный состав (только просмотр)"

    # RO-права
    def has_view_permission(self, r, o=None): return True
    def has_add_permission(self, r, o=None): return False
    def has_change_permission(self, r, o=None): return False
    def has_delete_permission(self, r, o=None): return False

    # кэш для вычисляемых колонок
    _roles_by_user = {}
    _subs_by_user = {}

    def get_formset(self, request, obj=None, **kwargs):
        base_fs = super().get_formset(request, obj, **kwargs)

        # если объект не сохранён — пусто
        if not obj or not obj.pk:
            class _EmptyFS(base_fs):
                def get_queryset(self_inner):
                    return self_inner.model._default_manager.none()
            return _EmptyFS

        # 1) Собираем ids: родитель + все потомки
        ids, q = [obj.pk], [obj.pk]
        parent_of = {}
        name_of = {obj.pk: obj.name}
        while q:
            rows = list(Department.objects
                        .filter(parent_id__in=q)
                        .values("id", "name", "parent_id"))
            if not rows:
                break
            ids.extend(r["id"] for r in rows)
            parent_of.update({r["id"]: r["parent_id"] for r in rows})
            name_of.update({r["id"]: r["name"] for r in rows})
            q = [r["id"] for r in rows]

        # 2) Агрегируем по пользователю: роли и ближайшие поддепартаменты
        members = (DepartmentMember.objects
                   .filter(department_id__in=ids)
                   .select_related("user", "role", "department")
                   .order_by("user_id", "id"))

        roles_by_user: dict[int, set[str]] = defaultdict(set)
        subdeps_by_user: dict[int, set[str]] = defaultdict(set)
        first_pk_by_user: dict[int, int] = {}

        def first_child_of_parent(dept_id: int):
            node, prev = dept_id, None
            while node and node != obj.pk:
                prev = node
                node = parent_of.get(node)
            return prev  # None → запись висит на самом родителе

        for m in members:
            first_pk_by_user.setdefault(m.user_id, m.pk)
            if m.role_id:
                roles_by_user[m.user_id].add(m.role.name)
            if m.department_id != obj.pk:
                child = first_child_of_parent(m.department_id)
                if child:
                    subdeps_by_user[m.user_id].add(name_of.get(child, str(child)))

        # сохраняем строки для вычисляемых колонок
        self._roles_by_user = {u: ", ".join(sorted(v)) if v else "—"
                               for u, v in roles_by_user.items()}
        self._subs_by_user = {u: ", ".join(sorted(v)) if v else "—"
                              for u, v in subdeps_by_user.items()}

        # итоговый queryset: 1 любая запись на пользователя (для строки)
        aggregated_qs = (DepartmentMember.objects
                         .filter(pk__in=list(first_pk_by_user.values()))
                         .select_related("user")
                         .order_by("user__username", "pk"))

        # 3) Класс-обёртка с переопределённым get_queryset (важно!)
        class _AggregatedFS(base_fs):
            def get_queryset(self_inner):
                return aggregated_qs

        return _AggregatedFS

    # вычисляемые колонки
    def roles_joined(self, obj):       # все роли пользователя через запятую
        return self._roles_by_user.get(obj.user_id, "—")
    roles_joined.short_description = "Роли"

    def subdeps_joined(self, obj):     # ближайшие дочерние от текущего родителя
        return self._subs_by_user.get(obj.user_id, "—")
    subdeps_joined.short_description = "Поддепартаменты"


# ===================== Админка Department =====================
from django.urls import path
from django.http import HttpResponseRedirect

class DepartmentAdminForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        parent = cleaned.get("parent")
        project = cleaned.get("project")
        if parent:
            # наследуем проект от родителя и не позволяем поменять вручную
            cleaned["project"] = getattr(parent, "project", None)
            if cleaned["project"] is None:
                raise forms.ValidationError("У родителя не задан проект — уточните данные.")
        else:
            if not project:
                raise forms.ValidationError("Для корневого департамента необходимо выбрать проект.")
        return cleaned

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    form = DepartmentAdminForm
    list_display = ("name", "project", "children_badge")
    list_filter = ("project",)
    search_fields = ("name",)
    
    class Media:
        js = ('admin/js/department_inline_fix.js',)
    # базовые поля для change-view
    fields = ("project", "name", "parent", "lead_role")
    autocomplete_fields = ("project", "parent", "lead_role")
    # используем свой шаблон change_form, чтобы показать кнопки
    # change_form_template = "admin/core/department/change_form.html"  # Отключаем пока нет шаблона

    # ====== helpers контекста ======
    def _is_add(self, obj): 
        return obj is None
    def _is_add_child(self, request, obj):
        return self._is_add(obj) and request.GET.get("parent")
    def _is_add_root(self, request, obj):
        return self._is_add(obj) and not request.GET.get("parent")

    def parent_display(self, obj):
        return obj.parent.name if (obj and obj.parent_id) else "—"
    parent_display.short_description = "Родительский департамент"

    # ====== ограничение выбора родителя ======
    def get_form(self, request, obj=None, **kwargs):
        request._current_department_obj = obj  # прокинем текущий объект в formfield_for_foreignkey
        form = super().get_form(request, obj, **kwargs)
        # если есть родитель — поле project делаем readonly
        if 'project' in form.base_fields and obj and obj.parent_id:
            form.base_fields['project'].disabled = True
        return form



    # ====== компоновка полей ======
    def get_fields(self, request, obj=None):
        # ADD (глобально): создаём родителя — без поля parent
        if obj is None and not request.GET.get("parent"):
            return ("project", "name", "lead_role")
        # ADD с ?parent=... : создаём дочку — parent не редактируем и не показываем селект
        if obj is None and request.GET.get("parent"):
            return ("project", "name", "lead_role", "parent_display")
        # CHANGE дочернего узла: parent скрыт (только текст)
        if obj and obj.parent_id:
            return ("project", "name", "lead_role", "parent_display")
        # CHANGE корня: parent по определению отсутствует
        if obj and not obj.parent_id:
            return ("project", "name", "lead_role")
        # fallback
        return super().get_fields(request, obj)

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        # на ADD child и CHANGE всегда readonly проект + сам родитель
        if (obj and obj.pk) or request.GET.get("parent"):
            ro += ["project", "parent", "parent_display"]
        return tuple(ro)

    # начальные значения при add child (?parent=<id>)
    def get_changeform_initial_data(self, request):
        init = super().get_changeform_initial_data(request)
        parent_id = request.GET.get("parent")
        if parent_id:
            try:
                parent = Department.objects.get(pk=parent_id)
                init["parent"] = parent
                init["project"] = parent.project  # Передаем объект, не ID
            except Department.DoesNotExist:
                pass
        return init

    # ограничиваем queryset полей FK в зависимости от режима
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # родитель: скрываем выпадашку в add-root (поле исключено), 
        # а в add-child ограничиваем ровно одним выбранным родителем
        if db_field.name == "parent":
            parent_id = request.GET.get("parent")
            if parent_id:
                try:
                    parent = Department.objects.get(pk=parent_id)
                    kwargs["queryset"] = Department.objects.filter(pk=parent_id)
                    kwargs["initial"] = parent  # ВАЖНО: устанавливаем начальное значение
                except Department.DoesNotExist:
                    kwargs["queryset"] = Department.objects.filter(parent__isnull=True)
            else:
                kwargs["queryset"] = Department.objects.filter(parent__isnull=True)
        # глобальный add-root: поле parent скрыто (его нет в fields), 
        # но на change-view можно показывать любое дерево в пределах проекта
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # жёстко фиксируем связки при сохранении
    def save_model(self, request, obj, form, change):
        # Валидация на уровне админки
        if obj.parent and obj.parent.parent_id:
            from django.core.exceptions import ValidationError
            raise ValidationError({'parent': 'Запрещено создавать 3-й уровень поддепартаментов.'})
        
        # Перестраховка: при сохранении поддепартамента — унаследовать проект
        if obj.parent_id and not obj.project_id:
            obj.project = obj.parent.project
        
        parent_id = request.GET.get("parent")
        if not change and parent_id:
            parent = Department.objects.get(pk=parent_id)
            obj.parent = parent
            obj.project = parent.project
        if not change and not parent_id:
            obj.parent = None  # гарантируем "родителя" при глобальном добавлении
        super().save_model(request, obj, form, change)

    _parent_only = False

    def get_queryset(self, request):
        qs = super().get_queryset(request).prefetch_related("children")
        return qs.filter(parent__isnull=True) if self._parent_only else qs

    def changelist_view(self, request, extra_context=None):
        self._parent_only = True
        try:
            return super().changelist_view(request, extra_context)
        finally:
            self._parent_only = False

    def children_badge(self, obj):
        n = obj.children.count()
        return format_html("<b>{}</b>", n) if n else "-"
    children_badge.short_description = "Дочерние"

    # ====== инлайны: как и договорились ранее ======
    def get_inline_instances(self, request, obj=None):
        # На странице «добавления» (obj=None) инлайны скрываем — сначала сохраняем,
        # затем редактируем с корректно определённым project.
        if not obj:
            return []
        is_root = (obj.parent_id is None)
        has_children = Department.objects.filter(parent=obj).exists()
        # родительский режим: дети + сводка (RO)
        if is_root or has_children:
            return [
                ChildDepartmentInline(self.model, self.admin_site),
                AllMembersInline(self.model, self.admin_site),
            ]
        # лист: редактируем только свой состав
        return [DepartmentMemberInline(self.model, self.admin_site)]
    

    # обработка кнопок сохранения
    def response_add(self, request, obj, post_url_continue=None):
        if "_save_and_dashboard" in request.POST:
            return HttpResponseRedirect(reverse("admin:index"))
        if request.GET.get("parent"):
            return HttpResponseRedirect(
                reverse("admin:core_department_change", args=[obj.pk])
            )
        # дефолт: оставить на этой же форме по кнопке СОХРАНИТЬ (_continue)
        return super().response_add(request, obj, post_url_continue)
    
    def response_change(self, request, obj):
        if "_save_and_dashboard" in request.POST:
            return HttpResponseRedirect(reverse("admin:index"))
        return super().response_change(request, obj)
    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        obj = self.get_object(request, object_id) if object_id else None
        can_add_child = False
        if obj:
            # Можно добавить поддепартамент только если текущий департамент 1-го уровня
            can_add_child = (obj.parent_id is None)  # Только корневые могут иметь детей
        
        extra_context = (extra_context or {}) | {
            "show_chat_users": (request.GET.get("show_chat_users") == "1"),
            "can_add_child": can_add_child
        }
        return super().changeform_view(request, object_id, form_url, extra_context)

    # Автосинхронизация ProjectMember при добавлении в департамент
    def save_formset(self, request, form, formset, change):
        instances = formset.save()
        for inst in instances:
            if isinstance(inst, DepartmentMember):
                # Создаем запись с привязкой к департаменту
                pm, created = ProjectMember.objects.get_or_create(
                    project=inst.department.project,
                    user=inst.user,
                    role=inst.role,
                    department=inst.department,  # ВАЖНО: указываем департамент
                )
                # Удаляем общий уровень для этой роли (правило P1)
                ProjectMember.objects.filter(
                    project=inst.department.project,
                    user=inst.user,
                    role=inst.role,
                    department__isnull=True
                ).delete()


# ===================== Админка ProjectMember =====================
@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "project", "role", "department", "created_at")
    list_filter = ("project", "role", "department", "created_at")
    search_fields = ("user__username", "user__first_name", "project__name")
    autocomplete_fields = ("user", "project", "role", "department")


# ===================== Админка Task =====================
@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "responsible_display", "status", "deadline_display", "project")
    list_filter = ("status", "project", "created_at")
    search_fields = ("title", "description", "responsible_username")
    readonly_fields = ("created_at", "updated_at")
    
    def responsible_display(self, obj):
        if obj.responsible_user:
            return f"@{obj.responsible_user.username}" if obj.responsible_user.username else f"User {obj.responsible_user.telegram_id}"
        return obj.responsible_username
    responsible_display.short_description = "Responsible"
    
    def deadline_display(self, obj):
        if not obj.deadline:
            return "-"
        
        today = timezone.now().date()
        if obj.is_overdue:
            return format_html('<span style="color: red;">🔥 {}</span>', obj.deadline)
        elif obj.is_warning:
            return format_html('<span style="color: orange;">⏰ {}</span>', obj.deadline)
        else:
            return format_html('<span style="color: green;">✅ {}</span>', obj.deadline)
    deadline_display.short_description = "Deadline"


# ===================== ForumTopic скрытый админ =====================
class ForumTopicAdminHidden(admin.ModelAdmin):
    list_display = ("title", "group", "topic_id", "message_count", "last_seen")
    list_filter = ("group",)
    search_fields = ("title", "group__title")
    readonly_fields = ("topic_id", "message_count", "first_seen", "last_seen")
    fields = ("group", "topic_id", "title", "message_count", "first_seen", "last_seen")
    inlines = [TopicBindingInline]
    actions = ["sync_title_to_telegram"]

    def sync_title_to_telegram(self, request, queryset):
        """Синхронизация названия топика с Telegram через Bot API"""
        if not BOT_TOKEN:
            self.message_user(request, "BOT_TOKEN не настроен", level="error")
            return
        
        updated = 0
        for topic in queryset:
            if topic.topic_id == 0:
                continue  # General topic нельзя переименовать
            
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/editForumTopic"
            payload = {
                "chat_id": topic.group.telegram_id,
                "message_thread_id": topic.topic_id,
                "name": topic.title
            }
            
            try:
                response = requests.post(url, json=payload)
                if response.json().get("ok"):
                    updated += 1
            except Exception as e:
                self.message_user(request, f"Ошибка для {topic}: {e}", level="error")
        
        self.message_user(request, f"Обновлено топиков в Telegram: {updated}")
    
    sync_title_to_telegram.short_description = "Синхронизировать название с Telegram"

    def get_model_perms(self, request):
        """Скрываем из меню"""
        return {}


# Регистрируем ForumTopic без отображения в меню
admin.site.register(ForumTopic, ForumTopicAdminHidden)

# TopicRole больше не нужен - используем TopicBinding
# @admin.register(TopicRole)
# class TopicRoleAdmin(admin.ModelAdmin):
#     list_display = ('group', 'topic_id', 'user', 'role', 'department')
#     list_filter = ('group', 'role', 'department')
#     search_fields = ('group__title', 'topic_id', 'user__username')
#     autocomplete_fields = ('user', 'role', 'department')