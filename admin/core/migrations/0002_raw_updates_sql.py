from django.db import migrations

SQL_FWD = """
CREATE TABLE IF NOT EXISTS raw_updates (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    message_id BIGINT,
    user_id BIGINT,
    username VARCHAR(255),
    text TEXT DEFAULT '',
    topic_id BIGINT,
    payload JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_raw_chat_created ON raw_updates (chat_id, created_at);
CREATE INDEX IF NOT EXISTS idx_raw_chat_msg     ON raw_updates (chat_id, message_id);
CREATE INDEX IF NOT EXISTS idx_raw_created      ON raw_updates (created_at);
"""

SQL_BWD = """
DROP INDEX IF EXISTS idx_raw_created;
DROP INDEX IF EXISTS idx_raw_chat_msg;
DROP INDEX IF EXISTS idx_raw_chat_created;
/* Таблицу сознательно не удаляем — данные логов ценные */
"""

class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunSQL(sql=SQL_FWD, reverse_sql=SQL_BWD)]