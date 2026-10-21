# bot.py
import discord
from discord.ext import commands
import psutil
import os
import glob
import datetime
from database import get_setting, save_setting

class PhoenixBot(commands.Bot):
    def __init__(self, config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config
        self.start_time = datetime.datetime.now()
        self.process = psutil.Process(os.getpid())
        self.load_presence_from_db()

    def load_presence_from_db(self):
        """Lädt den gespeicherten Status aus der DB und setzt die Bot-Variablen."""
        status_str = get_setting('status', 'online')
        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible
        }
        self.current_status = status_map.get(status_str, discord.Status.online)

        activity_type_str = get_setting('activity_type', 'playing')
        activity_name = get_setting('activity_name', 'Phoenix Dashboard')
        
        activity = None
        if activity_name:
            if activity_type_str == "playing":
                activity = discord.Game(name=activity_name)
            elif activity_type_str == "watching":
                activity = discord.Activity(type=discord.ActivityType.watching, name=activity_name)
            elif activity_type_str == "listening":
                activity = discord.Activity(type=discord.ActivityType.listening, name=activity_name)
            elif activity_type_str == "streaming":
                activity = discord.Streaming(name=activity_name, url="https://www.twitch.tv/placeholder")
        
        self.current_activity = activity

    async def setup_hook(self):
        """Sucht rekursiv nach Cogs und lädt sie."""
        print("INFO: Lade Cogs...")
        
        cog_files = glob.glob('cogs/**/*.py', recursive=True)
        for file_path in cog_files:
            module_path = file_path.replace('\\', '.').replace('/', '.').replace('.py', '')
            
            # --- DIES IST DIE KORREKTUR ---
            # Ignoriere alle Web-Dateien, da sie keine Cogs sind.
            if 'web' in module_path:
                continue
            
            try:
                await self.load_extension(module_path)
                print(f"  -> Cog '{module_path}' erfolgreich geladen.")
            except Exception as e:
                print(f"ERROR: Fehler beim Laden von {module_path}: {e}")
        
        print("-------------------")
        
        dev_config = self.config.get("development", {})
        clear_commands = dev_config.get("clear_commands_on_startup", False)
        dev_guild_id = dev_config.get("development_guild_id")
        
        if clear_commands and dev_guild_id:
            try:
                guild = discord.Object(id=dev_guild_id)
                print(f"DEV MODE: Synchronisiere Befehle für Test-Server {dev_guild_id}...")
                commands_synced = await self.tree.sync(guild=guild)
                print(f"DEV MODE: {len(commands_synced)} Befehle erfolgreich für den Test-Server synchronisiert.")
            except discord.errors.Forbidden:
                 print("\nCRITICAL ERROR: 'Missing Access' (Fehler 50001). Der Bot hat keine Berechtigung, Slash-Befehle zu verwalten.")
                 await self.close()
            except Exception as e:
                 print(f"Ein Fehler bei der Befehlssynchronisation ist aufgetreten: {e}")
                 await self.close()
        else:
            print("PRODUCTION MODE: Synchronisiere globale Befehle...")
            commands_synced = await self.tree.sync()
            print(f"PRODUCTION MODE: {len(commands_synced)} globale Befehle synchronisiert.")

    async def on_ready(self):
        """Wird ausgeführt, wenn der Bot erfolgreich mit Discord verbunden ist."""
        print(f'INFO: {self.user.name} ist online und bereit!')
        print(f'INFO: Verbunden mit {len(self.guilds)} Servern.')
        print("-------------------")
        await self.change_presence(status=self.current_status, activity=self.current_activity)

    def get_stats(self):
        """Sammelt alle Statistiken für das Web-Dashboard."""
        uptime = str(datetime.datetime.now() - self.start_time).split('.')[0]
        total_users = sum(guild.member_count for guild in self.guilds) if self.is_ready() else 0
        loaded_cogs = list(self.cogs.keys())
        bot_ram_usage = self.process.memory_info().rss / (1024 * 1024)
        bot_cpu_usage = self.process.cpu_percent(interval=0.1)
        server_ram = psutil.virtual_memory()
        server_cpu = psutil.cpu_percent(interval=0.1)
        server_disk = psutil.disk_usage('/')
        
        return {
            "uptime": uptime, "guild_count": len(self.guilds), "total_users": total_users,
            "loaded_cogs": loaded_cogs, "bot_ram_mb": f"{bot_ram_usage:.2f}", "bot_cpu_percent": bot_cpu_usage,
            "server_ram_percent": server_ram.percent, "server_cpu_percent": server_cpu, "server_disk_percent": server_disk.percent
        }
        
    async def update_presence(self, status_str: str, activity_type_str: str, activity_name: str):
        """Aktualisiert den Online-Status, die Aktivität UND speichert sie in der Datenbank."""
        if status_str:
            save_setting('status', status_str)
        if activity_type_str:
            save_setting('activity_type', activity_type_str)
        save_setting('activity_name', activity_name or '')
        
        self.load_presence_from_db()
        
        await self.change_presence(status=self.current_status, activity=self.current_activity)