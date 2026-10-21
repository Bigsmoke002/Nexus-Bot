# cogs/VoiceCreator/cog.py
import discord
from discord.ext import commands, tasks
import os
import sqlite3
import time
from datetime import datetime, timedelta

class VoiceCreator(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = "plugin_data/VoiceCreator/voicecreate.db"
        self.config_cache = {}
        self.init_db()
        self.bot.loop.create_task(self.load_config_to_cache())
        self.purge_messages_task.start()

    def cog_unload(self):
        self.purge_messages_task.cancel()

    # --- DATENBANK-VERWALTUNG ---
    def get_db_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self.get_db_connection() as con:
            cur = con.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS join_channels (
                    id TEXT PRIMARY KEY,
                    category_id TEXT NOT NULL,
                    channel_format TEXT DEFAULT '{username}''s Channel',
                    use_sequential BOOLEAN DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS created_channels (
                    channel_id TEXT PRIMARY KEY,
                    creator_id TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS message_delete_channels (
                    slot TEXT PRIMARY KEY,
                    channel_id TEXT,
                    minutes INTEGER
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_deletions (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    deletion_time INTEGER NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS warning_history (
                    channel_id TEXT PRIMARY KEY,
                    last_warning_time INTEGER NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS channel_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    format TEXT NOT NULL
                )
            """)
            # Standardwerte setzen
            defaults = {
                'deleteEmptyChannels': 'true', 'useSequentialNames': 'false', 'lastRoomNumber': '0',
                'showDeleteWarning': 'true', 'userChannelFormat': "{username}'s Channel",
                'sequentialChannelFormat': "-Room{number}-"
            }
            for key, value in defaults.items():
                cur.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (key, value))
            
            for i in range(1, 4):
                 cur.execute("INSERT OR IGNORE INTO message_delete_channels (slot) VALUES (?)", (f'channel{i}',))
            con.commit()

    async def load_config_to_cache(self):
        await self.bot.wait_until_ready()
        with self.get_db_connection() as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("SELECT key, value FROM config")
            rows = cur.fetchall()
            for row in rows:
                key, value = row['key'], row['value']
                if value in ['true', 'false']:
                    self.config_cache[key] = (value == 'true')
                elif value.isdigit():
                    self.config_cache[key] = int(value)
                else:
                    self.config_cache[key] = value
        print("[VoiceCreator] Config cache loaded.")
    
    async def update_config(self, key, value):
        self.config_cache[key] = value
        with self.get_db_connection() as con:
            con.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
            con.commit()

    # --- HINTERGRUND-TASKS ---
    @tasks.loop(seconds=30.0)
    async def purge_messages_task(self):
        with self.get_db_connection() as con:
            cur = con.cursor()
            now = int(time.time())
            cur.execute("SELECT message_id, channel_id FROM scheduled_deletions WHERE deletion_time <= ?", (now,))
            messages_to_delete = cur.fetchall()
            
            if not messages_to_delete:
                return

            for msg_id, chan_id in messages_to_delete:
                try:
                    channel = self.bot.get_channel(int(chan_id)) or await self.bot.fetch_channel(int(chan_id))
                    message = await channel.fetch_message(int(msg_id))
                    await message.delete()
                    await asyncio.sleep(1) # Rate-Limit vermeiden
                except (discord.NotFound, discord.Forbidden, AttributeError):
                    pass # Nachricht oder Kanal nicht gefunden, oder keine Rechte
                finally:
                    cur.execute("DELETE FROM scheduled_deletions WHERE message_id = ?", (msg_id,))
            con.commit()

    @purge_messages_task.before_loop
    async def before_purge_task(self):
        await self.bot.wait_until_ready()

    # --- EVENT-LISTENER ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # User joins a channel
        if after.channel and after.channel != before.channel:
            with self.get_db_connection() as con:
                cur = con.cursor()
                cur.execute("SELECT * FROM join_channels WHERE id = ?", (str(after.channel.id),))
                join_channel_config = cur.fetchone()

            if join_channel_config:
                channel_id, category_id, channel_format, use_sequential = join_channel_config
                
                # Naming logic
                if use_sequential:
                    new_room_number = self.config_cache.get('lastRoomNumber', 0) + 1
                    await self.update_config('lastRoomNumber', new_room_number)
                    name = channel_format.replace('{number}', str(new_room_number))
                else:
                    name = channel_format.replace('{username}', member.display_name)
                
                try:
                    category = self.bot.get_channel(int(category_id))
                    new_channel = await member.guild.create_voice_channel(
                        name,
                        category=category,
                        reason="Auto Voice Channel"
                    )
                    await member.move_to(new_channel)
                    with self.get_db_connection() as con:
                        con.execute("INSERT INTO created_channels (channel_id, creator_id) VALUES (?, ?)", (str(new_channel.id), str(member.id)))
                        con.commit()
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"[VoiceCreator] Could not create/move channel: {e}")

        # User leaves a channel
        if before.channel and before.channel != after.channel:
            with self.get_db_connection() as con:
                cur = con.cursor()
                cur.execute("SELECT channel_id FROM created_channels WHERE channel_id = ?", (str(before.channel.id),))
                is_auto_channel = cur.fetchone()

            if is_auto_channel and self.config_cache.get('deleteEmptyChannels', True) and len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Channel empty")
                    with self.get_db_connection() as con:
                        con.execute("DELETE FROM created_channels WHERE channel_id = ?", (str(before.channel.id),))
                        con.commit()
                except (discord.NotFound, discord.Forbidden) as e:
                    print(f"[VoiceCreator] Could not delete channel: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        with self.get_db_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT minutes FROM message_delete_channels WHERE channel_id = ?", (str(message.channel.id),))
            result = cur.fetchone()

        if result and result[0] is not None:
            minutes = result[0]
            # Send warning if needed
            if self.config_cache.get('showDeleteWarning', True):
                with self.get_db_connection() as con:
                    cur = con.cursor()
                    cur.execute("SELECT last_warning_time FROM warning_history WHERE channel_id = ?", (str(message.channel.id),))
                    warning_row = cur.fetchone()
                    
                    if not warning_row or (time.time() - warning_row[0]) > 3600: # 1 hour cooldown
                        time_format = f"{minutes} Minute(n)"
                        if minutes >= 60:
                            time_format = f"{minutes // 60} Stunde(n)"
                        if minutes >= 1440:
                            time_format = f"{minutes // 1440} Tag(e)"

                        await message.channel.send(f"⚠️ **Achtung!** Nachrichten in diesem Kanal werden automatisch nach **{time_format}** gelöscht.", delete_after=30)
                        cur.execute("INSERT OR REPLACE INTO warning_history (channel_id, last_warning_time) VALUES (?, ?)", (str(message.channel.id), int(time.time())))
                        con.commit()

            # Schedule deletion
            deletion_time = int(time.time()) + minutes * 60
            with self.get_db_connection() as con:
                con.execute("INSERT INTO scheduled_deletions (message_id, channel_id, deletion_time) VALUES (?, ?, ?)",
                            (str(message.id), str(message.channel.id), deletion_time))
                con.commit()

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceCreator(bot))