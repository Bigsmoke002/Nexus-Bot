# database.py
import sqlite3
import datetime
import os

DB_FOLDER = "database"
DB_NAME = os.path.join(DB_FOLDER, "bot_main.db")

def init_db():
    os.makedirs(DB_FOLDER, exist_ok=True)
    with sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, guild_name TEXT NOT NULL,
                channel_id INTEGER NOT NULL, channel_name TEXT NOT NULL, author_id INTEGER NOT NULL,
                author_name TEXT NOT NULL, content TEXT, timestamp TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS event_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, source TEXT NOT NULL,
                level TEXT NOT NULL, message TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS web_plugin_permissions (
                guild_id INTEGER NOT NULL, plugin_name TEXT NOT NULL,
                entity_type TEXT NOT NULL, entity_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, plugin_name, entity_type, entity_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,
                created_at TEXT NOT NULL, expires_at TEXT NOT NULL
            )
        """)
        con.commit()
        print(f"INFO: Haupt-Datenbank unter {DB_NAME} erfolgreich initialisiert.")

def get_plugin_permissions(guild_id, plugin_name):
    with sqlite3.connect(DB_NAME) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        return cur.execute("SELECT * FROM web_plugin_permissions WHERE guild_id = ? AND plugin_name = ?", (guild_id, plugin_name)).fetchall()

def add_plugin_permission(guild_id, plugin_name, entity_type, entity_id):
    with sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        cur.execute("INSERT OR IGNORE INTO web_plugin_permissions (guild_id, plugin_name, entity_type, entity_id) VALUES (?, ?, ?, ?)",
                    (guild_id, plugin_name, entity_type, entity_id))
        con.commit()

def remove_plugin_permission(guild_id, plugin_name, entity_type, entity_id):
    with sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        cur.execute("DELETE FROM web_plugin_permissions WHERE guild_id = ? AND plugin_name = ? AND entity_type = ? AND entity_id = ?",
                    (guild_id, plugin_name, entity_type, entity_id))
        con.commit()

def check_user_permission_for_plugin(member, plugin_name):
    if member.guild_permissions.administrator:
        return True
    with sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        cur.execute("SELECT 1 FROM web_plugin_permissions WHERE guild_id = ? AND plugin_name = ? AND entity_type = 'user' AND entity_id = ?", (member.guild.id, plugin_name, member.id))
        if cur.fetchone():
            return True
        user_role_ids = {str(role.id) for role in member.roles}
        cur.execute("SELECT entity_id FROM web_plugin_permissions WHERE guild_id = ? AND plugin_name = ? AND entity_type = 'role'", (member.guild.id, plugin_name))
        allowed_roles = {str(row[0]) for row in cur.fetchall()}
        return not user_role_ids.isdisjoint(allowed_roles)

def create_auth_token(token, user_id, guild_id):
    created_at = datetime.datetime.utcnow()
    expires_at = created_at + datetime.timedelta(seconds=60)
    with sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        cur.execute("INSERT INTO auth_tokens (token, user_id, guild_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                    (token, user_id, guild_id, created_at.isoformat(), expires_at.isoformat()))
        con.commit()

def consume_auth_token(token):
    now = datetime.datetime.utcnow()
    with sqlite3.connect(DB_NAME) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        result = cur.execute("SELECT * FROM auth_tokens WHERE token = ? AND expires_at > ?", (token, now.isoformat())).fetchone()
        if result:
            cur.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
            con.commit()
            return dict(result)
    return None

def save_setting(key: str, value: str):
    with sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        cur.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, value))
        con.commit()

def get_setting(key: str, default: str = None) -> str:
    with sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        cur.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
        result = cur.fetchone()
        return result[0] if result else default

def log_event(source, level, message):
    timestamp = datetime.datetime.now().isoformat()
    with sqlite3.connect(DB_NAME) as con:
        cur = con.cursor()
        cur.execute("INSERT INTO event_logs (timestamp, source, level, message) VALUES (?, ?, ?, ?)", (timestamp, source, level, message))
        con.commit()

def get_recent_logs(limit=20):
    with sqlite3.connect(DB_NAME) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        logs = cur.execute("SELECT * FROM event_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return logs # KORREKTUR: Fehlendes return hinzugefügt

def get_messages_for_channel(channel_id, limit=100):
    with sqlite3.connect(DB_NAME) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        messages = cur.execute("SELECT * FROM messages WHERE channel_id = ? ORDER BY timestamp DESC LIMIT ?", (channel_id, limit)).fetchall()
        return messages # KORREKTUR: Fehlendes return hinzugefügt