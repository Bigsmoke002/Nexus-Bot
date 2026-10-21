# app/routes_files.py
from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required, current_user
import os
from pathlib import Path
from .models import Bot

files = Blueprint('files', __name__, url_prefix='/files')

def is_safe_path(bot_base_path, requested_path):
    """
    Sicherheitsfunktion, um zu prüfen, ob ein Pfad innerhalb der erlaubten Grenzen liegt.
    Erlaubt sind nur der 'cogs'-Ordner und die 'config.json'.
    """
    base_path = Path(bot_base_path).resolve()
    req_path = Path(requested_path).resolve()

    # Erlaube den Zugriff auf config.json im Hauptverzeichnis des Bots
    config_path = base_path / 'config.json'
    if req_path == config_path:
        return True

    # Erlaube den Zugriff auf den 'cogs'-Ordner und dessen Unterverzeichnisse
    cogs_path = base_path / 'cogs'
    return cogs_path in req_path.parents or req_path == cogs_path

@files.route('/browse/<int:bot_id>')
@files.route('/browse/<int:bot_id>/<path:subpath>')
@login_required
def browse(bot_id, subpath=''):
    bot = Bot.query.get_or_404(bot_id)
    if not current_user.is_admin and bot.owner_id != current_user.id:
        abort(403)

    bot_root = Path(bot.path).resolve()
    requested_path = (bot_root / subpath).resolve()

    if not is_safe_path(bot_root, requested_path):
        abort(403, "Zugriff auf diesen Pfad ist nicht erlaubt.")
    
    if not requested_path.exists():
        abort(404, "Pfad nicht gefunden.")

    content = None
    items = []
    
    if requested_path.is_file():
        try:
            content = requested_path.read_text(encoding='utf-8')
        except Exception as e:
            content = f"Fehler beim Lesen der Datei: {e}"
    elif requested_path.is_dir():
        for item in requested_path.iterdir():
            items.append({
                'name': item.name,
                'is_dir': item.is_dir(),
                'path': item.relative_to(bot_root).as_posix() # as_posix() für Web-freundliche Slashes
            })

    # Erstelle eine Breadcrumb-Navigation
    breadcrumbs = []
    current_path = Path(subpath)
    for part in list(current_path.parents)[::-1] + [current_path]:
        if str(part) != '.':
             breadcrumbs.append({'name': part.name, 'path': part.as_posix()})

    return render_template(
        'file_browser.html', 
        bot=bot, 
        items=items, 
        content=content,
        current_path=subpath,
        breadcrumbs=breadcrumbs
    )

@files.route('/save/<int:bot_id>/<path:filepath>', methods=['POST'])
@login_required
def save_file(bot_id, filepath):
    bot = Bot.query.get_or_404(bot_id)
    if not current_user.is_admin and bot.owner_id != current_user.id:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    bot_root = Path(bot.path).resolve()
    file_to_save = (bot_root / filepath).resolve()

    if not is_safe_path(bot_root, file_to_save):
        return jsonify({"success": False, "message": "Zugriff verweigert."}), 403
        
    if file_to_save.is_dir():
        return jsonify({"success": False, "message": "Kann keinen Ordner speichern."}), 400

    new_content = request.json.get('content')
    try:
        file_to_save.write_text(new_content, encoding='utf-8')
        return jsonify({"success": True, "message": "Datei erfolgreich gespeichert."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Fehler beim Speichern: {e}"}), 500