import os
from .cog import VRChatControlCog
from .__web import create_blueprint
from .vrc_manager import VRCManager

# Da die Web-App nicht am bot-Objekt hängt, importieren wir sie direkt.
# Dein Log "Serving Flask app 'webapp'" legt nahe, dass sie so verfügbar ist.
from webapp import app 

async def setup(bot):
    """
    Diese Funktion wird aufgerufen, wenn das Plugin geladen wird.
    Sie initialisiert den VRCManager, den Web-Blueprint und den Discord-Cog.
    """
    # Datenpfad für das Plugin sicherstellen
    data_path = os.path.join(os.path.dirname(__file__), 'data')
    if not os.path.exists(data_path):
        os.makedirs(data_path)

    # 1. Erstelle eine Instanz des VRCManagers, der die gesamte Logik enthält.
    manager = VRCManager(data_path=data_path)

    # 2. Erstelle den Flask-Blueprint für das Web-Dashboard.
    vrc_blueprint = create_blueprint(manager)

    # 3. Registriere den Blueprint bei der importierten Flask-App.
    # Dies ist die wichtigste Änderung, um den AttributeError zu beheben.
    app.register_blueprint(vrc_blueprint)

    # 4. Initialisiere und füge den Discord-Cog zum Bot hinzu.
    # VRChatControlCog ist eine app_commands.Group (kein Cog) und wird daher direkt im Command-Tree registriert
    bot.tree.add_command(VRChatControlCog(bot, manager))