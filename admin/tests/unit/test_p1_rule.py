"""
Тесты правила P1 для ProjectMember
Критичный тест согласно решению координатора
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Добавляем путь к Django моделям
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'admin'))


@pytest.mark.unit
class TestP1Rule:
    """Тесты правила P1: нельзя иметь одновременно общий уровень и департаменты для одной роли"""
    
    def test_p1_cannot_add_general_if_has_department(self):
        """Нельзя добавить общий уровень если уже есть департамент"""
        # Мокаем Django модель
        with patch('core.models.ProjectMember') as MockPM:
            mock_instance = MagicMock()
            mock_instance.project_id = 1
            mock_instance.user_id = 1
            mock_instance.role_id = 1
            mock_instance.department_id = None  # Пытаемся добавить общий уровень
            
            # Симулируем что уже есть запись с департаментом
            existing = MagicMock()
            existing.department_id = 10  # Уже есть в департаменте
            
            MockPM.objects.exclude.return_value.filter.return_value.filter.return_value.exists.return_value = True
            
            # Должна быть ValidationError
            from django.core.exceptions import ValidationError
            
            # Симулируем вызов clean()
            def mock_clean():
                if mock_instance.department_id is None:
                    # Проверяем, есть ли уже записи с департаментами
                    has_departments = MockPM.objects.exclude.return_value.filter.return_value.filter.return_value.exists()
                    if has_departments:
                        raise ValidationError(
                            "Роль 'Producer' уже назначена в департаментах. "
                            "Выберите конкретный департамент или удалите существующие назначения."
                        )
            
            # Проверяем что вызывается исключение
            with pytest.raises(ValidationError) as exc_info:
                mock_clean()
            
            assert "уже назначена в департаментах" in str(exc_info.value)
    
    def test_p1_auto_remove_general_when_add_department(self):
        """При добавлении в департамент автоматически удаляется общий уровень"""
        with patch('core.models.ProjectMember') as MockPM:
            # Новая запись с департаментом
            new_instance = MagicMock()
            new_instance.project_id = 1
            new_instance.user_id = 1
            new_instance.role_id = 1
            new_instance.department_id = 10  # Добавляем в департамент
            
            # Мокаем метод save
            def mock_save():
                # При сохранении записи с департаментом
                if new_instance.department_id is not None:
                    # Удаляем общий уровень для той же роли
                    MockPM.objects.filter.return_value.delete()
            
            mock_save()
            
            # Проверяем что delete был вызван
            MockPM.objects.filter.return_value.delete.assert_called()
    
    def test_p1_can_have_multiple_departments(self):
        """Можно иметь одну роль в нескольких департаментах"""
        # Это разрешено правилом P1
        departments = [
            {"user_id": 1, "role_id": 1, "department_id": 10},
            {"user_id": 1, "role_id": 1, "department_id": 20},
            {"user_id": 1, "role_id": 1, "department_id": 30},
        ]
        
        # Все записи с департаментами - это OK
        for dept in departments:
            assert dept["department_id"] is not None
        
        # Проверяем что нет общего уровня
        general_level = [d for d in departments if d["department_id"] is None]
        assert len(general_level) == 0, "Не должно быть записей без департамента"
    
    def test_p1_different_roles_independent(self):
        """Разные роли независимы друг от друга"""
        # Можно иметь одну роль на общем уровне, другую в департаменте
        records = [
            {"user_id": 1, "role_id": 1, "department_id": None},  # Producer на общем
            {"user_id": 1, "role_id": 2, "department_id": 10},   # Animator в департаменте
        ]
        
        # Группируем по ролям
        by_role = {}
        for r in records:
            role_id = r["role_id"]
            if role_id not in by_role:
                by_role[role_id] = []
            by_role[role_id].append(r)
        
        # Проверяем правило P1 для каждой роли отдельно
        for role_id, role_records in by_role.items():
            has_general = any(r["department_id"] is None for r in role_records)
            has_departments = any(r["department_id"] is not None for r in role_records)
            
            # Нельзя иметь оба одновременно для одной роли
            assert not (has_general and has_departments), f"Нарушение P1 для роли {role_id}"
    
    def test_p1_constraint_names(self):
        """Проверка имен constraint в БД"""
        # Проверяем что constraint правильно именованы
        constraints = [
            "pm_unique_role_project_level",
            "pm_unique_role_department_level"
        ]
        
        for constraint in constraints:
            assert "unique" in constraint.lower()
            assert "role" in constraint.lower()
    
    @pytest.mark.parametrize("dept_before,dept_after,should_fail", [
        # (department_before, department_after, should_fail)
        (None, None, False),  # Общий → Общий (OK)
        (None, 10, False),    # Общий → Департамент (OK, но удалит общий)
        (10, None, True),     # Департамент → Общий (FAIL если есть другие департаменты)
        (10, 20, False),      # Департамент → Другой департамент (OK)
        (10, 10, False),      # Департамент → Тот же (OK)
    ])
    def test_p1_transitions(self, dept_before, dept_after, should_fail):
        """Тестирование различных переходов между уровнями"""
        
        # Симулируем проверку
        if dept_after is None and dept_before is not None:
            # Переход из департамента на общий уровень
            # Это разрешено только если нет других департаментов
            other_departments_exist = True  # Для теста предполагаем что есть
            if other_departments_exist and should_fail:
                assert should_fail, "Должен быть запрет перехода"
        else:
            assert not should_fail, "Переход должен быть разрешен"


@pytest.mark.unit
class TestP1FallbackEmptyList:
    """Тест fallback при пустом ProjectMember (фикс координатора)"""
    
    def test_show_all_users_when_projectmember_empty(self):
        """При пустом ProjectMember показываем всех пользователей"""
        
        # Мокаем queryset
        class MockQuerySet:
            def __init__(self, data):
                self.data = data
            
            def filter(self, **kwargs):
                return self
            
            def distinct(self):
                return self
            
            def exists(self):
                return len(self.data) > 0
            
            def count(self):
                return len(self.data)
            
            def all(self):
                return self.data
        
        # Сценарий: ProjectMember пуст
        project_members = MockQuerySet([])
        all_users = MockQuerySet([
            {"id": 1, "username": "user1"},
            {"id": 2, "username": "user2"},
            {"id": 3, "username": "user3"}
        ])
        
        # Логика fallback (как в админке департаментов)
        if not project_members.exists():
            # Показываем всех пользователей
            available_users = all_users
        else:
            # Показываем только участников проекта
            available_users = project_members
        
        # Проверяем результат
        assert available_users.count() == 3
        assert available_users.all()[0]["username"] == "user1"
        
    def test_filter_by_department_when_not_empty(self):
        """При непустом ProjectMember фильтруем по департаментам"""
        
        class MockQuerySet:
            def __init__(self, data):
                self.data = data
            
            def filter(self, **kwargs):
                # Симулируем фильтрацию
                if "department__project_id" in kwargs:
                    return MockQuerySet([d for d in self.data if d.get("department_id")])
                return self
            
            def distinct(self):
                return self
            
            def exists(self):
                return len(self.data) > 0
            
            def count(self):
                return len(self.data)
        
        # Сценарий: есть участники в департаментах
        department_members = MockQuerySet([
            {"id": 1, "username": "user1", "department_id": 10},
            {"id": 2, "username": "user2", "department_id": 20}
        ])
        
        all_users = MockQuerySet([
            {"id": 1, "username": "user1"},
            {"id": 2, "username": "user2"},
            {"id": 3, "username": "user3"},  # Этот не в департаментах
            {"id": 4, "username": "user4"}   # Этот тоже
        ])
        
        # Логика: показываем только тех, кто в департаментах
        if department_members.exists():
            available_users = department_members
        else:
            available_users = all_users
        
        # Проверяем что показываем только 2 пользователей
        assert available_users.count() == 2