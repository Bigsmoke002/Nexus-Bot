# run.py
import os
from app import create_app, socketio

app = create_app()

if __name__ == '__main__':
    # Starte die Flask-App mit SocketIO-Unterstützung
    # Standardmäßig nur lokal erreichbar (Datei-Editor + Standard-Login admin/admin); CONTROLLER_HOST=0.0.0.0 für Netzwerkzugriff
    socketio.run(app, host=os.environ.get('CONTROLLER_HOST', '127.0.0.1'), port=int(os.environ.get('CONTROLLER_PORT', 5000)), debug=False, allow_unsafe_werkzeug=True)