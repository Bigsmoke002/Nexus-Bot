# run.py
import threading
import discord
from bot import PhoenixBot
from webapp import run_app
from database import init_db
from config_handler import load_config

# Lade die Konfiguration sicher über den Handler
config = load_config()

# Initialisiere die Datenbank
init_db()

# Aktiviere alle Intents
intents = discord.Intents.all()

# Übergebe die geladene Konfiguration an den Bot
bot = PhoenixBot(config=config, command_prefix=config['bot_prefix'], intents=intents)

if __name__ == "__main__":
    # Übergebe die Konfiguration auch an die Web-App
    webapp_thread = threading.Thread(target=run_app, args=(bot, config))
    webapp_thread.daemon = True
    webapp_thread.start()

    token = config.get("discord_token")
    if not token or "DEIN_DISCORD_BOT_TOKEN_HIER" in token:
        print("\n!!! WICHTIG !!!")
        print("Bitte trage deinen Discord-Bot-Token in die neu erstellte 'config.json' ein und starte den Bot erneut.")
    else:
        try:
            bot.run(token)
        except discord.errors.LoginFailure:
            print("FEHLER: Ungültiger Discord-Token. Bitte überprüfe die config.json.")
        except discord.errors.PrivilegedIntentsRequired:
            print("FEHLER: Privileged Intents sind nicht aktiviert. Bitte aktiviere sie im Discord Developer Portal.")
        except Exception as e:
            print(f"Ein unerwarteter Fehler beim Bot-Start ist aufgetreten: {e}")