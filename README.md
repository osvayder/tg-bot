# 📋 Telegram Production Coordinator Bot

> Интеллектуальная система управления производством графического контента через Telegram с автоматизацией контроля задач, эскалаций и маршрутизации сообщений между командами.

## 🎯 Преимущества Git/GitHub для AI-разработки

### Почему GitHub критически важен:
- **Единый источник истины** - все AI работают с одним репозиторием
- **Полный контекст** - AI видят весь проект, а не фрагменты
- **История изменений** - можно откатить любые изменения
- **Параллельная работа** - эксперименты в отдельных ветках
- **Автоматическая документация** - каждый коммит документирует изменения

### Workflow преимущества:
```
Без GitHub: копировать код → объяснять контекст → терять версии
С GitHub: ссылка на репо → AI понимает всё → git push → синхронизация
```

## 🚀 Быстрый старт

### Требования
- Docker Desktop
- Git
- PowerShell (Windows) или Bash (Linux/Mac)
- Telegram Bot Token от [@BotFather](https://t.me/botfather)
- GitHub аккаунт (для синхронизации с AI)

### Установка и запуск

```bash
# Клонировать репозиторий
git clone https://github.com/osvayder/tg-bot.git
cd tg-bot

# Создать файл с переменными окружения
cp .env.example .env
# Отредактировать .env и добавить BOT_TOKEN

# Запустить через Docker Compose
docker-compose up -d

# Проверить статус
docker ps
```

Админка будет доступна по адресу: http://localhost:8000/admin (admin/admin)

## 📦 Технологический стек

| Компонент | Технология | Описание |
|-----------|-----------|----------|
| **Bot** | Python 3.12 + aiogram 3.x | Telegram бот с webhook/long-poll |
| **Database** | PostgreSQL 15 | Основная БД для хранения данных |
| **Cache** | Redis 7 | Кеш и временное хранилище |
| **Admin** | Django 5.0 | Административная панель |
| **Deployment** | Docker Compose | Контейнеризация сервисов |

### Планируется к внедрению:
- **API**: FastAPI + Pydantic v2 (Sprint 2)
- **Queue**: Celery (Sprint 2)
- **Frontend**: React Dashboard (Sprint 4)
- **Vector Search**: PGVector (Sprint 3)

## 🤖 Команды бота

### Управление задачами
- `/start` - инициализация бота
- `/whoami` - информация о пользователе и ролях
- `/ping` - проверка работы бота
- `/checklast N` - выбор задач из последних N сообщений
- `/add [задача]` - создать новую задачу
- `/syncmembers` - синхронизация участников группы

### Парсинг дат (русский язык)
- "сегодня", "завтра", "послезавтра"
- "через час", "через 2 дня", "через неделю"
- "в понедельник", "в пятницу"
- "15 марта", "1 января 2025"
- "15.03", "01.01.2025"
- "в 14:00", "завтра в 10:30"

## 🏗 Архитектура

### Текущая реализация (Sprint 0 - CLI MVP)
```
tg-bot/
├── bot/                    # ✅ Telegram бот (работает)
│   ├── main.py            # Entry point с Redis кэшированием
│   ├── handlers/          # Обработчики команд
│   │   └── calendar.py    # Календарь для выбора дат
│   └── services/          # Сервисы
│       └── datetime.py    # Парсинг дат на русском
├── admin/                  # ✅ Django админка (работает)
│   ├── manage.py         
│   └── core/             # Модели и админ панель
│       ├── models.py     # Project, User, Task, Department, Role
│       ├── admin.py      # Кастомизированная админка
│       └── templates/    # UI с каскадными селектами
├── tests/                  # ✅ Тесты
├── docker-compose.yml      # ✅ Docker окружение
├── .env                    # Конфигурация
└── README.md              # Этот файл
```

## 🎯 Основные возможности

### ✅ Реализовано (Sprint 0 - CLI MVP)
- [x] **Управление задачами** - создание, назначение, отслеживание
- [x] **Парсинг дат** - понимание дат на русском языке
- [x] **Календарь** - визуальный выбор дедлайнов
- [x] **Департаменты** - двухуровневая иерархия
- [x] **Роли и права** - гибкая система доступа
- [x] **ProjectMember** - участники с множественными ролями
- [x] **TopicBinding** - автоназначение ответственных
- [x] **Redis кэш** - 5-минутный TTL для resolver'а
- [x] **Django админка** - полное управление данными
- [x] **Docker окружение** - легкий запуск и развертывание
- [x] **GitHub интеграция** - синхронизация с AI-ассистентами

### 🚧 В разработке (Sprint 1)
- [ ] **Профили групп** - настройки поведения для разных типов чатов
- [ ] **Webhook режим** - для production окружения
- [ ] **API слой** - FastAPI для интеграций

### 📅 Планируется
- [ ] **Автопарсер** - автоматическое создание задач из сообщений
- [ ] **Правила маршрутизации** - автоматическая пересылка по условиям
- [ ] **Эскалации** - многоуровневые уведомления о просрочках
- [ ] **React Dashboard** - веб-интерфейс для аналитики

## 📊 Модели данных

### Основные сущности
- **Project** - контейнер для всей работы
- **TgGroup** - Telegram группы с профилями и маршрутизацией
- **User** - пользователи из Telegram
- **Role** - роли с правами (can_assign, can_close)
- **Department** - иерархическая структура (max 2 уровня)
- **ProjectMember** - участники с ролями в проектах/департаментах
- **Task** - задачи с дедлайнами и статусами
- **ForumTopic** - топики в супергруппах
- **TopicBinding** - привязка топиков к ответственным

### Правило P1 (ProjectMember)
Для тройки (user, project, role) допускается:
- **Либо** одна запись с department=NULL (роль на уровне проекта)
- **Либо** записи с department!=NULL (роль в департаментах)
- **Но не оба одновременно** (автоочистка при сохранении)

## 🛠 Команды управления

```bash
# Docker команды
docker-compose up -d        # Запуск всех сервисов
docker-compose down         # Остановка
docker-compose logs -f bot  # Логи бота
docker-compose logs -f admin # Логи админки

# Django миграции
docker-compose exec admin python manage.py migrate
docker-compose exec admin python manage.py createsuperuser

# Тестирование
docker-compose exec bot pytest
docker-compose exec bot pytest --cov=.
```

## 🧪 Тестирование

```bash
# Запустить все тесты
docker-compose exec bot pytest

# Конкретный модуль
docker-compose exec bot pytest tests/test_datetime_parse.py -v

# С покрытием
docker-compose exec bot pytest --cov=bot tests/
```

### Smoke тесты в Telegram
```
/start - проверка инициализации
/ping - проверка БД
/whoami - проверка авторизации
/checklast 5 - проверка парсинга
```

## 📝 Переменные окружения

Создайте файл `.env` на основе `.env.example`:

```env
# Telegram
BOT_TOKEN=your_bot_token_from_botfather
SHADOW_MODE=false  # true = бот только логирует
TIMEZONE=Europe/Moscow

# Database
DB_HOST=db
DB_PORT=5432
DB_NAME=botdb
DB_USER=bot
DB_PASSWORD=secure_password

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Django
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
```

## 🐛 Решение проблем

### Бот не запускается
```bash
docker-compose logs bot --tail=50
# Проверить BOT_TOKEN в .env
```

### Ошибки БД
```bash
docker-compose exec db psql -U bot -d botdb
\dt  # Показать таблицы
\d+ core_projectmember  # Структура таблицы
```

### Сброс всего проекта
```bash
docker-compose down -v  # Удалить контейнеры и volumes
docker-compose up -d --build  # Пересобрать и запустить
```

## 🤝 AI-Driven Development Workflow

### 🎯 Роли AI-ассистентов
- **GPT-5 Pro** - Координатор проекта (анализ, постановка задач)
- **Claude Opus 4.1** - Архитектурный советник (проверка решений)
- **Claude Code** - Исполнительный разработчик (написание кода)

### 📋 Процесс разработки

#### 1. GPT-5 Pro (Координатор)
```markdown
# Подключение к репозиторию:
"Проанализируй https://github.com/osvayder/tg-bot и определи следующую задачу"

# GPT анализирует:
- Текущее состояние проекта
- Roadmap и спринты
- Открытые issues
- Формирует детальную задачу
```

#### 2. Claude Opus 4.1 (Советник)
```markdown
# Проверка архитектуры:
"Вот задача от координатора: [задача]. Репозиторий: github.com/osvayder/tg-bot"

# Claude Opus проверяет:
- Архитектурное решение
- Структуру БД
- Совместимость с существующим кодом
- Создает артефакты с кодом
```

#### 3. Claude Code (Исполнитель)
```bash
# Получает код и инструкции
# Реализует в проекте
# Тестирует локально
# Коммитит изменения:
git add .
git commit -m "feat(sprint1): описание #issue"
git push
```

### 🔄 Синхронизация через GitHub

```
GPT-5 Pro → [Анализ GitHub] → Задача
    ↓
Claude Opus → [Проверка архитектуры] → Код
    ↓
Claude Code → [Реализация] → git push
    ↓
GitHub → [Обновленный репозиторий]
    ↓
GPT-5 Pro → [Следующая итерация]
```

### 🛠 Команды Git для Claude Code

```bash
# Начало работы
git pull                    # Получить последние изменения

# После изменений
git add .                   # Добавить все файлы
git commit -m "type: desc"  # Закоммитить
git push                    # Отправить на GitHub

# Проверка
git status                  # Текущее состояние
git log --oneline -5        # История коммитов

# Если что-то пошло не так
git reset --hard HEAD       # Откатить изменения
git checkout -- file.py     # Откатить конкретный файл
```

### Соглашения о коммитах
- `feat:` - новая функциональность
- `fix:` - исправление бага
- `docs:` - изменения документации
- `refactor:` - рефакторинг кода
- `test:` - добавление тестов
- `chore:` - обслуживание кода

## 📈 Roadmap

### Phase 1: Foundation ✅ 
**Sprint 0 (CLI MVP) - ЗАВЕРШЕН**
- [x] Docker инфраструктура
- [x] Базовые команды бота
- [x] Django админка
- [x] Управление ролями и задачами
- [x] GitHub репозиторий
- [x] Redis кэширование
- [x] Парсинг дат на русском

### Phase 2: Intelligence 🚧
**Sprint 1 (Departments)** - ТЕКУЩИЙ
- [x] Модель департаментов с иерархией
- [x] ProjectMember с правилом P1
- [x] TopicBinding для автоназначения
- [ ] Профили групп
- [ ] Webhook режим

**Sprint 2 (Rules Engine)**
- [ ] Правила маршрутизации
- [ ] Эскалации
- [ ] Дайджесты
- [ ] FastAPI интеграция

**Sprint 3 (Auto Parser)**
- [ ] Парсер обещаний из сообщений
- [ ] Confidence scoring
- [ ] Learning mode

### Phase 3: Scale 📅
**Sprint 4 (Analytics & UI)**
- [ ] React Dashboard
- [ ] Графики и метрики
- [ ] AI-рекомендации
- [ ] Telegram Web App

## 📄 Лицензия

MIT License - свободное использование и модификация

## 👥 Команда и методология

### AI-Driven Development Team
- **GPT-5 Pro** - Координатор проекта
- **Claude Opus 4.1** - Архитектурный советник
- **Claude Code** - Исполнительный разработчик
- **osvayder** - Product Owner

### Особенности разработки
- Централизованный репозиторий на GitHub
- AI-ассистенты имеют доступ к полному контексту проекта
- Итеративная разработка по спринтам
- Автоматическое документирование через коммиты
- Полная прослеживаемость изменений

---

<div align="center">

**[Issues](https://github.com/osvayder/tg-bot/issues)** • **[Telegram](https://t.me/osvayder)**

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>

</div># CI Trigger Sun Aug 24 01:57:36 +04 2025
