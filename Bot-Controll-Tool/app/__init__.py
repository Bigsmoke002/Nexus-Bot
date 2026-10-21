# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
import os
import json
import secrets
from werkzeug.security import generate_password_hash

db = SQLAlchemy()
socketio = SocketIO()
login_manager = LoginManager()

# --- NEUE SETUP-FUNKTION ---
def setup_initial_config():
    """Prüft und erstellt eine default config.json, falls nicht vorhanden."""
    config_path = 'config.json'
    if not os.path.exists(config_path):
        print("INFO: config.json nicht gefunden. Erstelle eine Standard-Konfiguration...")
        
        default_config = {
            "dashboard_password": "admin",
            "secret_key": secrets.token_hex(32)
        }
        
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=4)
        
        print("="*40)
        print("Eine neue 'config.json' wurde erstellt.")
        print("Standard-Admin-Login:")
        print("Username: admin")
        print("Password: admin")
        print("Bitte ändere das Passwort nach dem ersten Login!")
        print("="*40)
        return default_config
    
    with open(config_path, 'r') as f:
        return json.load(f)

def create_app():
    # Führe das Setup aus, bevor die App erstellt wird
    config = setup_initial_config()

    # Absoluter Pfad zur Instanz
    instance_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'instance'))
    if not os.path.exists(instance_path):
        os.makedirs(instance_path)

    app = Flask(__name__, instance_path=instance_path)
    app.config['SECRET_KEY'] = config.get('secret_key')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(instance_path, "controller.db")}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    socketio.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Registriere die Blueprints
    from .routes_auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)
    from .routes_main import main as main_blueprint
    app.register_blueprint(main_blueprint)
    from .routes_admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint)
    from .routes_files import files as files_blueprint
    app.register_blueprint(files_blueprint)

    with app.app_context():
        db.create_all()
        # Erstelle einen Admin-User basierend auf der Config, falls noch keiner existiert
        if not User.query.filter_by(username='admin').first():
            admin_password = config.get('dashboard_password', 'admin')
            new_admin = User(
                username='admin',
                password=generate_password_hash(admin_password, method='pbkdf2:sha256'),
                is_admin=True
            )
            db.session.add(new_admin)
            db.session.commit()
            print("INFO: Standard-Admin-Benutzer wurde in der Datenbank erstellt.")
            
    return app