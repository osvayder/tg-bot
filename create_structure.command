#!/usr/bin/env python3
import os
import json
import sys

# --- НАСТРОЙКИ ---

# Список папок и файлов для игнорирования
IGNORE_LIST = [
    'node_modules',
    '.git',
    '.vscode',
    '__pycache__',
    'dist',
    'build',
    'Library',  # Игнорируем системную папку Library
    'Pictures',
    'Movies',
    'Music',
    '.Trash',
    'Applications',
    'venv',
    'collect_files.py',
    'file_list.txt',
    'create_structure.py',
    'create_structure.command',
    'project_structure.json',
    '_CONTEXT_FOR_AI.txt',
    '_MISSING_FILES_REPORT.txt',
    'files_for_neuron_network'
]

# Имя итогового JSON-файла
OUTPUT_FILENAME = 'project_structure.json'

# Максимальная глубина сканирования
MAX_DEPTH = 3

# --- КОНЕЦ НАСТРОЕК ---


def create_project_structure(path, depth=0):
    """
    Рекурсивно сканирует путь и создает словарь, представляющий
    структуру папок и файлов.
    """
    if depth > MAX_DEPTH:
        return None
        
    name = os.path.basename(path)

    if name in IGNORE_LIST:
        return None

    if os.path.isdir(path):
        structure = {
            "name": name,
            "type": "directory",
            "children": []
        }
        try:
            items = os.listdir(path)
            # Ограничиваем количество файлов
            if len(items) > 100:
                items = items[:100]
                
            for item_name in sorted(items):
                child_path = os.path.join(path, item_name)
                child_structure = create_project_structure(child_path, depth + 1)
                if child_structure:
                    structure["children"].append(child_structure)
        except PermissionError:
            return None
            
        return structure
    else:
        return {
            "name": name,
            "type": "file"
        }


def main():
    """
    Основная функция для запуска скрипта.
    """
    # Получаем директорию, где находится этот скрипт
    # Используем realpath для разрешения символических ссылок
    script_path = os.path.realpath(__file__)
    script_dir = os.path.dirname(script_path)
    
    print(f"Начинаю сканирование структуры проекта в: {script_dir}")
    print(f"Максимальная глубина: {MAX_DEPTH} уровня\n")
    
    project_json = create_project_structure(script_dir)

    if project_json:
        output_path = os.path.join(script_dir, OUTPUT_FILENAME)
        
        print(f"Сканирование завершено. Сохраняю структуру в файл: {output_path}")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(project_json, f, ensure_ascii=False, indent=4)
            
        print("\n✅ Готово! Структура проекта сохранена в project_structure.json")
        print("\nМожете закрыть это окно.")
    else:
        print("❌ Не удалось создать структуру проекта.")
        print("\nМожете закрыть это окно.")


if __name__ == "__main__":
    main()