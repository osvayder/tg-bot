import os, asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg, datetime, json
import redis.asyncio as aioredis
from services.datetime import parse_deadline
from handlers.calendar import build_calendar_kb, build_time_kb
from zoneinfo import ZoneInfo

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHADOW_MODE = os.getenv("SHADOW_MODE", "true").lower() in ("1", "true", "yes")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
_redis_client: aioredis.Redis | None = None

def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            decode_responses=True,
        )
    return _redis_client

# === Helper функции ====================================================
def format_task_created_response(count: int, ids: list[int] | None = None) -> str:
    if count <= 1 and ids:
        return f"📌 Задача добавлена в планировщик, id #{ids[0]}"
    if not ids: 
        return f"📌 Добавлено задач: {count}"
    ids_part = ", ".join(f"#{i}" for i in ids[:5])
    return f"📌 Добавлено задач: {count}. Первые id: {ids_part}"

def _cl_rows_key(chat_id: int, user_id: int) -> str:
    return f"checklast:{chat_id}:{user_id}:rows"

def _cl_sel_key(chat_id: int, user_id: int) -> str:
    return f"checklast:{chat_id}:{user_id}:sel"

def _quote(txt: str, n: int = 60) -> str:
    t = (txt or "").strip().replace("\n", " ")
    return (t[:n] + "…") if len(t) > n else t

# === DB helper =========================================================
async def get_conn():
    return await asyncpg.connect(
        user="bot",
        password=os.getenv("DB_PASSWORD"),
        database="botdb",
        host="db",
        port=5432,
    )

async def log_raw_update(msg: Message):
    try:
        compact = {
            "chat_id": msg.chat.id if msg.chat else None,
            "message_id": msg.message_id,
            "from_id": msg.from_user.id if msg.from_user else None,
            "topic_id": getattr(msg, "message_thread_id", None),
            "date": (getattr(msg, "date", None).isoformat() if getattr(msg, "date", None) else None),
            "has_text": bool(msg.text),
        }
        conn = await get_conn()
        # Try to upsert Telegram group metadata for per-group settings
        # НЕ создаем проект автоматически - только обновляем название если группа уже существует
        try:
            if msg.chat and msg.chat.type in ("group", "supergroup") and compact["chat_id"]:
                await conn.execute(
                    """
                    INSERT INTO core_tggroup (telegram_id, title, created_at, project_id)
                    VALUES ($1, $2, NOW(), NULL)
                    ON CONFLICT (telegram_id)
                    DO UPDATE SET title = EXCLUDED.title
                    -- НЕ трогаем project_id при обновлении
                    """,
                    compact["chat_id"],
                    getattr(msg.chat, "title", ""),
                )
        except Exception as e:
            # Schema might not exist yet; ignore silently
            print(f"TG_GROUP_UPSERT_WARN: {e}")
        # upsert core_user по входящему сообщению
        if msg.from_user and not msg.from_user.is_bot:
            def _norm(u): 
                return (u or "").lstrip("@").strip().lower()
            await conn.execute("""
                INSERT INTO core_user (telegram_id, username, first_name, last_name, status, created_at)
                VALUES ($1, $2, $3, $4, 'active', NOW())
                ON CONFLICT (telegram_id) DO UPDATE
                   SET username = COALESCE(NULLIF(EXCLUDED.username, ''), core_user.username),
                       first_name = COALESCE(EXCLUDED.first_name, core_user.first_name),
                       last_name  = COALESCE(EXCLUDED.last_name,  core_user.last_name)
            """,
            msg.from_user.id,
            _norm(msg.from_user.username),
            msg.from_user.first_name or "",
            msg.from_user.last_name or "",
            )
        
        # Обработка топиков для супергрупп с форумами
        if msg.chat and msg.chat.type == "supergroup":
            # 1) Получаем полную инфу о чате, чтобы знать is_forum
            chat = msg.chat
            try:
                if getattr(chat, "is_forum", None) is None:
                    chat = await bot.get_chat(chat.id)  # aiogram 3
            except Exception:
                pass
            is_forum = bool(getattr(chat, "is_forum", False))
            
            # 2) Определяем topic_id
            topic_id = getattr(msg, "message_thread_id", None)  # может отсутствовать в General
            
            # 3) Апсерт топика: General → topic_id=0
            if is_forum:
                tid = 0 if topic_id is None else int(topic_id)
                title_hint = "General" if tid == 0 else None
                
                try:
                    await conn.execute("""
                        INSERT INTO core_forumtopic (group_id, topic_id, title, first_seen, last_seen, message_count)
                        SELECT g.id, $2, COALESCE($3,''), NOW(), NOW(), 1
                        FROM core_tggroup g WHERE g.telegram_id=$1
                        ON CONFLICT (group_id, topic_id) DO UPDATE
                           SET last_seen = NOW(),
                               title = CASE 
                                         WHEN core_forumtopic.title IS NULL OR core_forumtopic.title = '' 
                                           THEN COALESCE(NULLIF($3,''), core_forumtopic.title)
                                         ELSE core_forumtopic.title
                                       END,
                               message_count = core_forumtopic.message_count + 1
                    """, msg.chat.id, tid, title_hint)
                except Exception as e:
                    print(f"FORUMTOPIC_UPSERT_WARN: {e}")
        await conn.execute(
            """
            INSERT INTO raw_updates (chat_id, message_id, user_id, text, payload, topic_id)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            """,
            compact["chat_id"],
            compact["message_id"],
            compact["from_id"],
            msg.text or "",
            json.dumps(compact, ensure_ascii=False, default=str),
            compact["topic_id"],
        )
        await conn.close()
        print(f"RAW_LOG_OK chat={compact['chat_id']} msg={compact['message_id']}")
    except Exception as e:
        print(f"RAW_LOG_ERR: {e}")
    
    # попытка маршрутизации (shadow для клиента соблюдается — в клиентский чат не пишем)
    try:
        await _maybe_route_to_forward(msg)
    except Exception as _e:
        print(f"route skip: {_e}")

async def _maybe_route_to_forward(msg: Message) -> None:
    # только группы/супергруппы
    if msg.chat.type not in ("group", "supergroup"):
        return
    # не трогаем команды и ботов
    if getattr(msg, "text", "") and msg.text.startswith("/"):
        return
    if msg.from_user and msg.from_user.is_bot:
        return
    # уже пересланные не гоняем
    if getattr(msg, "forward_date", None) or getattr(msg, "forward_from_chat", None) or getattr(msg, "forward_origin", None):
        return

    # смотрим, есть ли маршрут из этого чата
    conn = await get_conn()
    row = await conn.fetchrow("""
        SELECT g2.telegram_id AS dst_chat_id, g.forward_topic_id AS dst_topic_id
        FROM core_tggroup g
        LEFT JOIN core_tggroup g2 ON g.forward_to_id = g2.id
        WHERE g.telegram_id = $1
        LIMIT 1
    """, msg.chat.id)
    await conn.close()
    if not row or not row["dst_chat_id"] or row["dst_chat_id"] == msg.chat.id:
        return

    # форвардим молча, в указанный топик (если задан)
    try:
        dst_topic = row["dst_topic_id"]
        if dst_topic is not None:
            await bot.forward_message(
                chat_id=row["dst_chat_id"],
                from_chat_id=msg.chat.id,
                message_id=msg.message_id,
                message_thread_id=dst_topic,
            )
        else:
            await bot.forward_message(
                chat_id=row["dst_chat_id"],
                from_chat_id=msg.chat.id,
                message_id=msg.message_id,
            )
    except Exception as e:
        print(f"forward failed: {e}")

async def _update_raw_on_edit(msg: Message) -> None:
    """Обновляет запись в raw_updates при редактировании сообщения"""
    txt = (msg.text or msg.caption or "")[:4096]
    topic_id = getattr(msg, "message_thread_id", None)
    conn = await get_conn()
    res = await conn.execute(
        """
        UPDATE raw_updates
           SET text = $1,
               topic_id = COALESCE($4, topic_id)
         WHERE chat_id = $2 AND message_id = $3
        """,
        txt, msg.chat.id, msg.message_id, topic_id
    )
    # если вдруг строки нет (бот перезапускался) — создадим
    if res == "UPDATE 0":
        await conn.execute(
            """
            INSERT INTO raw_updates (chat_id, message_id, user_id, text, topic_id, payload)
            VALUES ($1,$2,$3,$4,$5,$6::jsonb)
            """,
            msg.chat.id,
            msg.message_id,
            (msg.from_user.id if msg.from_user else None),
            txt,
            topic_id,
            json.dumps({"message_type": "text"}, ensure_ascii=False),
        )
    await conn.close()

async def _is_shadow_for_chat(chat_id: int) -> bool | None:
    if not chat_id:
        return None
    try:
        conn = await get_conn()
        row = await conn.fetchrow(
            """
            SELECT gp.shadow_mode AS shadow
            FROM core_tggroup g
            LEFT JOIN core_groupprofile gp ON g.profile_id = gp.id
            WHERE g.telegram_id = $1
            """,
            chat_id,
        )
        await conn.close()
        if row is None:
            return None
        return bool(row["shadow"]) if row["shadow"] is not None else None
    except Exception as e:
        # Schema might not exist yet; fall back to global
        print(f"SHADOW_LOOKUP_WARN: {e}")
        return None

async def safe_reply(msg: Message, text: str, **kwargs):
    # Per-group shadow-mode overrides global if present
    shadow_override = None
    if msg.chat:
        shadow_override = await _is_shadow_for_chat(msg.chat.id)
    effective_shadow = SHADOW_MODE if shadow_override is None else shadow_override
    if effective_shadow:
        return
    try:
        # answer безопасно отдаёт в текущий топик/чат
        await msg.answer(text, **kwargs)
    except Exception:
        # fallback с явным thread id
        await msg.bot.send_message(
            chat_id=msg.chat.id,
            text=text,
            message_thread_id=getattr(msg, "message_thread_id", None),
            **kwargs,
        )

# === /checklast helpers ====================================================
def _parse_count_arg(command_text: str | None, default_count: int, max_count: int) -> int:
    if not command_text:
        return default_count
    parts = command_text.strip().split()
    if len(parts) <= 1:
        return default_count
    try:
        n = int(parts[1])
        if n < 1:
            return 1
        return min(n, max_count)
    except ValueError:
        return default_count

async def fetch_raw_updates_for_chat(chat_id: int, topic_id: int | None, limit: int):
    conn = await get_conn()
    rows = await conn.fetch(
        """
        SELECT id, chat_id, message_id, user_id, text, created_at
        FROM raw_updates
        WHERE chat_id = $1
          AND ($2::bigint IS NULL OR topic_id = $2)
          AND (text IS NOT NULL AND LEFT(text,1) <> '/')
        ORDER BY created_at DESC
        LIMIT $3
        """,
        chat_id,
        topic_id,
        limit,
    )
    await conn.close()
    return rows

async def fetch_raw_updates_by_ids(ids: list[int]):
    if not ids:
        return []
    conn = await get_conn()
    rows = await conn.fetch(
        """
        SELECT id, chat_id, message_id, user_id, text, topic_id, created_at
        FROM raw_updates
        WHERE id = ANY($1::bigint[])
        ORDER BY created_at DESC
        """,
        ids,
    )
    await conn.close()
    return rows

def _trim_text(text: str | None, length: int = 160) -> str:
    if not text:
        return "(no text)"
    t = text.strip()
    return t if len(t) <= length else (t[: length - 1] + "…")

def build_checklast_kb(rows: list[dict], selected: set[int]) -> InlineKeyboardMarkup:
    kb_rows = []
    for r in rows:
        mid = int(r.get("message_id", r.get("id", 0)))  # поддержка старого формата с id
        checked = "☑️" if mid in selected else "⬜️"
        title = _quote(r.get("text") or "", 40)
        kb_rows.append([InlineKeyboardButton(
            text=f"{checked} {r['idx']}) {title}",
            callback_data=f"cl:toggle:{mid}"
        )])
    # нижняя панель
    kb_rows.append([
        InlineKeyboardButton(text=f"✅ Создать задачи ({len(selected)})",
                             callback_data="cl:create"),
    ])
    kb_rows.append([
        InlineKeyboardButton(text="♻️ Сброс", callback_data="cl:reset"),
        InlineKeyboardButton(text="✖️ Отмена", callback_data="cl:cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)

async def _create_task_minimal(
    title: str,
    description: str | None,
    responsible_user_id: int | None,
    responsible_username: str | None,
    author_user_id: int | None = None,
    project_id: int | None = None,
    source_chat_id: int | None = None,
    source_message_id: int | None = None,
    source_topic_id: int | None = None,
):
    conn = await get_conn()
    
    # Гарантируем, что responsible_username не NULL
    responsible_username = responsible_username or "unknown"
    
    result = await conn.fetchval(
        """
        INSERT INTO core_task (
            title, description, responsible_user_id, responsible_username,
            author_user_id, project_id,
            status, created_at, updated_at,
            source_chat_id, source_message_id, source_topic_id
        )
        VALUES ($1::varchar, $2::text, $3, $4::varchar, $5, $6, 'TODO', NOW(), NOW(), $7, $8, $9)
        RETURNING id
        """,
        title[:256],
        description or "",
        responsible_user_id,
        responsible_username,
        author_user_id,
        project_id,
        source_chat_id,
        source_message_id,
        source_topic_id,
    )
    await conn.close()
    return result

async def ensure_schema():
    try:
        conn = await get_conn()
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_updates (
                id bigserial PRIMARY KEY,
                chat_id bigint,
                message_id bigint,
                user_id bigint,
                text text,
                payload jsonb,
                created_at timestamptz DEFAULT now()
            );
            """
        )
        await conn.execute("ALTER TABLE raw_updates ADD COLUMN IF NOT EXISTS topic_id bigint;")
        await conn.close()
        print("DB schema ensured (raw_updates)")
    except Exception as e:
        print(f"DB_SCHEMA_WARN: {e}")

# === Permission helpers ===================================================
async def _role_flags_for_user_in_chat(telegram_id: int, chat_id: int) -> tuple[bool, bool] | None:
    if not telegram_id:
        return None
    conn = await get_conn()
    row = await conn.fetchrow("""
        SELECT r.can_assign, r.can_close
        FROM core_projectmember pm
        JOIN core_user u ON u.id = pm.user_id
        JOIN core_role r ON r.id = pm.role_id
        JOIN core_tggroup g ON g.project_id = pm.project_id
        WHERE u.telegram_id = $1 AND g.telegram_id = $2
        ORDER BY pm.id DESC
        LIMIT 1
    """, telegram_id, chat_id)
    await conn.close()
    return (bool(row["can_assign"]), bool(row["can_close"])) if row else None

async def _role_flags_for_user(telegram_id: int) -> tuple[bool, bool]:
    if not telegram_id:
        return (False, False)
    conn = await get_conn()
    row = await conn.fetchrow("""
        SELECT r.can_assign AS can_assign, r.can_close AS can_close
        FROM core_projectmember pm
        JOIN core_user u ON u.id = pm.user_id
        JOIN core_role r ON r.id = pm.role_id
        WHERE u.telegram_id = $1
        ORDER BY pm.id DESC
        LIMIT 1
    """, telegram_id)
    await conn.close()
    return (bool(row["can_assign"]), bool(row["can_close"])) if row else (False, False)

async def _require_can_assign_msg(msg: Message) -> bool:
    telegram_id = msg.from_user.id if msg.from_user else None
    if not telegram_id:
        await safe_reply(msg, "🔒 Недостаточно прав")
        return False
    scoped = await _role_flags_for_user_in_chat(telegram_id, msg.chat.id)
    can_assign, _ = scoped if scoped is not None else await _role_flags_for_user(telegram_id)
    if not can_assign:
        await safe_reply(msg, "🔒 Недостаточно прав")
        return False
    return True

async def _require_can_close_msg(msg: Message) -> bool:
    telegram_id = msg.from_user.id if msg.from_user else None
    if not telegram_id:
        await safe_reply(msg, "🔒 Недостаточно прав")
        return False
    scoped = await _role_flags_for_user_in_chat(telegram_id, msg.chat.id)
    _, can_close = scoped if scoped is not None else await _role_flags_for_user(telegram_id)
    if not can_close:
        await safe_reply(msg, "🔒 Недостаточно прав")
        return False
    return True

async def _require_can_assign_cb(cb: CallbackQuery) -> bool:
    telegram_id = cb.from_user.id if cb.from_user else None
    if not telegram_id:
        await cb.answer("🔒 Недостаточно прав", show_alert=True)
        return False
    scoped = await _role_flags_for_user_in_chat(telegram_id, cb.message.chat.id)
    can_assign, _ = scoped if scoped is not None else await _role_flags_for_user(telegram_id)
    if not can_assign:
        await cb.answer("🔒 Недостаточно прав", show_alert=True)
        return False
    return True

# === TopicRole helpers ====================================================
async def _get_project_id_by_chat(chat_id: int) -> int | None:
    conn = await get_conn()
    row = await conn.fetchrow("""
        SELECT project_id FROM core_tggroup WHERE telegram_id = $1 LIMIT 1
    """, chat_id)
    await conn.close()
    return row["project_id"] if row else None

async def _resolve_responsible(conn, chat_id: int, topic_id: int | None, explicit_username: str | None):
    """Единый резолвер для определения ответственного через TopicBinding. Возвращает (user_id, username)"""
    
    # 1) Явный исполнитель через @username
    if explicit_username:
        row = await conn.fetchrow(
            "SELECT id, username, telegram_id FROM core_user WHERE LOWER(username) = $1", 
            explicit_username.lower()
        )
        if row:
            uname = row["username"] or f"id:{row['telegram_id']}"
            return row["id"], uname
        return None, None

    # 2) Автоназначение через TopicBinding с кэшированием
    if topic_id is None:
        return None, None
    
    # Пробуем получить из кэша Redis (TTL 5 минут)
    cache_key = f"responsible:{chat_id}:{topic_id}"
    try:
        redis_client = get_redis()
        cached = await redis_client.get(cache_key)
        if cached:
            parts = cached.split(":", 1)
            if len(parts) == 2:
                user_id = int(parts[0]) if parts[0] != "None" else None
                username = parts[1] if parts[1] != "None" else None
                return user_id, username
    except Exception as e:
        print(f"Redis cache read error: {e}")
        
    # Находим привязки топика, отсортированные по приоритету
    bindings = await conn.fetch("""
        SELECT tb.user_id, tb.role_id, tb.department_id, tb.priority
        FROM core_topicbinding tb
        JOIN core_forumtopic ft ON ft.id = tb.topic_id
        JOIN core_tggroup g ON g.id = ft.group_id
        WHERE g.telegram_id = $1 AND ft.topic_id = $2
        ORDER BY tb.priority ASC
    """, chat_id, topic_id)
    
    if not bindings:
        return None, None

    # Проходим по привязкам в порядке приоритета
    for tb in bindings:
        # 2a) Прямое назначение на пользователя
        if tb["user_id"]:
            row = await conn.fetchrow(
                "SELECT id, username, telegram_id FROM core_user WHERE id = $1", 
                tb["user_id"]
            )
            if row:
                uname = row["username"] or f"id:{row['telegram_id']}"
                # Сохраняем в кэш
                try:
                    redis_client = get_redis()
                    cache_value = f"{row['id']}:{uname}"
                    await redis_client.setex(cache_key, 300, cache_value)  # TTL 5 минут
                except Exception as e:
                    print(f"Redis cache write error: {e}")
                return row["id"], uname

        # 2b) Назначение через роль в проекте
        if tb["role_id"]:
            uid = await conn.fetchval("""
                SELECT pm.user_id
                FROM core_projectmember pm
                JOIN core_tggroup g ON g.project_id = pm.project_id
                WHERE g.telegram_id = $1 AND pm.role_id = $2
                ORDER BY pm.id DESC LIMIT 1
            """, chat_id, tb["role_id"])
            if uid:
                row = await conn.fetchrow(
                    "SELECT id, username, telegram_id FROM core_user WHERE id = $1", uid
                )
                if row:
                    uname = row["username"] or f"id:{row['telegram_id']}"
                    # Сохраняем в кэш
                    try:
                        cache_value = f"{row['id']}:{uname}"
                        await redis_client.setex(cache_key, 300, cache_value)  # TTL 5 минут
                    except Exception as e:
                        print(f"Redis cache write error: {e}")
                    return row["id"], uname

        # 2c) Назначение через департамент (берем первого члена с is_lead или is_tech)
        if tb["department_id"]:
            # Сначала пробуем найти лида
            uid = await conn.fetchval("""
                SELECT dm.user_id
                FROM core_departmentmember dm
                WHERE dm.department_id = $1 AND dm.is_lead = TRUE
                ORDER BY dm.order_index, dm.id
                LIMIT 1
            """, tb["department_id"])
            
            # Если лида нет, ищем техлида
            if not uid:
                uid = await conn.fetchval("""
                    SELECT dm.user_id
                    FROM core_departmentmember dm
                    WHERE dm.department_id = $1 AND dm.is_tech = TRUE
                    ORDER BY dm.order_index, dm.id
                    LIMIT 1
                """, tb["department_id"])
            
            # Если и техлида нет, берем первого участника
            if not uid:
                uid = await conn.fetchval("""
                    SELECT dm.user_id
                    FROM core_departmentmember dm
                    WHERE dm.department_id = $1
                    ORDER BY dm.order_index, dm.id
                    LIMIT 1
                """, tb["department_id"])
            
            if uid:
                row = await conn.fetchrow(
                    "SELECT id, username, telegram_id FROM core_user WHERE id = $1", uid
                )
                if row:
                    uname = row["username"] or f"id:{row['telegram_id']}"
                    # Сохраняем в кэш
                    try:
                        cache_value = f"{row['id']}:{uname}"
                        await redis_client.setex(cache_key, 300, cache_value)  # TTL 5 минут
                    except Exception as e:
                        print(f"Redis cache write error: {e}")
                    return row["id"], uname

    # Сохраняем результат в кэш (даже если None)
    try:
        redis_client = get_redis()
        cache_value = f"{None}:{None}"
        await redis_client.setex(cache_key, 300, cache_value)  # TTL 5 минут
    except Exception as e:
        print(f"Redis cache write error: {e}")
    
    return None, None

# === /start (smoke test #1) ============================================
@dp.message(Command("start", ignore_mention=True))
async def start(msg: Message):
    await log_raw_update(msg)
    await safe_reply(msg, "✅ Бот на связи. Доступно: /whoami, /ping, /checklast N, /syncmembers")

# === /syncmembers - синхронизация участников группы ===================
@dp.message(Command("syncmembers", ignore_mention=True))
async def sync_members(msg: Message):
    """Синхронизация участников группы с ProjectMember"""
    await log_raw_update(msg)
    
    if msg.chat.type == "private":
        await safe_reply(msg, "Эта команда работает только в группах")
        return
    
    try:
        # Проверяем права администратора
        member = await bot.get_chat_member(msg.chat.id, msg.from_user.id)
        if member.status not in ["creator", "administrator"]:
            await safe_reply(msg, "Только администраторы могут синхронизировать участников")
            return
        
        conn = await get_conn()
        
        # Получаем группу и проект
        group = await conn.fetchrow(
            "SELECT id, project_id FROM core_tggroup WHERE telegram_id = $1",
            msg.chat.id
        )
        if not group or not group["project_id"]:
            await safe_reply(msg, "Группа не привязана к проекту")
            await conn.close()
            return
        
        # Получаем роль по умолчанию
        default_role = await conn.fetchrow(
            "SELECT id FROM core_role WHERE name ILIKE 'Member' LIMIT 1"
        )
        if not default_role:
            default_role = await conn.fetchrow(
                "INSERT INTO core_role (name, can_assign, can_close) VALUES ('Member', false, false) RETURNING id"
            )
        role_id = default_role["id"]
        
        # Получаем администраторов группы (обычных участников API не дает)
        created_count = 0
        updated_count = 0
        
        try:
            # Пробуем получить администраторов
            admins = await bot.get_chat_administrators(msg.chat.id)
            
            for admin in admins:
                if admin.user.is_bot:
                    continue
                    
                # Создаем или обновляем пользователя
                user = await conn.fetchrow(
                    """
                    INSERT INTO core_user (telegram_id, username, first_name, last_name, status, created_at)
                    VALUES ($1, $2, $3, $4, 'active', NOW())
                    ON CONFLICT (telegram_id) DO UPDATE
                    SET username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name
                    RETURNING id
                    """,
                    admin.user.id,
                    admin.user.username or "",
                    admin.user.first_name or "",
                    admin.user.last_name or ""
                )
                
                # Добавляем в ProjectMember
                result = await conn.fetchrow(
                    """
                    INSERT INTO core_projectmember (project_id, user_id, role_id, created_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (project_id, user_id, role_id) 
                    WHERE department_id IS NULL
                    DO NOTHING
                    RETURNING id
                    """,
                    group["project_id"],
                    user["id"],
                    role_id
                )
                
                if result:
                    created_count += 1
                else:
                    updated_count += 1
                    
        except Exception as e:
            # Если не можем получить администраторов, используем raw_updates
            users_from_logs = await conn.fetch(
                """
                SELECT DISTINCT u.id, u.telegram_id, u.username, u.first_name, u.last_name
                FROM raw_updates ru
                JOIN core_user u ON u.telegram_id = ru.user_id
                WHERE ru.chat_id = $1
                  AND ru.user_id IS NOT NULL
                LIMIT 100
                """,
                msg.chat.id
            )
            
            for user in users_from_logs:
                result = await conn.fetchrow(
                    """
                    INSERT INTO core_projectmember (project_id, user_id, role_id, created_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (project_id, user_id, role_id)
                    WHERE department_id IS NULL
                    DO NOTHING
                    RETURNING id
                    """,
                    group["project_id"],
                    user["id"],
                    role_id
                )
                
                if result:
                    created_count += 1
                else:
                    updated_count += 1
        
        await conn.close()
        
        await safe_reply(
            msg,
            f"✅ Синхронизация завершена\n"
            f"Добавлено новых участников: {created_count}\n"
            f"Уже были в проекте: {updated_count}"
        )
        
    except Exception as e:
        await safe_reply(msg, f"❌ Ошибка синхронизации: {str(e)[:200]}")

# === /whoami (always replies) =========================================
@dp.message(Command("whoami", ignore_mention=True))
async def whoami(msg: Message):
    await log_raw_update(msg)
    me = await bot.get_me()
    text = (
        f"bot=@{me.username} id={me.id}\n"
        f"chat_id={msg.chat.id}\n"
        f"from_id={(msg.from_user.id if msg.from_user else 'None')}"
    )
    await msg.reply(text)

# === simple /ping ======================================================
@dp.message(Command("ping", ignore_mention=True))
async def ping(msg: Message):
    await log_raw_update(msg)
    await safe_reply(msg, "pong")

# === /newrole Name [can_assign] [can_close] ============================
@dp.message(Command("newrole", ignore_mention=True))
async def new_role(msg: Message, command: CommandObject):
    await log_raw_update(msg)
    if not command.args:
        return await safe_reply(msg, "Usage: /newrole Name [can_assign] [can_close]")
    parts = command.args.strip().split()
    name = parts[0]
    flags = set(p.lower() for p in parts[1:])
    can_assign = "can_assign" in flags
    can_close = "can_close" in flags

    conn = await get_conn()
    await conn.execute(
        """
        INSERT INTO core_role (name, can_assign, can_close)
        VALUES ($1, $2, $3)
        ON CONFLICT (name)
        DO UPDATE SET can_assign = EXCLUDED.can_assign, can_close = EXCLUDED.can_close
        """,
        name,
        can_assign,
        can_close,
    )
    await conn.close()
    await safe_reply(msg, f"✅ Роль {name} создана (assign={can_assign}, close={can_close})")

# === /setrole @user RoleName | id:123456789 RoleName | reply + RoleName ===
@dp.message(Command("setrole", ignore_mention=True))
async def set_role(msg: Message, command: CommandObject):
    await log_raw_update(msg)
    if not command.args:
        return await safe_reply(msg, "Usage: /setrole [@user|id:123456789] RoleName (или reply на сообщение)")
    
    try:
        conn = await get_conn()
        async with conn.transaction():
            # Проект из текущего чата
            project_id = await conn.fetchval(
                "SELECT project_id FROM core_tggroup WHERE telegram_id = $1",
                msg.chat.id
            )
            if not project_id:
                await conn.close()
                return await safe_reply(
                    msg,
                    "⚠️ Чат не привязан к проекту. Используйте /setproject <Name>"
                )
            
            parts = command.args.split()
            tg_id = None
            role_name = None
            
            # Если есть reply - берем пользователя из него
            if msg.reply_to_message and msg.reply_to_message.from_user:
                if msg.reply_to_message.from_user.is_bot:
                    return await safe_reply(msg, "⚠️ Нельзя назначить роль боту")
                tg_id = msg.reply_to_message.from_user.id
                role_name = parts[0] if parts else None
            # Иначе парсим аргументы
            elif len(parts) >= 2:
                user_arg = parts[0]
                role_name = parts[1]
                
                if user_arg.startswith("id:"):
                    # Формат id:123456789
                    try:
                        tg_id = int(user_arg[3:])
                    except ValueError:
                        return await safe_reply(msg, "⚠️ Неверный формат ID")
                else:
                    # Формат @username
                    username = user_arg.lstrip("@").lower()
                    user_row = await conn.fetchrow(
                        "SELECT telegram_id FROM core_user WHERE LOWER(username) = $1",
                        username
                    )
                    if not user_row:
                        return await safe_reply(msg, f"⚠️ Пользователь @{username} не найден. Он должен сначала написать боту.")
                    tg_id = user_row["telegram_id"]
            else:
                return await safe_reply(msg, "⚠️ Укажите пользователя и роль")
            
            if not role_name:
                return await safe_reply(msg, "⚠️ Укажите название роли")
            
            # Проверяем/создаем пользователя
            user_id = await conn.fetchval(
                "SELECT id FROM core_user WHERE telegram_id = $1",
                tg_id
            )
            if not user_id:
                # Создаем пользователя по telegram_id
                user_id = await conn.fetchval(
                    """
                    INSERT INTO core_user (telegram_id, username, first_name, last_name, status, created_at)
                    VALUES ($1, '', '', '', 'active', NOW())
                    RETURNING id
                    """,
                    tg_id
                )
            
            # Проверяем роль
            role_id = await conn.fetchval("SELECT id FROM core_role WHERE name = $1", role_name)
            if not role_id:
                return await safe_reply(msg, f"⚠️ Роль '{role_name}' не найдена. Создайте: /newrole {role_name}")
            
            # Назначаем роль
            await conn.execute(
                """
                INSERT INTO core_projectmember (user_id, project_id, role_id, created_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id, project_id) DO UPDATE SET role_id = EXCLUDED.role_id
                """,
                user_id,
                project_id,
                role_id,
            )
        
        await conn.close()
        await safe_reply(msg, f"✅ Роль '{role_name}' назначена")
        
    except Exception as e:
        await safe_reply(msg, f"⚠️ Ошибка: {str(e)[:200]}")

# === /setproject <Name> - привязка чата к проекту ======================
@dp.message(Command("setproject", ignore_mention=True))
async def setproject(msg: Message, command: CommandObject):
    await log_raw_update(msg)
    name = (command.args or "").strip()
    if not name:
        return await safe_reply(msg, "Usage: /setproject <ProjectName>")
    
    try:
        conn = await get_conn()
        async with conn.transaction():
            # Создаем или находим проект
            project_id = await conn.fetchval(
                """INSERT INTO core_project (name, status, created_at) 
                VALUES ($1, 'active', NOW()) 
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name 
                RETURNING id""",
                name
            )
            
            # Обновляем привязку группы к проекту
            await conn.execute(
                "UPDATE core_tggroup SET project_id = $1 WHERE telegram_id = $2",
                project_id, 
                msg.chat.id
            )
        
        await conn.close()
        await safe_reply(msg, f"✅ Проект чата: {name}")
        
    except Exception as e:
        await safe_reply(msg, f"⚠️ Ошибка: {str(e)[:200]}")

# === /newtask @user text [YYYY-MM-DD] ==================================
@dp.message(Command("newtask", ignore_mention=True))
async def new_task(msg: Message, command: CommandObject):
    await log_raw_update(msg)
    if not await _require_can_assign_msg(msg):
        return
    if not command.args:
        return await safe_reply(msg, "Usage: /newtask [@user] text [YYYY-MM-DD]")
    
    try:
        conn = await get_conn()
        parts = command.args.split()
        
        # Определяем явного исполнителя и текст
        explicit_username = None
        if parts[0].startswith("@"):
            explicit_username = parts[0].lstrip("@")
            text_parts = parts[1:]
        else:
            text_parts = parts
        
        # Парсим дедлайн с помощью новой утилиты
        deadline = None
        text = None
        
        # Проверяем различные варианты дедлайна в конце
        for i in range(len(text_parts)):
            potential_deadline_str = " ".join(text_parts[-(i+1):])
            potential_deadline = parse_deadline(potential_deadline_str, TIMEZONE)
            if potential_deadline:
                deadline = potential_deadline
                text = " ".join(text_parts[:-(i+1)])
                break
        
        # Если дедлайн не найден, весь текст - это задача
        if not text:
            text = " ".join(text_parts) if text_parts else "Задача"
        
        # Если дедлайн не указан, показываем календарь
        if not deadline:
            # Сохраняем данные в Redis
            r = get_redis()
            task_data = {
                "text": text,
                "responsible_username": explicit_username,
                "topic_id": topic_id,
                "message_id": msg.message_id
            }
            await r.set(
                f"newtask:{msg.chat.id}:{msg.from_user.id}",
                json.dumps(task_data),
                ex=1200  # 20 минут
            )
            await conn.close()
            
            # Показываем календарь
            tz = ZoneInfo(TIMEZONE)
            now = datetime.datetime.now(tz)
            kb = build_calendar_kb(now)
            return await safe_reply(
                msg,
                f"📅 Выберите дату дедлайна для задачи:\n<b>{text[:100]}</b>",
                reply_markup=kb
            )
        
        # Резолвим ответственного
        topic_id = getattr(msg, "message_thread_id", None)
        resp_user_id, resp_username = await _resolve_responsible(
            conn, msg.chat.id, topic_id, explicit_username
        )
        
        if not resp_user_id and not resp_username:
            await conn.close()
            return await safe_reply(
                msg, 
                "⚠️ Не удалось определить ответственного. Укажите @username или настройте /topicrole"
            )
        
        # Получаем автора и проект
        author_id = await conn.fetchval(
            "SELECT id FROM core_user WHERE telegram_id = $1", 
            msg.from_user.id
        )
        project_id = await conn.fetchval(
            "SELECT project_id FROM core_tggroup WHERE telegram_id = $1", 
            msg.chat.id
        )
        
        # Создаем задачу
        result = await conn.fetchval(
            """
            INSERT INTO core_task (
                title, description, responsible_user_id, responsible_username,
                author_user_id, project_id, deadline,
                status, created_at, updated_at,
                source_chat_id, source_message_id, source_topic_id
            )
            VALUES ($1::varchar, $2::text, $3, $4::varchar, $5, $6, $7::timestamp with time zone, 
                    'TODO', NOW(), NOW(), $8, $9, $10)
            RETURNING id
            """,
            text[:256],
            text,
            resp_user_id,
            resp_username or "unknown",
            author_id,
            project_id,
            deadline,
            msg.chat.id,
            msg.message_id,
            topic_id,
        )
        
        await conn.close()
        response_text = format_task_created_response(1, [result] if result else None)
        await safe_reply(msg, response_text)
        
    except Exception as e:
        await safe_reply(msg, f"⚠️ Ошибка: {str(e)[:200]}")

# === /add (ответ на сообщение) ==========================================
@dp.message(Command("add", ignore_mention=True))
async def add_task(msg: Message, command: CommandObject):
    """Создание задачи из сообщения (reply)"""
    await log_raw_update(msg)
    
    if not await _require_can_assign_msg(msg):
        return
    
    if not msg.reply_to_message:
        return await safe_reply(msg, "Ответьте на сообщение для создания задачи")
    
    import re
    import logging
    logger = logging.getLogger(__name__)
    
    # Извлекаем текст из сообщения
    base = msg.reply_to_message.text or msg.reply_to_message.caption or ""
    extra = (command.args or "").strip()
    
    # Вытащить @username из extra (и не мешать парсеру даты)
    m = re.search(r'@([A-Za-z0-9_]{5,})', extra)
    extracted_username_or_none = f"{m.group(1)}" if m else None
    extra_wo_user = re.sub(r'@([A-Za-z0-9_]{5,})', '', extra).strip()
    
    title = (base + (" — " + extra_wo_user if extra_wo_user else "")).strip()
    if not title:
        title = "Задача из сообщения"
    
    # Пробуем распарсить дедлайн из аргументов
    deadline = parse_deadline(extra_wo_user, TIMEZONE) if extra_wo_user else None
    
    logger.info("ADD: reply mid=%s, args=%r", msg.reply_to_message.message_id if msg.reply_to_message else None, command.args)
    
    if deadline:
        # Если дедлайн указан - создаем задачу сразу
        logger.info("ADD: create with deadline=%s", deadline)
        conn = await get_conn()
        try:
            # Резолвим ответственного
            topic_id = getattr(msg, "message_thread_id", None)
            resp_user_id, resp_username = await _resolve_responsible(
                conn, msg.chat.id, topic_id, extracted_username_or_none
            )
            
            if not resp_user_id and not resp_username:
                # Мягкий фолбэк
                resp_username = extracted_username_or_none or (msg.from_user.username or "unknown")
            
            # Получаем автора и проект
            author_id = await conn.fetchval(
                "SELECT id FROM core_user WHERE telegram_id = $1", 
                msg.from_user.id
            )
            project_id = await conn.fetchval(
                "SELECT project_id FROM core_tggroup WHERE telegram_id = $1", 
                msg.chat.id
            )
            
            # Создаем задачу
            result = await conn.fetchval(
                """
                INSERT INTO core_task (
                    title, description, responsible_user_id, responsible_username,
                    author_user_id, project_id, deadline,
                    status, created_at, updated_at,
                    source_chat_id, source_message_id, source_topic_id
                )
                VALUES ($1::varchar, $2::text, $3, $4::varchar, $5, $6, $7::timestamp with time zone, 
                        'TODO', NOW(), NOW(), $8, $9, $10)
                RETURNING id
                """,
                title[:256],
                title,
                resp_user_id,
                resp_username or "unknown",
                author_id,
                project_id,
                deadline,
                msg.chat.id,
                msg.reply_to_message.message_id,
                topic_id,
            )
            
            response_text = format_task_created_response(1, [result] if result else None)
            await safe_reply(msg, response_text)
        finally:
            await conn.close()
    else:
        # ПОДГОТОВИТЬ КАЛЕНДАРЬ ДЛЯ /add БЕЗ ДАТЫ
        r = get_redis()
        key = f"newtask:{msg.chat.id}:{msg.from_user.id}"
        
        task_data = {
            "text": title,  # текст из reply + args
            "message_id": msg.reply_to_message.message_id,
            "topic_id": msg.message_thread_id,  # если есть топики
            "responsible_username": extracted_username_or_none,  # если @юзер был в args
        }
        await r.set(key, json.dumps(task_data), ex=1200)
        logger.info("ADD: state saved to redis key=%s", key)
        
        # показать календарь
        today = datetime.datetime.now(ZoneInfo(TIMEZONE)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        kb = build_calendar_kb(today)
        await msg.answer(f"📅 Выберите дату дедлайна:\n<b>{_quote(title, 100)}</b>", reply_markup=kb)

# === /closetask #ID =====================================================
@dp.message(Command("closetask", ignore_mention=True))
async def close_task(msg: Message, command: CommandObject):
    await log_raw_update(msg)
    if not await _require_can_close_msg(msg):
        return
    if not command.args or not command.args.lstrip("#").isdigit():
        return await safe_reply(msg, "Usage: /closetask #123")
    task_id = int(command.args.lstrip("#"))
    conn = await get_conn()
    updated = await conn.execute(
        "UPDATE core_task SET status='DONE', updated_at = NOW() WHERE id=$1", task_id
    )
    await conn.close()
    if updated.endswith("0"):
        await safe_reply(msg, "Не найдено")
    else:
        await safe_reply(msg, f"✅ Task #{task_id} закрыта")

# === /topicrole - привязка топика к пользователю/роли/департаменту ======
@dp.message(Command("topicrole", ignore_mention=True))
async def topicrole_cmd(msg: Message, command: CommandObject):
    await log_raw_update(msg)
    if not await _require_can_assign_msg(msg):
        return
    
    # проверка, что команда вызвана в топике
    topic_id = getattr(msg, "message_thread_id", None)
    if not topic_id:
        return await safe_reply(msg, "⚠️ Команда работает только в топиках")
    
    # проверка, что группа привязана к проекту
    project_id = await _get_project_id_by_chat(msg.chat.id)
    if not project_id:
        return await safe_reply(msg, "⚠️ Группа не привязана к проекту")
    
    if not command.args:
        return await safe_reply(msg, "Usage: /topicrole @user | role RoleName | dept DepartmentName")
    
    args = command.args.strip()
    conn = await get_conn()
    
    try:
        # получаем group_id для TgGroup
        group_row = await conn.fetchrow(
            "SELECT id FROM core_tggroup WHERE telegram_id = $1", msg.chat.id
        )
        if not group_row:
            return await safe_reply(msg, "⚠️ Группа не найдена в базе")
        group_id = group_row["id"]
        
        # Убедимся, что топик существует в core_forumtopic
        await _touch_topic_title(msg.chat.id, topic_id, None)
        
        # Получаем forum_topic.id
        topic_row = await conn.fetchrow("""
            SELECT ft.id
            FROM core_forumtopic ft
            WHERE ft.group_id = $1 AND ft.topic_id = $2
            LIMIT 1
        """, group_id, topic_id)
        
        if not topic_row:
            return await safe_reply(msg, "⚠️ Не удалось создать запись топика")
        
        forum_topic_id = topic_row["id"]
        
        # парсим аргументы команды
        if args.startswith("@"):
            # /topicrole @user
            username = args[1:].lower()
            user_row = await conn.fetchrow(
                "SELECT id FROM core_user WHERE LOWER(username) = $1", username
            )
            if not user_row:
                return await safe_reply(msg, f"⚠️ Пользователь @{username} не найден")
            
            await conn.execute("""
                INSERT INTO core_topicbinding (topic_id, priority, user_id, role_id, department_id)
                VALUES ($1, 1, $2, NULL, NULL)
                ON CONFLICT (topic_id, priority)
                DO UPDATE SET user_id = EXCLUDED.user_id, role_id = NULL, department_id = NULL
            """, forum_topic_id, user_row["id"])
            
            await safe_reply(msg, f"✅ Топик привязан к @{username}")
            
        elif args.startswith("role "):
            # /topicrole role RoleName
            role_name = args[5:].strip()
            role_row = await conn.fetchrow(
                "SELECT id FROM core_role WHERE name = $1", role_name
            )
            if not role_row:
                return await safe_reply(msg, f"⚠️ Роль '{role_name}' не найдена")
            
            await conn.execute("""
                INSERT INTO core_topicbinding (topic_id, priority, role_id, user_id, department_id)
                VALUES ($1, 1, $2, NULL, NULL)
                ON CONFLICT (topic_id, priority)
                DO UPDATE SET role_id = EXCLUDED.role_id, user_id = NULL, department_id = NULL
            """, forum_topic_id, role_row["id"])
            
            await safe_reply(msg, f"✅ Топик привязан к роли '{role_name}'")
            
        elif args.startswith("dept "):
            # /topicrole dept DepartmentName
            dept_name = args[5:].strip()
            dept_row = await conn.fetchrow(
                "SELECT id FROM core_department WHERE name = $1 AND project_id = $2", 
                dept_name, project_id
            )
            if not dept_row:
                return await safe_reply(msg, f"⚠️ Департамент '{dept_name}' не найден в проекте")
            
            await conn.execute("""
                INSERT INTO core_topicbinding (topic_id, priority, department_id, user_id, role_id)
                VALUES ($1, 1, $2, NULL, NULL)
                ON CONFLICT (topic_id, priority)
                DO UPDATE SET department_id = EXCLUDED.department_id, user_id = NULL, role_id = NULL
            """, forum_topic_id, dept_row["id"])
            
            await safe_reply(msg, f"✅ Топик привязан к департаменту '{dept_name}'")
            
        else:
            await safe_reply(msg, "Usage: /topicrole @user | role RoleName | dept DepartmentName")
            
    except Exception as e:
        await safe_reply(msg, f"⚠️ Ошибка: {str(e)[:200]}")
    finally:
        await conn.close()

# === /assigntopic - alias для /topicrole (соответствие чек-листам S1) ===
@dp.message(Command("assigntopic", ignore_mention=True))
async def assigntopic_cmd(msg: Message, command: CommandObject):
    """Alias для /topicrole для соответствия чек-листам"""
    # Проксируем в существующую команду topicrole
    await topicrole_cmd(msg, command)

# === Helper для обновления названия топика ==============================
async def _touch_topic_title(chat_id: int, topic_id: int | None, title: str | None):
    """Обновляет или создаёт топик с названием"""
    if topic_id is None:
        return
    conn = await get_conn()
    try:
        await conn.execute("""
            INSERT INTO core_forumtopic (group_id, topic_id, title, first_seen, last_seen, message_count)
            SELECT g.id, $2, COALESCE($3,''), NOW(), NOW(), 0
            FROM core_tggroup g WHERE g.telegram_id = $1
            ON CONFLICT (group_id, topic_id) DO UPDATE
               SET title = CASE 
                             WHEN $3 IS NOT NULL AND $3 <> '' THEN $3
                             ELSE core_forumtopic.title
                           END,
                   last_seen = NOW()
        """, chat_id, topic_id, (title or "")[:256])
    except Exception as e:
        print(f"TOPIC_TITLE_UPDATE_WARN: {e}")
    finally:
        await conn.close()

# === Обработчики сервисных сообщений о топиках ==========================
@dp.message(F.forum_topic_created)
async def on_topic_created(msg: Message):
    """Обработка создания нового топика"""
    await log_raw_update(msg)
    if msg.message_thread_id is not None and msg.forum_topic_created:
        await _touch_topic_title(
            msg.chat.id, 
            msg.message_thread_id,
            msg.forum_topic_created.name
        )

@dp.message(F.forum_topic_edited)
async def on_topic_edited(msg: Message):
    """Обработка изменения топика"""
    await log_raw_update(msg)
    if msg.message_thread_id is not None and msg.forum_topic_edited:
        await _touch_topic_title(
            msg.chat.id,
            msg.message_thread_id, 
            msg.forum_topic_edited.name
        )

@dp.message(F.general_forum_topic_hidden | F.general_forum_topic_unhidden)
async def on_general_topic_toggle(msg: Message):
    """Обработка скрытия/показа General топика"""
    await log_raw_update(msg)
    # General: если Telegram пришлёт thread id → используем его; если нет — пишем 0
    tid = getattr(msg, "message_thread_id", None)
    await _touch_topic_title(msg.chat.id, int(tid) if tid is not None else 0, "General")

@dp.message(F.text & ~F.text.startswith("/"))
async def catch_all(msg: Message):
    await log_raw_update(msg)
    # DEBUG: временное логирование для проверки топиков
    print(f"DBG topic: is_topic={getattr(msg,'is_topic_message',None)} "
          f"thread_id={getattr(msg,'message_thread_id',None)} "
          f"svc_created={bool(getattr(msg,'forum_topic_created',None))} "
          f"svc_edited={bool(getattr(msg,'forum_topic_edited',None))}")
    if not SHADOW_MODE:
        pass

# === /checklast (lite) ====================================================
async def _do_checklast(msg: Message, n=None):
    max_n = n or int(os.getenv("CHECKLAST_MAX", "20"))
    topic_id = getattr(msg, "message_thread_id", None)
    print(f"[CHECKLAST] chat={msg.chat.id} topic={topic_id} n={max_n}")
    rows = await fetch_raw_updates_for_chat(msg.chat.id, topic_id, max_n)
    rows = list(reversed(rows))
    if not rows:
        await msg.answer("Нет сообщений в журнале")
        return
    
    r = get_redis()
    
    # формируем "тонкие" данные с фиксированным порядком
    slim = []
    for idx, x in enumerate(rows, start=1):
        slim.append({
            "idx": idx,
            "message_id": int(x["id"]),
            "text": x["text"],
            "topic_id": x.get("topic_id"),
        })
    
    await r.set(_cl_rows_key(msg.chat.id, msg.from_user.id),
                json.dumps(slim), ex=1200)
    await r.delete(_cl_sel_key(msg.chat.id, msg.from_user.id))
    
    kb = build_checklast_kb(slim, set())
    await msg.answer("Выберите сообщения для задач:", reply_markup=kb)

@dp.message(Command("checklast", ignore_mention=True))
async def checklast_command(msg: Message, command: CommandObject):
    await log_raw_update(msg)
    n = None
    if command.args and command.args.strip().isdigit():
        n = int(command.args.strip())
    await _do_checklast(msg, n)

@dp.message(Command("debug_chat"))
async def debug_chat(msg: Message):
    """Проверка прав бота и статуса группы"""
    await log_raw_update(msg)
    chat = await bot.get_chat(msg.chat.id)
    me = await bot.get_me()
    member = await bot.get_chat_member(msg.chat.id, me.id)
    
    # Проверяем права
    can_manage = False
    if hasattr(member, 'can_manage_topics'):
        if hasattr(member.can_manage_topics, '__bool__'):
            can_manage = bool(member.can_manage_topics)
        else:
            can_manage = member.can_manage_topics
    
    debug_info = (
        f"DBG_CHAT: "
        f"type={chat.type} "
        f"is_forum={getattr(chat,'is_forum',None)} "
        f"bot_admin={(member.status in ('administrator','creator'))} "
        f"can_manage_topics={can_manage}"
    )
    print(debug_info)
    await safe_reply(msg, f"✅ Debug info:\n{debug_info}")


@dp.callback_query(F.data.startswith("cl:toggle:"))
async def checklast_toggle(cb: CallbackQuery):
    """Обработчик переключения выбора сообщения"""
    _, _, raw_id = cb.data.partition(":toggle:")
    rows_key = _cl_rows_key(cb.message.chat.id, cb.from_user.id)
    sel_key = _cl_sel_key(cb.message.chat.id, cb.from_user.id)
    
    r = get_redis()
    exists = await r.sismember(sel_key, raw_id)
    if exists:
        await r.srem(sel_key, raw_id)
    else:
        await r.sadd(sel_key, raw_id)
        await r.expire(sel_key, 1200)  # 20 минут
    
    # Обновляем клавиатуру
    raw_rows = await r.get(rows_key)
    if raw_rows:
        rows = json.loads(raw_rows)
        selected = await r.smembers(sel_key)
        selected_ids = set(map(int, selected)) if selected else set()
        kb = build_checklast_kb(rows, selected_ids)
        try:
            await cb.message.edit_reply_markup(reply_markup=kb)
        except:
            pass
    await cb.answer()

@dp.callback_query(F.data == "cl:reset")
async def checklast_reset(cb: CallbackQuery):
    """Обработчик сброса выбора"""
    rows_key = _cl_rows_key(cb.message.chat.id, cb.from_user.id)
    sel_key = _cl_sel_key(cb.message.chat.id, cb.from_user.id)
    
    r = get_redis()
    await r.delete(sel_key)
    
    # Обновляем клавиатуру
    raw_rows = await r.get(rows_key)
    if raw_rows:
        rows = json.loads(raw_rows)
        kb = build_checklast_kb(rows, set())
        try:
            await cb.message.edit_reply_markup(reply_markup=kb)
        except:
            pass
    await cb.answer("Выбор сброшен")

@dp.callback_query(F.data == "cl:cancel")
async def checklast_cancel(cb: CallbackQuery):
    """Обработчик отмены операции"""
    rows_key = _cl_rows_key(cb.message.chat.id, cb.from_user.id)
    sel_key = _cl_sel_key(cb.message.chat.id, cb.from_user.id)
    
    r = get_redis()
    await r.delete(rows_key)
    await r.delete(sel_key)
    
    try:
        await cb.message.delete()
    except:
        pass
    await cb.answer("Отменено")

@dp.callback_query(F.data == "cl:create")
async def checklast_create(cb: CallbackQuery):
    if not await _require_can_assign_cb(cb):
        return
    
    chat_id = cb.message.chat.id
    user_id = cb.from_user.id
    rows_key = _cl_rows_key(chat_id, user_id)
    sel_key = _cl_sel_key(chat_id, user_id)
    r = get_redis()
    
    # Получаем выбранные ID
    raw_ids = await r.smembers(sel_key)
    selected_ids = set(map(int, raw_ids)) if raw_ids else set()
    if not selected_ids:
        await cb.answer("Не выбрано ни одного сообщения", show_alert=True)
        return
    
    # Получаем данные из Redis
    raw_rows = await r.get(rows_key)
    rows = json.loads(raw_rows) if raw_rows else []
    
    # берём только выбранные, в исходном порядке (по idx)
    ordered = [rd for rd in rows if int(rd["message_id"]) in selected_ids]
    ordered.sort(key=lambda rd: rd.get("idx", 0))
    
    created_titles = []
    conn = await get_conn()
    try:
        # Получаем автора и проект один раз
        author_id = await conn.fetchval(
            "SELECT id FROM core_user WHERE telegram_id = $1", 
            user_id
        )
        project_id = await conn.fetchval(
            "SELECT project_id FROM core_tggroup WHERE telegram_id = $1", 
            chat_id
        )
        
        for rd in ordered:
            resp_user_id, resp_username = await _resolve_responsible(
                conn, chat_id, rd.get("topic_id"), None
            )
            task_id = await _create_task_minimal(
                title=_quote(rd["text"], 160),
                description=rd["text"],
                responsible_user_id=resp_user_id,
                responsible_username=resp_username,
                author_user_id=author_id,
                project_id=project_id,
                source_chat_id=chat_id,
                source_message_id=int(rd["message_id"]),
                source_topic_id=rd.get("topic_id"),
            )
            if task_id:
                created_titles.append(_quote(rd["text"], 60))
    finally:
        await conn.close()
    
    # вывод — без ID, только цитаты
    if len(created_titles) == 1:
        text = f"📌 Задача создана:\n1) «{created_titles[0]}»"
    elif created_titles:
        items = "\n".join(f"{i+1}) «{t}»" for i, t in enumerate(created_titles))
        text = f"✅ Создано задач: {len(created_titles)}\n\nЦитаты из чата:\n{items}"
    else:
        text = "❌ Задачи не созданы"
    
    await cb.message.answer(text)
    
    # очистка состояния и закрытие меню
    await r.delete(sel_key)
    await r.delete(rows_key)
    try:
        await cb.message.delete()
    except:
        pass

# === Обработчики календаря ===============================================
@dp.callback_query(F.data.startswith("cal:"))
async def calendar_callback(cb: CallbackQuery):
    """Обработчик выбора даты в календаре"""
    data = cb.data
    
    if data == "cal:cancel":
        # Отмена выбора
        r = get_redis()
        await r.delete(f"newtask:{cb.message.chat.id}:{cb.from_user.id}")
        await cb.message.delete()
        await cb.answer("Отменено")
        return
    
    if data == "cal:ignore":
        # Игнорируемые кнопки
        await cb.answer()
        return
    
    if data.startswith("cal:prev:") or data.startswith("cal:next:"):
        # Навигация по месяцам
        _, action, year_month = data.split(":")
        year, month = map(int, year_month.split("-"))
        
        if action == "prev":
            month -= 1
            if month < 1:
                month = 12
                year -= 1
        else:  # next
            month += 1
            if month > 12:
                month = 1
                year += 1
        
        # Создаем новый календарь
        tz = ZoneInfo(TIMEZONE)
        new_date = datetime.datetime(year, month, 1, tzinfo=tz)
        kb = build_calendar_kb(new_date)
        
        try:
            await cb.message.edit_reply_markup(reply_markup=kb)
        except:
            pass
        await cb.answer()
        return
    
    # Выбрана конкретная дата
    if data.startswith("cal:"):
        date_str = data[4:]  # Убираем "cal:"
        
        # Сохраняем выбранную дату в Redis
        r = get_redis()
        key = f"newtask:{cb.message.chat.id}:{cb.from_user.id}"
        task_data_raw = await r.get(key)
        if not task_data_raw:
            await cb.message.delete()
            await cb.answer("Сессия истекла, начните заново")
            return
        
        task_data = json.loads(task_data_raw)
        task_data["date"] = date_str
        await r.set(key, json.dumps(task_data), ex=1200)
        
        # Показываем выбор времени
        kb = build_time_kb(30)
        await cb.message.edit_text(
            f"🕐 Выберите время дедлайна для {date_str}:\n<b>{task_data['text'][:100]}</b>",
            reply_markup=kb
        )
        await cb.answer()

@dp.callback_query(F.data.startswith("time:"))
async def time_callback(cb: CallbackQuery):
    """Обработчик выбора времени"""
    time_str = cb.data[5:]  # Убираем "time:"
    
    # Получаем данные из Redis
    r = get_redis()
    key = f"newtask:{cb.message.chat.id}:{cb.from_user.id}"
    task_data_raw = await r.get(key)
    if not task_data_raw:
        await cb.message.delete()
        await cb.answer("Сессия истекла, начните заново")
        return
    
    task_data = json.loads(task_data_raw)
    
    # Создаем полный дедлайн
    date_str = task_data.get("date", datetime.datetime.now().strftime("%Y-%m-%d"))
    deadline_str = f"{date_str} {time_str}"
    tz = ZoneInfo(TIMEZONE)
    deadline = datetime.datetime.strptime(deadline_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    
    # Создаем задачу
    conn = await get_conn()
    try:
        # Резолвим ответственного
        resp_user_id, resp_username = await _resolve_responsible(
            conn, cb.message.chat.id, task_data.get("topic_id"), 
            task_data.get("responsible_username")
        )
        
        if not resp_user_id and not resp_username:
            # мягкий фолбэк — пишем username инициатора либо "unknown"
            resp_username = task_data.get("responsible_username") or (cb.from_user.username or "unknown")
            # resp_user_id оставить None — в БД есть поле responsible_username
        
        # Получаем автора и проект
        author_id = await conn.fetchval(
            "SELECT id FROM core_user WHERE telegram_id = $1", 
            cb.from_user.id
        )
        project_id = await conn.fetchval(
            "SELECT project_id FROM core_tggroup WHERE telegram_id = $1", 
            cb.message.chat.id
        )
        
        # Создаем задачу
        text = task_data["text"]
        result = await conn.fetchval(
            """
            INSERT INTO core_task (
                title, description, responsible_user_id, responsible_username,
                author_user_id, project_id, deadline,
                status, created_at, updated_at,
                source_chat_id, source_message_id, source_topic_id
            )
            VALUES ($1::varchar, $2::text, $3, $4::varchar, $5, $6, $7::timestamp with time zone, 
                    'TODO', NOW(), NOW(), $8, $9, $10)
            RETURNING id
            """,
            text[:256],
            text,
            resp_user_id,
            resp_username or "unknown",
            author_id,
            project_id,
            deadline,
            cb.message.chat.id,
            task_data.get("message_id"),
            task_data.get("topic_id"),
        )
        
        # Удаляем данные из Redis
        await r.delete(key)
        
        # Отправляем ответ
        response_text = format_task_created_response(1, [result] if result else None)
        await cb.message.edit_text(response_text)
        
    finally:
        await conn.close()
    
    await cb.answer("Задача создана")

# === Обработчики редактирования сообщений ===============================
@dp.edited_message()
async def on_edited_message(msg: Message):
    """Обновляет текст в raw_updates при редактировании сообщения"""
    await _update_raw_on_edit(msg)

@dp.edited_channel_post()
async def on_edited_channel_post(msg: Message):
    """Обновляет текст в raw_updates при редактировании поста канала"""
    await _update_raw_on_edit(msg)


async def setup_bot_commands(bot: Bot):
    from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats
    private_cmds = [
        BotCommand(command="start", description="запустить бота"),
        BotCommand(command="ping", description="проверить связь"),
        BotCommand(command="whoami", description="инфо о чате/юзере"),
        BotCommand(command="newrole", description="создать роль"),
        BotCommand(command="setrole", description="назначить роль"),
        BotCommand(command="newtask", description="новая задача"),
        BotCommand(command="closetask", description="закрыть задачу"),
        BotCommand(command="checklast", description="последние N"),
        BotCommand(command="topicrole", description="привязка к топику"),
        BotCommand(command="assigntopic", description="alias topicrole"),
        BotCommand(command="add", description="задача из сообщения")
    ]
    group_cmds = [c for c in private_cmds if c.command not in ("newrole","setrole")]
    await bot.set_my_commands(private_cmds, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(group_cmds,   scope=BotCommandScopeAllGroupChats())

async def main():
    await ensure_schema()
    me = await bot.get_me()
    print(f"Starting bot @{me.username} id={me.id} SHADOW_MODE={SHADOW_MODE}")
    
    # Устанавливаем меню команд
    await setup_bot_commands(bot)
    print("Bot commands menu configured")
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("Webhook deleted (if existed), starting polling…")
    except Exception as e:
        print(f"Failed to delete webhook: {e}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())