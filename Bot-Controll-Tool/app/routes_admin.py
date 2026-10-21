# app/routes_admin.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import os
import shutil
import zipfile
from .models import db, User, Bot

admin = Blueprint('admin', __name__, url_prefix='/admin')

# Sicherstellen, dass nur Admins auf diese Routen zugreifen können
@admin.before_request
@login_required
def check_is_admin():
    if not current_user.is_admin:
        return "Unauthorized", 403

BOTS_DIR = os.path.abspath('managed_bots')
if not os.path.exists(BOTS_DIR):
    os.makedirs(BOTS_DIR)

@admin.route('/dashboard')
def dashboard():
    # Scanne das BOTS_DIR nach nicht registrierten Bots
    registered_bot_paths = [bot.path for bot in Bot.query.all()]
    unregistered_bots = []
    for item in os.listdir(BOTS_DIR):
        item_path = os.path.join(BOTS_DIR, item)
        if os.path.isdir(item_path) and item_path not in registered_bot_paths:
            unregistered_bots.append({'name': item, 'path': item_path})

    users = User.query.all()
    bots = Bot.query.all()
    return render_template('admin_dashboard.html', users=users, bots=bots, unregistered_bots=unregistered_bots)

@admin.route('/user/create', methods=['POST'])
def create_user():
    username = request.form.get('username')
    password = request.form.get('password')
    is_admin = 'is_admin' in request.form

    if User.query.filter_by(username=username).first():
        flash(f"Benutzer '{username}' existiert bereits.", 'danger')
    else:
        new_user = User(
            username=username,
            password=generate_password_hash(password, method='pbkdf2:sha256'),
            is_admin=is_admin
        )
        db.session.add(new_user)
        db.session.commit()
        flash(f"Benutzer '{username}' erfolgreich erstellt.", 'success')
    return redirect(url_for('admin.dashboard'))

@admin.route('/bot/add', methods=['POST'])
def add_bot():
    bot_name = request.form.get('bot_name')
    owner_id = request.form.get('owner_id')
    uploaded_file = request.files.get('bot_zip')

    if not all([bot_name, owner_id, uploaded_file]):
        flash("Alle Felder sind erforderlich.", 'danger')
        return redirect(url_for('admin.dashboard'))
    
    bot_path = os.path.join(BOTS_DIR, secure_filename(bot_name))

    if os.path.exists(bot_path):
        flash(f"Ein Ordner mit dem Namen '{bot_name}' existiert bereits.", 'danger')
        return redirect(url_for('admin.dashboard'))

    # Ordner erstellen und Zip entpacken
    os.makedirs(bot_path)
    try:
        with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
            zip_ref.extractall(bot_path)
    except Exception as e:
        shutil.rmtree(bot_path) # Aufräumen bei Fehler
        flash(f"Fehler beim Entpacken der ZIP-Datei: {e}", 'danger')
        return redirect(url_for('admin.dashboard'))

    # Bot in der DB registrieren
    new_bot = Bot(name=bot_name, path=bot_path, owner_id=owner_id)
    db.session.add(new_bot)
    db.session.commit()
    flash(f"Bot '{bot_name}' erfolgreich erstellt und zugewiesen.", 'success')
    return redirect(url_for('admin.dashboard'))

@admin.route('/bot/register', methods=['POST'])
def register_bot():
    bot_name = request.form.get('bot_name')
    bot_path = request.form.get('bot_path')
    owner_id = request.form.get('owner_id')
    
    new_bot = Bot(name=bot_name, path=bot_path, owner_id=owner_id)
    db.session.add(new_bot)
    db.session.commit()
    flash(f"Bot '{bot_name}' erfolgreich registriert.", 'success')
    return redirect(url_for('admin.dashboard'))

@admin.route('/bot/delete/<int:bot_id>', methods=['POST'])
def delete_bot(bot_id):
    bot = Bot.query.get_or_404(bot_id)
    confirmation_name = request.form.get('confirmation_name')

    if bot.name != confirmation_name:
        flash("Bestätigungsname ist falsch.", 'danger')
        return redirect(url_for('admin.dashboard'))
    
    try:
        if os.path.exists(bot.path):
            shutil.rmtree(bot.path)
        
        db.session.delete(bot)
        db.session.commit()
        flash(f"Bot '{bot.name}' und alle zugehörigen Dateien wurden gelöscht.", 'success')
    except Exception as e:
        flash(f"Fehler beim Löschen des Bots: {e}", 'danger')

    return redirect(url_for('admin.dashboard'))