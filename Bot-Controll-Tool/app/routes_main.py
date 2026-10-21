# app/routes_main.py
from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from . import socketio
from .process_manager import process_manager

main = Blueprint('main', __name__)

@main.route('/')
@login_required
def dashboard():
    # Admins sehen alle Bots, normale User nur ihre eigenen
    bots = current_user.bots if not current_user.is_admin else Bot.query.all()
    return render_template('dashboard.html', bots=bots)

# SocketIO Events für die Interaktion mit dem Frontend
@socketio.on('get_status')
@login_required
def handle_get_status(data):
    bot_id = data.get('bot_id')
    status = process_manager.get_status(bot_id)
    socketio.emit('status_update', {'bot_id': bot_id, 'status': status})

@socketio.on('start_bot')
@login_required
def handle_start_bot(data):
    bot_id = data.get('bot_id')
    bot = Bot.query.get(bot_id)
    if bot and (bot.owner_id == current_user.id or current_user.is_admin):
        process_manager.start_bot(bot)

@socketio.on('stop_bot')
@login_required
def handle_stop_bot(data):
    bot_id = data.get('bot_id')
    bot = Bot.query.get(bot_id)
    if bot and (bot.owner_id == current_user.id or current_user.is_admin):
        process_manager.stop_bot(bot_id)

@main.route('/get_initial_logs/<int:bot_id>')
@login_required
def get_initial_logs(bot_id):
    """Gibt die bereits vorhandenen Logs für einen Bot zurück."""
    bot = Bot.query.get_or_404(bot_id)
    if bot.owner_id != current_user.id and not current_user.is_admin:
        return jsonify({"error": "Unauthorized"}), 403
    
    logs = process_manager.get_logs(bot_id)
    return jsonify(logs)

# Lade die Bot-Modelle, damit sie in dieser Datei bekannt sind
from .models import Bot