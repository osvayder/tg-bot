from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import calendar


def build_calendar_kb(current_date: datetime) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру календаря для выбора даты
    Не показывает дни < сегодня
    """
    kb_rows = []
    
    # Заголовок с месяцем и годом
    month_year = current_date.strftime("%B %Y")
    kb_rows.append([
        InlineKeyboardButton(text="◀", callback_data=f"cal:prev:{current_date.strftime('%Y-%m')}"),
        InlineKeyboardButton(text=month_year, callback_data="cal:ignore"),
        InlineKeyboardButton(text="▶", callback_data=f"cal:next:{current_date.strftime('%Y-%m')}")
    ])
    
    # Дни недели
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    kb_rows.append([
        InlineKeyboardButton(text=day, callback_data="cal:ignore")
        for day in weekdays
    ])
    
    # Получаем сегодняшнюю дату
    today = datetime.now(current_date.tzinfo).date()
    
    # Создаем календарь на текущий месяц
    cal = calendar.monthcalendar(current_date.year, current_date.month)
    
    for week in cal:
        week_row = []
        for day in week:
            if day == 0:
                # Пустая ячейка
                week_row.append(InlineKeyboardButton(text=" ", callback_data="cal:ignore"))
            else:
                # Создаем дату для проверки
                date_obj = datetime(current_date.year, current_date.month, day).date()
                
                if date_obj < today:
                    # Прошедшие дни недоступны
                    week_row.append(InlineKeyboardButton(text="·", callback_data="cal:ignore"))
                elif date_obj == today:
                    # Сегодня выделяем
                    week_row.append(InlineKeyboardButton(
                        text=f"[{day}]",
                        callback_data=f"cal:{date_obj.strftime('%Y-%m-%d')}"
                    ))
                else:
                    # Будущие дни доступны
                    week_row.append(InlineKeyboardButton(
                        text=str(day),
                        callback_data=f"cal:{date_obj.strftime('%Y-%m-%d')}"
                    ))
        kb_rows.append(week_row)
    
    # Быстрые кнопки
    kb_rows.append([
        InlineKeyboardButton(text="📅 Сегодня", callback_data=f"cal:{today.strftime('%Y-%m-%d')}"),
        InlineKeyboardButton(text="📆 Завтра", callback_data=f"cal:{(today + timedelta(days=1)).strftime('%Y-%m-%d')}")
    ])
    
    # Отмена
    kb_rows.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data="cal:cancel")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)


def build_time_kb(step_minutes: int = 30) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для выбора времени
    """
    kb_rows = []
    
    # Генерируем времена с заданным шагом
    times = []
    current_hour = 0
    current_minute = 0
    
    while current_hour < 24:
        times.append(f"{current_hour:02d}:{current_minute:02d}")
        current_minute += step_minutes
        if current_minute >= 60:
            current_minute = 0
            current_hour += 1
    
    # Разбиваем на строки по 4 кнопки
    for i in range(0, len(times), 4):
        row = []
        for time_str in times[i:i+4]:
            row.append(InlineKeyboardButton(
                text=time_str,
                callback_data=f"time:{time_str}"
            ))
        kb_rows.append(row)
    
    # Популярные времена
    kb_rows.append([
        InlineKeyboardButton(text="🌅 09:00", callback_data="time:09:00"),
        InlineKeyboardButton(text="☀️ 12:00", callback_data="time:12:00"),
        InlineKeyboardButton(text="🌇 18:00", callback_data="time:18:00"),
        InlineKeyboardButton(text="🌙 23:59", callback_data="time:23:59")
    ])
    
    # Отмена
    kb_rows.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data="cal:cancel")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)