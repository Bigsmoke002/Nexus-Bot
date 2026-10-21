# cogs/AntiSpam/cog.py
import discord
from discord.ext import commands, tasks
from discord import app_commands, ui, ButtonStyle, Interaction
import os
import sqlite3
import time
import re
from typing import Optional, Literal
import asyncio
from datetime import datetime, timedelta

# Standardkonfiguration, falls für einen Server keine existiert
DEFAULT_CONFIG = {
    "enabled": 1,
    "message_threshold": 5,
    "time_threshold": 5,
    "timeout_duration": 10,
    "similar_threshold": 0.8,
    "max_mentions": 5,
    "sim_check_enabled": 1,
    "mass_mention_check": 1,
    "link_spam_check": 1,
    "group_detection": 1,
    "group_threshold": 3,
    "group_time": 10,
    "log_channel": None,
    "pending_links_channel": None,
    "ignore_channels": "[]",
    "ignore_roles": "[]",
}

class AntiSpam(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = "plugin_data/AntiSpam/antispam.db"
        self.message_history = {}  # guild_id -> user_id -> [messages]
        self.group_history = {}    # guild_id -> [messages]
        self.init_db()

    # --- DATENBANK-VERWALTUNG ---
    
    def init_db(self):
        """Initialisiert die Datenbank und erstellt die notwendigen Tabellen."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            # Konfigurationstabelle
            cur.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    message_threshold INTEGER DEFAULT 5,
                    time_threshold INTEGER DEFAULT 5,
                    timeout_duration INTEGER DEFAULT 10,
                    similar_threshold REAL DEFAULT 0.8,
                    max_mentions INTEGER DEFAULT 5,
                    ignore_channels TEXT DEFAULT '[]',
                    ignore_roles TEXT DEFAULT '[]',
                    sim_check_enabled INTEGER DEFAULT 1,
                    mass_mention_check INTEGER DEFAULT 1,
                    link_spam_check INTEGER DEFAULT 1,
                    group_detection INTEGER DEFAULT 1,
                    group_threshold INTEGER DEFAULT 3,
                    group_time INTEGER DEFAULT 10,
                    log_channel INTEGER,
                    pending_links_channel INTEGER
                )
            """)
            # Link-Listen
            cur.execute("""
                CREATE TABLE IF NOT EXISTS links (
                    guild_id INTEGER,
                    link TEXT NOT NULL,
                    list_type TEXT NOT NULL, -- 'whitelist', 'blacklist'
                    UNIQUE(guild_id, link)
                )
            """)
            # Ausstehende Links
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pending_links (
                    guild_id INTEGER,
                    link TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    timestamp INTEGER NOT NULL,
                    UNIQUE(guild_id, link)
                )
            """)
            # Spam-Logs
            cur.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    message_count INTEGER NOT NULL,
                    content_sample TEXT,
                    timestamp INTEGER NOT NULL
                )
            """)
            con.commit()

    def get_config(self, guild_id: int) -> dict:
        """Holt die Konfiguration für einen Server aus der DB."""
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("SELECT * FROM config WHERE guild_id = ?", (guild_id,))
            config = cur.fetchone()
            if not config:
                cur.execute(
                    "INSERT OR IGNORE INTO config (guild_id) VALUES (?)", (guild_id,)
                )
                con.commit()
                # Erneut holen, um Standardwerte zu erhalten
                cur.execute("SELECT * FROM config WHERE guild_id = ?", (guild_id,))
                config = cur.fetchone()
            return dict(config)

    def save_config(self, guild_id: int, settings: dict):
        """Speichert eine Konfigurationseinstellung für einen Server."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            for key, value in settings.items():
                cur.execute(
                    f"UPDATE config SET {key} = ? WHERE guild_id = ?", (value, guild_id)
                )
            con.commit()

    def get_link_lists(self, guild_id: int) -> dict:
        """Holt alle Link-Listen für einen Server."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            # Whitelist & Blacklist
            cur.execute("SELECT link, list_type FROM links WHERE guild_id = ?", (guild_id,))
            links_data = cur.fetchall()
            whitelist = [row[0] for row in links_data if row[1] == 'whitelist']
            blacklist = [row[0] for row in links_data if row[1] == 'blacklist']
            # Pending List
            cur.execute("SELECT link, user_id FROM pending_links WHERE guild_id = ?", (guild_id,))
            pending = [{"link": row[0], "userId": row[1]} for row in cur.fetchall()]
            return {"whitelist": whitelist, "blacklist": blacklist, "pending": pending}

    # --- KERNLOGIK (SPAM-ERKENNUNG) ---
    
    def _levenshtein_similarity(self, s1: str, s2: str) -> float:
        """Berechnet die Ähnlichkeit zweier Strings (0-1)."""
        max_len = 200
        s1 = str(s1 or '')[:max_len]
        s2 = str(s2 or '')[:max_len]

        if s1 == s2: return 1.0
        if not s1 or not s2: return 0.0

        m, n = len(s1), len(s2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        for i in range(m + 1): dp[i][0] = i
        for j in range(n + 1): dp[0][j] = j

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                cost = 0 if s1[i - 1] == s2[j - 1] else 1
                dp[i][j] = min(dp[i - 1][j] + 1,        # Deletion
                               dp[i][j - 1] + 1,        # Insertion
                               dp[i - 1][j - 1] + cost) # Substitution

        max_len_val = max(m, n)
        if max_len_val == 0: return 1.0
        return 1 - (dp[m][n] / max_len_val)

    def _extract_links(self, text: str) -> list[str]:
        """Extrahiert URLs aus einem Text."""
        return re.findall(r'(https?://[^\s]+)', text)

    def _normalize_link(self, link: str) -> str:
        """Normalisiert einen Link für bessere Vergleiche."""
        try:
            normalized = link.lower()
            normalized = re.sub(r'^(https?:\/\/)?(www\.)?', '', normalized)
            normalized = re.sub(r'\/+$', '', normalized)
            return normalized
        except:
            return link
            
    def _is_link_in_lists(self, link: str, lists: dict) -> str | bool:
        """Prüft, ob ein Link in Whitelist, Blacklist oder Pending-Liste ist."""
        normalized_link = self._normalize_link(link)
        
        for whitelisted in lists.get('whitelist', []):
            white_normalized = self._normalize_link(whitelisted)
            if normalized_link == white_normalized or normalized_link.startswith(white_normalized):
                return 'whitelist'
        
        for blacklisted in lists.get('blacklist', []):
            black_normalized = self._normalize_link(blacklisted)
            if normalized_link == black_normalized or normalized_link.startswith(black_normalized):
                return 'blacklist'

        for pending_item in lists.get('pending', []):
            pending_normalized = self._normalize_link(pending_item['link'])
            if normalized_link == pending_normalized or normalized_link.startswith(pending_normalized):
                return 'pending'
                
        return False

    async def _handle_spam(self, message: discord.Message, reason: str, config: dict, user_history: list):
        """Führt Aktionen bei erkannter Spam-Aktivität aus."""
        member = message.author
        channel = message.channel
        
        try:
            # 1. Nachrichten löschen
            two_weeks_ago = discord.utils.utcnow() - timedelta(weeks=2)
            time_threshold_ms = time.time() - config['time_threshold']
            
            messages_to_delete = []
            async for msg in channel.history(limit=50):
                if msg.author.id == member.id and msg.created_at.timestamp() > time_threshold_ms:
                    if msg.created_at > two_weeks_ago:
                        messages_to_delete.append(msg)

            if messages_to_delete:
                await channel.delete_messages(messages_to_delete, reason=f"Anti-Spam: {reason}")
            
            # 2. Timeout anwenden
            bot_member = message.guild.get_member(self.bot.user.id)
            if bot_member.guild_permissions.moderate_members and bot_member.top_role > member.top_role:
                timeout_duration = timedelta(minutes=config['timeout_duration'])
                await member.timeout(timeout_duration, reason=f"Anti-Spam: {reason}")
            
            # 3. Vorfall loggen
            sample = user_history[-1]['content'][:100] if user_history else ""
            log_id = self._log_incident(message.guild.id, member.id, channel.id, reason, len(user_history), sample)

            # 4. Log an Kanal senden
            if log_id:
                await self._send_log_to_channel(
                    message.guild.id, log_id, member.id, channel.id, 
                    reason, len(user_history), sample, config
                )

            # 5. DM an Benutzer senden
            try:
                embed = discord.Embed(
                    title="Anti-Spam: Maßnahme ergriffen",
                    description=f"Du hast einen Timeout für **{config['timeout_duration']} Minuten** erhalten.",
                    color=discord.Color.red()
                )
                embed.add_field(name="Grund", value=reason, inline=True)
                embed.add_field(name="Server", value=message.guild.name, inline=True)
                embed.timestamp = discord.utils.utcnow()
                await member.send(embed=embed)
            except discord.Forbidden:
                pass  # DM konnte nicht gesendet werden

            # 6. Benutzer-Verlauf leeren
            if member.id in self.message_history.get(message.guild.id, {}):
                self.message_history[message.guild.id][member.id] = []

        except Exception as e:
            print(f"[AntiSpam Error] Fehler bei der Spam-Behandlung: {e}")

    # --- LOGGING & BENACHRICHTIGUNGEN ---

    def _log_incident(self, guild_id, user_id, channel_id, reason, msg_count, sample) -> int:
        """Speichert einen Spam-Vorfall in der Datenbank."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            timestamp = int(time.time())
            cur.execute(
                "INSERT INTO logs (guild_id, user_id, channel_id, reason, message_count, content_sample, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (guild_id, user_id, channel_id, reason, msg_count, sample, timestamp)
            )
            con.commit()
            return cur.lastrowid

    async def _send_log_to_channel(self, guild_id, log_id, user_id, channel_id, reason, msg_count, sample, config):
        """Sendet eine formatierte Log-Nachricht an den konfigurierten Log-Kanal."""
        log_channel_id = config.get('log_channel')
        if not log_channel_id:
            return

        channel = self.bot.get_channel(log_channel_id)
        if not channel:
            return
        
        embed = discord.Embed(
            title=f"Anti-Spam: Vorfall #{log_id}",
            description="Ein Spam-Vorfall wurde erkannt und behandelt.",
            color=discord.Color.red()
        )
        embed.add_field(name="Benutzer", value=f"<@{user_id}>", inline=True)
        embed.add_field(name="Kanal", value=f"<#{channel_id}>", inline=True)
        embed.add_field(name="Grund", value=reason, inline=True)
        embed.add_field(name="Nachrichten", value=str(msg_count), inline=True)
        embed.add_field(name="Zeitpunkt", value=f"<t:{int(time.time())}:F>", inline=True)
        embed.add_field(name="Beispielinhalt", value=f"```\n{sample or 'N/A'}\n```", inline=False)
        embed.timestamp = discord.utils.utcnow()
        
        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[AntiSpam Error] Konnte Log nicht an Kanal senden: {e}")

    async def _send_link_for_review(self, guild_id, link, user_id, message_content, config):
        """Sendet einen Link zur Überprüfung an den konfigurierten Kanal."""
        review_channel_id = config.get('pending_links_channel')
        if not review_channel_id:
            return

        channel = self.bot.get_channel(review_channel_id)
        if not channel:
            return

        embed = discord.Embed(
            title="Link-Überprüfung erforderlich",
            description="Ein neuer Link wurde erkannt und muss überprüft werden.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Link", value=link, inline=False)
        embed.add_field(name="Gesendet von", value=f"<@{user_id}>", inline=True)
        embed.add_field(name="Zeitpunkt", value=f"<t:{int(time.time())}:F>", inline=True)
        embed.add_field(name="Nachrichtenkontext", value=f"```\n{message_content[:300]}{'...' if len(message_content) > 300 else ''}\n```", inline=False)
        embed.set_footer(text="Reagiere mit ✅ zum Genehmigen oder ❌ zum Blockieren.")
        embed.timestamp = discord.utils.utcnow()

        try:
            review_message = await channel.send(embed=embed)
            await review_message.add_reaction('✅')
            await review_message.add_reaction('❌')
        except Exception as e:
            print(f"[AntiSpam Error] Konnte Link-Review nicht senden: {e}")

    # --- EVENT-LISTENER ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        guild_id = message.guild.id
        user_id = message.author.id
        channel_id = message.channel.id
        content = message.content
        timestamp = time.time()

        config = self.get_config(guild_id)
        if not config.get("enabled"):
            return

        # Ignorierte Kanäle und Rollen prüfen
        ignore_channels = eval(config.get("ignore_channels", "[]"))
        ignore_roles = eval(config.get("ignore_roles", "[]"))
        if channel_id in ignore_channels:
            return
        if any(role.id in ignore_roles for role in message.author.roles):
            return

        # --- Link-Prüfung ---
        links = self._extract_links(content)
        if links:
            lists = self.get_link_lists(guild_id)
            contains_blocked = False
            contains_unverified = False
            
            for link in links:
                status = self._is_link_in_lists(link, lists)
                if status == 'blacklist':
                    contains_blocked = True
                elif status is False:
                    contains_unverified = True
                    # In Pending-Liste eintragen und Review starten
                    with sqlite3.connect(self.db_path) as con:
                        cur = con.cursor()
                        cur.execute(
                            "INSERT OR IGNORE INTO pending_links (guild_id, link, user_id, message_id, channel_id, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                            (guild_id, link, user_id, message.id, channel_id, int(timestamp))
                        )
                        con.commit()
                    await self._send_link_for_review(guild_id, link, user_id, content, config)

            if contains_blocked or contains_unverified:
                try:
                    await message.delete()
                    desc = "Deine Nachricht enthielt einen blockierten Link und wurde entfernt." if contains_blocked else "Deine Nachricht enthielt einen unüberprüften Link und wurde zur Überprüfung entfernt."
                    color = discord.Color.red() if contains_blocked else discord.Color.orange()
                    embed = discord.Embed(title="Link entfernt", description=desc, color=color)
                    await message.author.send(embed=embed, delete_after=30)
                except (discord.Forbidden, discord.NotFound):
                    pass
                return

        # --- Spam-Prüfung ---
        if guild_id not in self.message_history:
            self.message_history[guild_id] = {}
        if user_id not in self.message_history[guild_id]:
            self.message_history[guild_id][user_id] = []
        
        user_history = self.message_history[guild_id][user_id]
        user_history.append({"content": content, "timestamp": timestamp, "message_id": message.id})

        # Alte Nachrichten entfernen
        time_limit = timestamp - config['time_threshold']
        user_history[:] = [msg for msg in user_history if msg['timestamp'] > time_limit]

        is_spam = False
        spam_reason = ""

        # 1. Nachrichten-Frequenz
        if len(user_history) >= config['message_threshold']:
            is_spam = True
            spam_reason = "Zu viele Nachrichten in kurzer Zeit"

        # 2. Ähnliche Nachrichten
        if not is_spam and config.get('sim_check_enabled') and len(user_history) > 1:
            last_msgs = [msg['content'] for msg in user_history[:-1]]
            for msg_content in last_msgs:
                if self._levenshtein_similarity(msg_content, content) >= config['similar_threshold']:
                    is_spam = True
                    spam_reason = "Wiederholte ähnliche Nachrichten"
                    break
        
        # 3. Massen-Erwähnungen
        if not is_spam and config.get('mass_mention_check'):
            if len(message.mentions) + len(message.role_mentions) > config['max_mentions']:
                is_spam = True
                spam_reason = "Zu viele Erwähnungen in einer Nachricht"
        
        # 4. Link-Spam (nur für erlaubte Links)
        if not is_spam and config.get('link_spam_check') and links:
            link_messages_count = sum(1 for msg in user_history if self._extract_links(msg['content']))
            if link_messages_count >= 3: # Harter Wert aus JS übernommen
                is_spam = True
                spam_reason = "Zu viele erlaubte Links in kurzer Zeit"
        
        if is_spam:
            await self._handle_spam(message, spam_reason, config, user_history)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id or not payload.guild_id:
            return

        guild_id = payload.guild_id
        config = self.get_config(guild_id)
        if payload.channel_id != config.get('pending_links_channel'):
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel: return
        
        try:
            message = await channel.fetch_message(payload.message_id)
            member = payload.member
            if not member or not message or not message.embeds: return
            
            # Berechtigungen prüfen
            if not (member.guild_permissions.manage_guild or member.guild_permissions.moderate_members):
                return
            
            embed = message.embeds[0]
            if not embed.title or "Link-Überprüfung" not in embed.title:
                return

            link_field = discord.utils.get(embed.fields, name="Link")
            if not link_field: return
            
            link = link_field.value
            
            # Link aus pending entfernen
            with sqlite3.connect(self.db_path) as con:
                cur = con.cursor()
                cur.execute("DELETE FROM pending_links WHERE guild_id = ? AND link = ?", (guild_id, link))
                
                new_title = ""
                new_color = discord.Color.default()
                
                # In Whitelist oder Blacklist eintragen
                if str(payload.emoji) == '✅':
                    cur.execute("INSERT OR IGNORE INTO links (guild_id, link, list_type) VALUES (?, ?, ?)", (guild_id, link, 'whitelist'))
                    cur.execute("DELETE FROM links WHERE guild_id = ? AND link = ? AND list_type = ?", (guild_id, link, 'blacklist'))
                    new_title, new_color = "Link genehmigt", discord.Color.green()
                
                elif str(payload.emoji) == '❌':
                    cur.execute("INSERT OR IGNORE INTO links (guild_id, link, list_type) VALUES (?, ?, ?)", (guild_id, link, 'blacklist'))
                    cur.execute("DELETE FROM links WHERE guild_id = ? AND link = ? AND list_type = ?", (guild_id, link, 'whitelist'))
                    new_title, new_color = "Link blockiert", discord.Color.red()
                
                con.commit()

            if new_title:
                updated_embed = embed.copy()
                updated_embed.title = new_title
                updated_embed.color = new_color
                updated_embed.set_footer(text=f"Bearbeitet von {member.display_name}")
                await message.edit(embed=updated_embed)
                await message.clear_reactions()

        except Exception as e:
            print(f"[AntiSpam Error] Fehler bei der Reaktionsverarbeitung: {e}")

    # --- SLASH-BEFEHLE ---
    
    antispam = app_commands.Group(
        name="antispam", 
        description="Verwaltet das Anti-Spam-System.",
        default_permissions=discord.Permissions(manage_guild=True)
    )

    @antispam.command(name="status", description="Zeigt den aktuellen Status und die Konfiguration an.")
    async def status(self, interaction: Interaction):
        config = self.get_config(interaction.guild_id)
        is_enabled = config.get('enabled', 0)
        
        embed = discord.Embed(
            title="Anti-Spam System Status",
            description=f"Das System ist derzeit **{'aktiviert' if is_enabled else 'deaktiviert'}**.",
            color=discord.Color.green() if is_enabled else discord.Color.red()
        )
        embed.add_field(name="Nachrichten-Limit", value=f"{config['message_threshold']} Nachrichten", inline=True)
        embed.add_field(name="Zeitfenster", value=f"{config['time_threshold']} Sekunden", inline=True)
        embed.add_field(name="Timeout-Dauer", value=f"{config['timeout_duration']} Minuten", inline=True)
        embed.add_field(name="Ähnlichkeits-Limit", value=f"{config['similar_threshold']}", inline=True)
        embed.add_field(name="Max. Erwähnungen", value=f"{config['max_mentions']}", inline=True)
        embed.add_field(name="Gruppen-Limit", value=f"{config['group_threshold']} Nachrichten", inline=True)
        embed.add_field(name="Gruppen-Zeitfenster", value=f"{config['group_time']} Sekunden", inline=True)
        
        checks_value = (
            f"Ähnlichkeit: {'✅' if config.get('sim_check_enabled') else '❌'}\n"
            f"Massen-Erwähnung: {'✅' if config.get('mass_mention_check') else '❌'}\n"
            f"Link-Spam: {'✅' if config.get('link_spam_check') else '❌'}\n"
            f"Gruppen-Erkennung: {'✅' if config.get('group_detection') else '❌'}"
        )
        embed.add_field(name="Aktive Prüfungen", value=checks_value, inline=False)
        
        if config.get('log_channel'):
            embed.add_field(name="Log-Kanal", value=f"<#{config['log_channel']}>", inline=True)
        if config.get('pending_links_channel'):
            embed.add_field(name="Link-Review-Kanal", value=f"<#{config['pending_links_channel']}>", inline=True)

        ignore_channels = eval(config.get("ignore_channels", "[]"))
        if ignore_channels:
            embed.add_field(name="Ignorierte Kanäle", value=", ".join(f"<#{c}>" for c in ignore_channels), inline=False)
        ignore_roles = eval(config.get("ignore_roles", "[]"))
        if ignore_roles:
            embed.add_field(name="Ignorierte Rollen", value=", ".join(f"<@&{r}>" for r in ignore_roles), inline=False)
        
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @antispam.command(name="toggle", description="Aktiviert oder deaktiviert das Anti-Spam-System.")
    async def toggle(self, interaction: Interaction):
        config = self.get_config(interaction.guild_id)
        new_status = not config.get('enabled', 0)
        self.save_config(interaction.guild_id, {"enabled": int(new_status)})
        
        embed = discord.Embed(
            title="Anti-Spam System",
            description=f"Das System wurde **{'aktiviert' if new_status else 'deaktiviert'}**.",
            color=discord.Color.green() if new_status else discord.Color.red()
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @antispam.command(name="config", description="Ändert eine Einstellung des Anti-Spam-Systems.")
    @app_commands.describe(
        setting="Die zu ändernde Einstellung.",
        value="Der neue Wert für die Einstellung."
    )
    @app_commands.choices(setting=[
        app_commands.Choice(name="Nachrichten-Limit", value="message_threshold"),
        app_commands.Choice(name="Zeitfenster (Sekunden)", value="time_threshold"),
        app_commands.Choice(name="Timeout-Dauer (Minuten)", value="timeout_duration"),
        app_commands.Choice(name="Ähnlichkeits-Limit (0.0-1.0)", value="similar_threshold"),
        app_commands.Choice(name="Max. Erwähnungen", value="max_mentions"),
        app_commands.Choice(name="Ähnlichkeits-Prüfung (true/false)", value="sim_check_enabled"),
        app_commands.Choice(name="Massen-Erwähnungs-Prüfung (true/false)", value="mass_mention_check"),
        app_commands.Choice(name="Link-Spam-Prüfung (true/false)", value="link_spam_check"),
        app_commands.Choice(name="Gruppen-Erkennung (true/false)", value="group_detection"),
        app_commands.Choice(name="Gruppen-Limit", value="group_threshold"),
        app_commands.Choice(name="Gruppen-Zeitfenster (Sekunden)", value="group_time"),
    ])
    async def config(self, interaction: Interaction, setting: str, value: str):
        config = self.get_config(interaction.guild_id)
        new_value = None
        error_msg = ""

        bool_true = ['true', '1', 'yes', 'an', 'on']
        bool_false = ['false', '0', 'no', 'aus', 'off']

        try:
            if setting in ['message_threshold', 'time_threshold', 'timeout_duration', 'max_mentions', 'group_threshold', 'group_time']:
                new_value = int(value)
                if new_value < 1:
                    error_msg = "Der Wert muss eine positive Zahl sein."
            elif setting == 'similar_threshold':
                new_value = float(value)
                if not (0.0 <= new_value <= 1.0):
                    error_msg = "Der Wert muss zwischen 0.0 und 1.0 liegen."
            elif setting in ['sim_check_enabled', 'mass_mention_check', 'link_spam_check', 'group_detection']:
                if value.lower() in bool_true: new_value = 1
                elif value.lower() in bool_false: new_value = 0
                else: error_msg = "Gültige Werte sind: true/false, 1/0, yes/no."
            else:
                error_msg = "Unbekannte Einstellung."
        except ValueError:
            error_msg = "Ungültiger Wert. Bitte gib eine passende Zahl an."

        if error_msg:
            embed = discord.Embed(title="Fehler", description=error_msg, color=discord.Color.red())
            embed.timestamp = discord.utils.utcnow()
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        self.save_config(interaction.guild_id, {setting: new_value})
        embed = discord.Embed(
            title="Konfiguration aktualisiert",
            description=f"Die Einstellung `{setting}` wurde auf `{value}` gesetzt.",
            color=discord.Color.green()
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @antispam.command(name="ignore_channel", description="Fügt einen Kanal zur Ignorier-Liste hinzu oder entfernt ihn.")
    @app_commands.describe(channel="Der zu ignorierende Kanal.")
    async def ignore_channel(self, interaction: Interaction, channel: discord.TextChannel):
        config = self.get_config(interaction.guild_id)
        ignored_channels = eval(config.get('ignore_channels', '[]'))
        
        if channel.id in ignored_channels:
            ignored_channels.remove(channel.id)
            msg = f"Der Kanal {channel.mention} wird nicht mehr ignoriert."
        else:
            ignored_channels.append(channel.id)
            msg = f"Der Kanal {channel.mention} wird nun vom Anti-Spam-System ignoriert."
        
        self.save_config(interaction.guild_id, {"ignore_channels": str(ignored_channels)})
        embed = discord.Embed(title="Konfiguration aktualisiert", description=msg, color=discord.Color.green())
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @antispam.command(name="ignore_role", description="Fügt eine Rolle zur Ignorier-Liste hinzu oder entfernt sie.")
    @app_commands.describe(role="Die zu ignorierende Rolle.")
    async def ignore_role(self, interaction: Interaction, role: discord.Role):
        config = self.get_config(interaction.guild_id)
        ignored_roles = eval(config.get('ignore_roles', '[]'))
        
        if role.id in ignored_roles:
            ignored_roles.remove(role.id)
            msg = f"Die Rolle {role.mention} wird nicht mehr ignoriert."
        else:
            ignored_roles.append(role.id)
            msg = f"Die Rolle {role.mention} wird nun vom Anti-Spam-System ignoriert."
            
        self.save_config(interaction.guild_id, {"ignore_roles": str(ignored_roles)})
        embed = discord.Embed(title="Konfiguration aktualisiert", description=msg, color=discord.Color.green())
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @antispam.command(name="set_log_channel", description="Legt den Kanal für Spam-Protokolle fest.")
    @app_commands.describe(channel="Der Kanal für die Logs.")
    async def set_log_channel(self, interaction: Interaction, channel: discord.TextChannel):
        self.save_config(interaction.guild_id, {"log_channel": channel.id})
        embed = discord.Embed(
            title="Konfiguration aktualisiert", 
            description=f"Der Log-Kanal wurde auf {channel.mention} gesetzt.", 
            color=discord.Color.green()
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @antispam.command(name="set_links_channel", description="Legt den Kanal für die Link-Überprüfung fest.")
    @app_commands.describe(channel="Der Kanal für die Link-Reviews.")
    async def set_links_channel(self, interaction: Interaction, channel: discord.TextChannel):
        self.save_config(interaction.guild_id, {"pending_links_channel": channel.id})
        embed = discord.Embed(
            title="Konfiguration aktualisiert", 
            description=f"Der Link-Review-Kanal wurde auf {channel.mention} gesetzt.", 
            color=discord.Color.green()
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @antispam.command(name="whitelist_link", description="Fügt einen Link zur Whitelist hinzu.")
    @app_commands.describe(link="Der zu erlaubende Link (z.B. google.com).")
    async def whitelist_link(self, interaction: Interaction, link: str):
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("DELETE FROM links WHERE guild_id = ? AND link = ?", (interaction.guild_id, link))
            cur.execute("DELETE FROM pending_links WHERE guild_id = ? AND link = ?", (interaction.guild_id, link))
            cur.execute("INSERT OR IGNORE INTO links (guild_id, link, list_type) VALUES (?, ?, ?)", (interaction.guild_id, link, 'whitelist'))
            con.commit()
        embed = discord.Embed(
            title="Link-Management",
            description=f"Der Link `{link}` wurde zur Whitelist hinzugefügt.",
            color=discord.Color.green()
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @antispam.command(name="blacklist_link", description="Fügt einen Link zur Blacklist hinzu.")
    @app_commands.describe(link="Der zu blockierende Link (z.B. boeseseite.net).")
    async def blacklist_link(self, interaction: Interaction, link: str):
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("DELETE FROM links WHERE guild_id = ? AND link = ?", (interaction.guild_id, link))
            cur.execute("DELETE FROM pending_links WHERE guild_id = ? AND link = ?", (interaction.guild_id, link))
            cur.execute("INSERT OR IGNORE INTO links (guild_id, link, list_type) VALUES (?, ?, ?)", (interaction.guild_id, link, 'blacklist'))
            con.commit()
        embed = discord.Embed(
            title="Link-Management",
            description=f"Der Link `{link}` wurde zur Blacklist hinzugefügt.",
            color=discord.Color.green()
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @antispam.command(name="remove_link", description="Entfernt einen Link aus allen Listen.")
    @app_commands.describe(link="Der zu entfernende Link.")
    async def remove_link(self, interaction: Interaction, link: str):
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("DELETE FROM links WHERE guild_id = ? AND link = ?", (interaction.guild_id, link))
            cur.execute("DELETE FROM pending_links WHERE guild_id = ? AND link = ?", (interaction.guild_id, link))
            con.commit()
        embed = discord.Embed(
            title="Link-Management",
            description=f"Der Link `{link}` wurde aus allen Listen entfernt.",
            color=discord.Color.green()
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @antispam.command(name="list_links", description="Zeigt die Links einer bestimmten Liste an.")
    @app_commands.describe(liste="Die anzuzeigende Liste.")
    @app_commands.choices(liste=[
        app_commands.Choice(name="Whitelist", value="whitelist"),
        app_commands.Choice(name="Blacklist", value="blacklist"),
        app_commands.Choice(name="Pendinglist", value="pending"),
    ])
    async def list_links(self, interaction: Interaction, liste: str):
        lists = self.get_link_lists(interaction.guild_id)
        
        title_map = {"whitelist": "Whitelist", "blacklist": "Blacklist", "pending": "Pending-Liste"}
        color_map = {"whitelist": discord.Color.green(), "blacklist": discord.Color.red(), "pending": discord.Color.orange()}
        
        embed = discord.Embed(
            title=f"Link-Management: {title_map[liste]}",
            color=color_map[liste]
        )
        
        if liste == 'pending':
            link_list = [f"{item['link']} (von <@{item['userId']}>)" for item in lists[liste]]
        else:
            link_list = lists[liste]
        
        if not link_list:
            embed.description = "Diese Liste ist leer."
        else:
            description = ""
            for i, item in enumerate(link_list, 1):
                line = f"{i}. {item}\n"
                if len(description) + len(line) > 4000:
                    description += "..."
                    break
                description += line
            embed.description = description
        
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @antispam.command(name="logs", description="Zeigt die letzten Anti-Spam-Vorfälle an.")
    @app_commands.describe(limit="Anzahl der anzuzeigenden Einträge (Standard: 10).")
    async def logs(self, interaction: Interaction, limit: app_commands.Range[int, 1, 25] = 10):
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute(
                "SELECT * FROM logs WHERE guild_id = ? ORDER BY timestamp DESC LIMIT ?",
                (interaction.guild_id, limit)
            )
            logs = cur.fetchall()

        if not logs:
            embed = discord.Embed(title="Anti-Spam Logs", description="Es wurden keine Spam-Vorfälle aufgezeichnet.", color=discord.Color.green())
            embed.timestamp = discord.utils.utcnow()
            await interaction.response.send_message(embed=embed)
            return

        embed = discord.Embed(title="Anti-Spam Logs", description=f"Die letzten {len(logs)} Spam-Vorfälle:", color=discord.Color.red())
        for log in logs:
            embed.add_field(
                name=f"Vorfall #{log['log_id']} (<t:{log['timestamp']}:R>)",
                value=(
                    f"**Benutzer:** <@{log['user_id']}>\n"
                    f"**Kanal:** <#{log['channel_id']}>\n"
                    f"**Grund:** {log['reason']}\n"
                    f"**Beispiel:** `{log['content_sample']}`"
                ),
                inline=False
            )
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @antispam.command(name="userlogs", description="Zeigt die letzten Vorfälle für einen bestimmten Benutzer an.")
    @app_commands.describe(user="Der Benutzer, dessen Logs angezeigt werden sollen.", limit="Anzahl der Einträge.")
    async def userlogs(self, interaction: Interaction, user: discord.Member, limit: app_commands.Range[int, 1, 25] = 10):
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute(
                "SELECT * FROM logs WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC LIMIT ?",
                (interaction.guild_id, user.id, limit)
            )
            logs = cur.fetchall()

        if not logs:
            embed = discord.Embed(title=f"Logs für {user.display_name}", description=f"Keine Vorfälle für {user.mention} gefunden.", color=discord.Color.green())
            embed.timestamp = discord.utils.utcnow()
            await interaction.response.send_message(embed=embed)
            return
        
        embed = discord.Embed(title=f"Logs für {user.display_name}", description=f"Die letzten {len(logs)} Vorfälle:", color=discord.Color.red())
        for log in logs:
            embed.add_field(
                name=f"Vorfall #{log['log_id']} (<t:{log['timestamp']}:R>)",
                value=(
                    f"**Kanal:** <#{log['channel_id']}>\n"
                    f"**Grund:** {log['reason']}\n"
                    f"**Beispiel:** `{log['content_sample']}`"
                ),
                inline=False
            )
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @antispam.command(name="clearlogs", description="Löscht alle Anti-Spam-Logs für diesen Server.")
    async def clearlogs(self, interaction: Interaction):
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("DELETE FROM logs WHERE guild_id = ?", (interaction.guild_id,))
            con.commit()
        
        embed = discord.Embed(
            title="Logs gelöscht",
            description="Alle Anti-Spam-Logs für diesen Server wurden erfolgreich gelöscht.",
            color=discord.Color.green()
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(AntiSpam(bot))