#!/usr/bin/env python3
import os
import sys

# --- НАСТРОЙКИ ---

# Имя итогового файла
OUTPUT_FILENAME = 'project_structure.txt'

# Максимальная глубина сканирования
MAX_DEPTH = 10

# --- КОНЕЦ НАСТРОЕК ---


def create_tree_structure(path, prefix="", depth=0, is_last=True):
    """
    Создает древовидную структуру проекта в текстовом формате
    БЕЗ ФИЛЬТРАЦИИ - показывает ВСЕ файлы
    """
    if depth > MAX_DEPTH:
        return ""
    
    name = os.path.basename(path) or path
    
    result = ""
    
    # Добавляем текущий элемент
    if depth > 0:
        connector = "└── " if is_last else "├── "
        result += prefix + connector + name
        
        # Добавляем описание типа файла
        if os.path.isfile(path):
            ext = os.path.splitext(name)[1]
            file_types = {
                '.py': ' (Python)',
                '.js': ' (JavaScript)',
                '.json': ' (JSON)',
                '.md': ' (Markdown)',
                '.txt': ' (Text)',
                '.yml': ' (YAML)',
                '.yaml': ' (YAML)',
                '.sh': ' (Shell)',
                '.command': ' (Command)',
                '.env': ' (Environment)',
                '.sql': ' (SQL)',
                '.html': ' (HTML)',
                '.css': ' (CSS)',
                '.dockerfile': ' (Docker)',
                '.ps1': ' (PowerShell)',
                '.diff': ' (Diff/Patch)',
                '.example': ' (Example)',
                '.pyc': ' (Python Compiled)',
                '.applescript': ' (AppleScript)'
            }
            result += file_types.get(ext.lower(), '')
            
            # Добавляем размер файла
            try:
                size = os.path.getsize(path)
                if size < 1024:
                    result += f" [{size} B]"
                elif size < 1024*1024:
                    result += f" [{size/1024:.1f} KB]"
                else:
                    result += f" [{size/(1024*1024):.1f} MB]"
            except:
                pass
                
        result += "\n"
    
    # Если это директория, обрабатываем ВСЁ содержимое
    if os.path.isdir(path):
        try:
            items = os.listdir(path)  # Берём ВСЕ файлы
            
            # Сортируем: сначала папки, потом файлы
            items.sort(key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()))
            
            for i, item in enumerate(items):
                item_path = os.path.join(path, item)
                is_last_item = (i == len(items) - 1)
                
                if depth > 0:
                    extension = "    " if is_last else "│   "
                    new_prefix = prefix + extension
                else:
                    new_prefix = ""
                
                result += create_tree_structure(item_path, new_prefix, depth + 1, is_last_item)
                
        except PermissionError:
            result += prefix + "    [Permission Denied]\n"
    
    return result


def create_summary(path):
    """Создает полную статистику ВСЕХ файлов проекта"""
    file_count = 0
    dir_count = 0
    total_size = 0
    file_types = {}
    hidden_files = 0
    
    for root, dirs, files in os.walk(path):
        dir_count += len(dirs)
        
        for file in files:
            file_count += 1
            file_path = os.path.join(root, file)
            
            # Считаем скрытые файлы
            if file.startswith('.'):
                hidden_files += 1
            
            # Считаем размер
            try:
                total_size += os.path.getsize(file_path)
            except:
                pass
            
            # Считаем типы файлов
            ext = os.path.splitext(file)[1].lower()
            if ext:
                file_types[ext] = file_types.get(ext, 0) + 1
            else:
                file_types['[no extension]'] = file_types.get('[no extension]', 0) + 1
    
    # Форматируем размер
    if total_size < 1024*1024:
        size_str = f"{total_size/1024:.1f} KB"
    else:
        size_str = f"{total_size/(1024*1024):.2f} MB"
    
    summary = f"""
ПОЛНАЯ СТАТИСТИКА ПРОЕКТА:
==========================
Всего директорий: {dir_count}
Всего файлов: {file_count}
Скрытых файлов: {hidden_files}
Общий размер: {size_str}

ВСЕ ТИПЫ ФАЙЛОВ:
"""
    
    for ext, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True):
        summary += f"  {ext}: {count} файлов\n"
    
    return summary


def main():
    """Основная функция"""
    # Получаем директорию, где находится скрипт
    script_path = os.path.realpath(__file__)
    script_dir = os.path.dirname(script_path)
    project_name = os.path.basename(script_dir)
    
    print(f"📂 Создаю ПОЛНУЮ структуру проекта: {project_name}")
    print(f"📍 Путь: {script_dir}")
    print(f"⚠️  Включены ВСЕ файлы (включая скрытые, системные и т.д.)\n")
    
    # Создаем заголовок
    header = f"""PROJECT STRUCTURE (FULL): {project_name}
{"=" * (26 + len(project_name))}
Path: {script_dir}
Generated: {os.popen('date').read().strip()}
Mode: SHOW ALL FILES (no filtering)

ПОЛНАЯ ФАЙЛОВАЯ СТРУКТУРА:
==========================
"""
    
    # Создаем древовидную структуру
    tree = project_name + "/\n"
    tree += create_tree_structure(script_dir, "", 0, True)
    
    # Создаем полную сводку
    summary = create_summary(script_dir)
    
    # Создаем список всех файлов
    all_files = "\nПОЛНЫЙ СПИСОК ФАЙЛОВ:\n"
    all_files += "=" * 20 + "\n"
    
    for root, dirs, files in os.walk(script_dir):
        rel_path = os.path.relpath(root, script_dir)
        if rel_path != '.':
            all_files += f"\n📁 {rel_path}/\n"
        else:
            all_files += f"\n📁 [root]/\n"
        
        for file in sorted(files):
            all_files += f"  • {file}\n"
    
    # Собираем все вместе
    full_content = header + tree + "\n" + summary + all_files
    
    # Сохраняем в файл
    output_path = os.path.join(script_dir, OUTPUT_FILENAME)
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
        
        print(f"✅ ПОЛНАЯ структура сохранена в: {OUTPUT_FILENAME}")
        print(f"📄 Размер файла: {len(full_content)} символов")
        print(f"📊 Обработано файлов: все файлы без исключений")
        print("\n📋 Файл готов для использования с нейросетями!")
        print("\nМожете закрыть это окно.")
        
    except Exception as e:
        print(f"❌ Ошибка при сохранении: {e}")
        print("\nМожете закрыть это окно.")


if __name__ == "__main__":
    main()