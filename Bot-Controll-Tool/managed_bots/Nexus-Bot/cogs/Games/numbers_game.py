# cogs/numbers_game.py
import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
import time

class NumbersGame(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # --- NEU: Dynamische Pfaderstellung ---
        # Erstellt einen Pfad wie: ./plugin_data/NumbersGame/data.db
        plugin_name = self.__class__.__name__
        data_folder = os.path.join('plugin_data', plugin_name)
        self.db_path = os.path.join(data_folder, 'data.db')
        
        # Die init_database Funktion erstellt jetzt den Ordner und die Tabellen.
        self.db_conn = self.init_database()
        
        if self.db_conn:
            print(f"INFO: {plugin_name} Cog geladen. Datenbank unter {self.db_path} initialisiert.")
        else:
            print(f"FATAL: {plugin_name} Cog konnte aufgrund eines DB-Fehlers nicht korrekt geladen werden.")

    def cog_unload(self):
        """Wird aufgerufen, wenn der Cog entladen wird, und schließt die DB-Verbindung."""
        if self.db_conn:
            self.db_conn.close()

    def init_database(self):
        """
        Stellt die Verbindung zur DB her und erstellt den Ordner sowie alle notwendigen Tabellen.
        """
        try:
            # Erstellt den Ordner (z.B. plugin_data/NumbersGame), falls er nicht existiert.
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Tabelle für die Spielkonfiguration
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS numbers_game_config (
                    id INTEGER PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    channel_id INTEGER,
                    current_number INTEGER NOT NULL DEFAULT 0
                )
            """)

            # Tabelle für die Spieler-Scores
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS numbers_game_players (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    last_number INTEGER NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)

            # Tabelle für den Spielverlauf
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS numbers_game_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    number INTEGER NOT NULL,
                    timestamp REAL NOT NULL,
                    success INTEGER NOT NULL
                )
            """)
            
            # Standard-Konfiguration einfügen, falls nicht vorhanden
            cursor.execute("SELECT id FROM numbers_game_config WHERE id = 1")
            if cursor.fetchone() is None:
                cursor.execute("INSERT INTO numbers_game_config (id, enabled) VALUES (1, 0)")
                print("INFO: Standard-Konfiguration für Numbers Game erstellt.")

            conn.commit()
            return conn
        except Exception as e:
            print(f"FATAL: Konnte die Numbers Game DB nicht initialisieren: {e}")
            return None

    # ... (alle anderen Methoden des Cogs wie get_config, on_ready, on_message, etc. bleiben unverändert)
    def get_config(self):
        """Lädt die Konfiguration aus der Datenbank."""
        if not self.db_conn: return {'enabled': False}
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT * FROM numbers_game_config WHERE id = 1")
        config = cursor.fetchone()
        return dict(config) if config else {'enabled': False, 'channel_id': None, 'current_number': 0}

    def save_config(self, config):
        """Speichert die Konfiguration in der Datenbank."""
        if not self.db_conn: return
        cursor = self.db_conn.cursor()
        cursor.execute(
            "UPDATE numbers_game_config SET enabled = ?, channel_id = ?, current_number = ? WHERE id = 1",
            (int(config['enabled']), config['channel_id'], config['current_number'])
        )
        self.db_conn.commit()

    @commands.Cog.listener()
    async def on_ready(self):
        config = self.get_config()
        if config.get('enabled') and config.get('channel_id'):
            print(f"INFO: Numbers Game überwacht Kanal-ID {config['channel_id']}.")
            try:
                channel = await self.bot.fetch_channel(config['channel_id'])
                if channel:
                    embed = discord.Embed(
                        title="🎯 Zahlen-Fortsetzungsspiel - Bot Neustart",
                        description=f"🔄 Der Bot wurde neu gestartet. Das Spiel ist **aktiv**.\n\n"
                                    f"📊 **Letzte Zahl:** {config['current_number']}\n"
                                    f"➡️ **Nächste erwartete Zahl:** {config['current_number'] + 1}",
                        color=discord.Color.blue()
                    )
                    await channel.send(embed=embed)
            except discord.NotFound:
                print(f"ERROR: Kanal für Numbers Game (ID: {config['channel_id']}) nicht gefunden.")
            except Exception as e:
                print(f"ERROR: Konnte Numbers Game Startnachricht nicht senden: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.db_conn or message.author.bot:
            return

        config = self.get_config()
        if not config.get('enabled') or not config.get('channel_id') or message.channel.id != config['channel_id']:
            return

        try:
            number = int(message.content.strip())
        except ValueError:
            return

        cursor = self.db_conn.cursor()
        
        cursor.execute("SELECT user_id FROM numbers_game_players ORDER BY timestamp DESC LIMIT 1")
        last_player = cursor.fetchone()
        
        if last_player and last_player['user_id'] == str(message.author.id) and config['current_number'] > 0:
            await self.reset_game(message, "zwei mal hintereinander geschrieben")
            return

        if number == config['current_number'] + 1:
            await message.add_reaction('✅')
            config['current_number'] = number
            self.save_config(config)
            
            timestamp = time.time()
            cursor.execute(
                "INSERT OR REPLACE INTO numbers_game_players (user_id, username, last_number, timestamp) VALUES (?, ?, ?, ?)",
                (str(message.author.id), message.author.name, number, timestamp)
            )
            cursor.execute(
                "INSERT INTO numbers_game_history (user_id, username, number, timestamp, success) VALUES (?, ?, ?, ?, ?)",
                (str(message.author.id), message.author.name, number, timestamp, 1)
            )
            self.db_conn.commit()
        else:
            await self.reset_game(message, "die falsche Zahl geschrieben", expected_number=config['current_number'] + 1, received_number=number)

    async def reset_game(self, message, reason, **kwargs):
        """Setzt das Spiel zurück und sendet eine Benachrichtigung."""
        await message.add_reaction('❌')

        expected = kwargs.get('expected_number')
        received = kwargs.get('received_number')
        
        description = f"❌ **{message.author.mention} hat {reason}!**\n\n"
        if expected is not None and received is not None:
            description += f"📊 **Erwartet wurde:** `{expected}`\n📥 **Erhalten:** `{received}`\n\n"
        
        description += "🔄 Das Spiel wird auf **0** zurückgesetzt. Beginnt wieder bei **1**."
        
        embed = discord.Embed(
            title="🎯 Zahlen-Fortsetzungsspiel - Fehler!",
            description=description,
            color=discord.Color.red()
        )
        await message.channel.send(embed=embed)
        
        cursor = self.db_conn.cursor()
        config = self.get_config()
        config['current_number'] = 0
        self.save_config(config)

        cursor.execute("DELETE FROM numbers_game_players")
        cursor.execute(
            "INSERT INTO numbers_game_history (user_id, username, number, timestamp, success) VALUES (?, ?, ?, ?, ?)",
            (str(message.author.id), message.author.name, received if received is not None else -1, time.time(), 0)
        )
        self.db_conn.commit()

    numbers_game_group = app_commands.Group(name="numbers_game", description="Verwaltet das Zahlen-Fortsetzungsspiel", guild_only=True, default_permissions=discord.Permissions(manage_guild=True))

    @numbers_game_group.command(name="setup", description="Konfiguriert den Kanal für das Spiel.")
    @app_commands.describe(channel="Der Kanal, in dem das Spiel stattfinden soll.")
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        config = self.get_config()
        config['channel_id'] = channel.id
        config['enabled'] = True
        config['current_number'] = 0
        self.save_config(config)
        
        cursor = self.db_conn.cursor()
        cursor.execute("DELETE FROM numbers_game_players")
        self.db_conn.commit()
        
        embed = discord.Embed(
            title="🎯 Zahlen-Fortsetzungsspiel - Setup",
            description=f"✅ Das Spiel wurde für den Kanal {channel.mention} konfiguriert und ist jetzt **aktiv**.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await channel.send("🚀 **Das Zahlen-Fortsetzungsspiel beginnt jetzt hier! Startet mit der Zahl 1!**")

    @numbers_game_group.command(name="toggle", description="Aktiviert oder deaktiviert das Spiel.")
    async def toggle(self, interaction: discord.Interaction):
        config = self.get_config()
        config['enabled'] = not config['enabled']
        self.save_config(config)
        
        status = "aktiviert" if config['enabled'] else "deaktiviert"
        color = discord.Color.green() if config['enabled'] else discord.Color.red()
        embed = discord.Embed(
            title=f"🎯 Spiel wurde {status}",
            description=f"Das Zahlen-Fortsetzungsspiel ist jetzt **{status}**.",
            color=color
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @numbers_game_group.command(name="status", description="Zeigt den aktuellen Spielstatus an.")
    async def status(self, interaction: discord.Interaction):
        if not self.db_conn:
            await interaction.response.send_message("DB-Fehler, Status kann nicht abgerufen werden.", ephemeral=True)
            return

        config = self.get_config()
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(user_id) FROM numbers_game_players")
        player_count_row = cursor.fetchone()
        player_count = player_count_row[0] if player_count_row else 0

        embed = discord.Embed(title="🎯 Zahlen-Fortsetzungsspiel - Status", color=discord.Color.blue())
        embed.add_field(name="Status", value="🟢 Aktiviert" if config.get('enabled') else "🔴 Deaktiviert", inline=True)
        embed.add_field(name="Kanal", value=f"<#{config.get('channel_id')}>" if config.get('channel_id') else "Nicht gesetzt", inline=True)
        embed.add_field(name="Aktuelle Zahl", value=config.get('current_number', 0), inline=True)
        embed.add_field(name="Teilnehmer", value=player_count, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(NumbersGame(bot))