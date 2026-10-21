# config_handler.py
import json
import os
import secrets

CONFIG_FILE = 'config.json'

DEFAULT_CONFIG = {
    "discord_token": "DEIN_DISCORD_BOT_TOKEN_HIER",
    "bot_prefix": "!",
    "dashboard_password": "admin",
    "secret_key": secrets.token_hex(24),
    "base_url": "http://127.0.0.1:5001",
    "web_host": "0.0.0.0",
    "web_port": 5001,
    "web_plugin_settings": {},
    "crash_handler": {
        "auto_restart": True,
        "max_restarts": 5,
        "restart_delay_seconds": 10
    },
    "development": {
        "clear_commands_on_startup": True,
        "development_guild_id": 0
    }
}

def _deep_update(source, overrides):
    """
    Aktualisiert ein verschachteltes Dictionary.
    """
    for key, value in overrides.items():
        if isinstance(value, dict) and key in source:
            source[key] = _deep_update(source.get(key, {}), value)
        else:
            source[key] = value
    return source

def load_config():
    """
    Lädt die config.json. Wenn sie nicht existiert, wird sie erstellt.
    Fehlende Schlüssel werden aus der DEFAULT_CONFIG nachgetragen.
    """
    if not os.path.exists(CONFIG_FILE):
        print("INFO: config.json nicht gefunden. Erstelle eine neue mit Standardwerten.")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    print("INFO: Lade Konfiguration aus config.json...")
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        try:
            user_config = json.load(f)
        except json.JSONDecodeError:
            print("WARNUNG: config.json ist fehlerhaft. Erstelle eine neue.")
            save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    config = _deep_update(config, user_config)
    
    if 'web_plugin_settings' not in config:
        config['web_plugin_settings'] = {}
    if 'base_url' not in config:
        config['base_url'] = "http://127.0.0.1:5001"

    save_config(config)
    
    return config

def save_config(config_data):
    """Speichert die Konfiguration in die config.json."""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=4)