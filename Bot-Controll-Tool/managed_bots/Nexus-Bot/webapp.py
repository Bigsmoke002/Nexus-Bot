# webapp.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify, Blueprint
import os
import signal
import discord
import asyncio
import json
import glob
from database import (get_recent_logs, get_messages_for_channel, consume_auth_token, get_plugin_permissions, 
                      add_plugin_permission, remove_plugin_permission, check_user_permission_for_plugin)
from pathlib import Path
from config_handler import save_config, load_config as load_initial_config

app = Flask(__name__)
bot_instance = None
app_config = load_initial_config()
app.secret_key = app_config.get('secret_key')

def get_web_plugins(fetch_from_config=True):
    """Hilfsfunktion, um Web-Plugins dynamisch zu erkennen und ihre Einstellungen zu laden."""
    web_files = glob.glob('cogs/**/*_web.py', recursive=True)
    plugins = []
    
    plugin_settings = app_config.get('web_plugin_settings', {}) if fetch_from_config else {}

    for file in web_files:
        module_name = file.replace('\\', '.').replace('/', '.').replace('.py', '')
        try:
            module = __import__(module_name, fromlist=['blueprint'])
            if hasattr(module, 'blueprint'):
                plugin_name = module.blueprint.name
                
                # Hole Einstellungen aus der Config, mit Fallbacks
                settings = plugin_settings.get(plugin_name, {'enabled': True, 'public': False})
                is_enabled = settings.get('enabled', True)
                is_public_from_config = settings.get('public', False)
                
                # Der 'is_public' Wert aus dem Blueprint-Objekt dient nur als initialer Standardwert
                is_public_from_blueprint = getattr(module.blueprint, 'is_public', False)
                
                plugins.append({
                    'name': plugin_name,
                    'display_name': getattr(module.blueprint, 'display_name', plugin_name.replace("_web", "").replace("verify", "Verification").capitalize()),
                    'is_enabled': is_enabled,
                    'is_public': is_public_from_config or is_public_from_blueprint,
                    # Hinzufügen des URL-Präfixes für die Navigation
                    'url_prefix': Path(file).parent.name
                })
        except Exception as e:
            print(f"WARNUNG beim Analysieren von {module_name}: {e}")
            pass
    return plugins

def register_cog_blueprints(app):
    """Sucht Plugins, prüft ob sie aktiviert sind und registriert ihre Blueprints bei Flask."""
    plugin_settings = app_config.get('web_plugin_settings', {})
    cog_web_files = glob.glob('cogs/**/*_web.py', recursive=True)
    
    for file_path in cog_web_files:
        module_name = file_path.replace('\\', '.').replace('/', '.').replace('.py', '')
        try:
            module = __import__(module_name, fromlist=['blueprint'])
            if hasattr(module, 'blueprint') and isinstance(module.blueprint, Blueprint):
                plugin_blueprint_name = module.blueprint.name
                
                if plugin_settings.get(plugin_blueprint_name, {}).get('enabled', True):
                    # === ANPASSUNG HIER ===
                    # Wir extrahieren den Ordnernamen des Plugins, um ihn als URL-Präfix zu verwenden.
                    # Beispiel: 'cogs/VoiceCreator/_web.py' -> 'VoiceCreator'
                    plugin_folder_name = Path(file_path).parent.name
                    url_prefix = f'/{plugin_folder_name}'
                    
                    # Registriere das Blueprint mit dem dynamischen Präfix
                    app.register_blueprint(module.blueprint, url_prefix=url_prefix)
                    print(f"INFO: Web-Routen aus {module_name} unter '{url_prefix}' bei Flask registriert.")
                else:
                    print(f"INFO: Web-Routen aus {module_name} sind deaktiviert und werden nicht geladen.")
        except Exception as e:
            print(f"FEHLER beim Laden der Web-Routen aus {module_name}: {e}")

@app.context_processor
def inject_sidebar_data():
    guilds = []
    if bot_instance and bot_instance.is_ready():
        guilds = sorted(bot_instance.guilds, key=lambda g: g.name.lower())
    
    # Zeige nur aktivierte, nicht-öffentliche Plugins in der Sidebar an
    plugin_pages = [p for p in get_web_plugins() if p['is_enabled'] and not p['is_public']]
    
    return dict(all_guilds=guilds, custom_pages=[], web_plugins_nav=plugin_pages)

@app.before_request
def require_login():
    """Die zentrale Sicherheitsprüfung, die zwischen lokalem und externem Zugriff unterscheidet."""
    public_endpoints = ['static', 'auth_login']
    if request.endpoint in public_endpoints:
        return

    # --- KORREKTUR HIER: '1227.0.0.1' zu '127.0.0.1' geändert ---
    is_local = request.remote_addr in ('127.0.0.1', '::1')

    if is_local:
        if request.endpoint == 'login':
            return
        if session.get('is_local_admin'):
            return
        return redirect(url_for('login'))
    else: # Externer Zugriff
        if request.blueprint:
            plugin_settings = app_config.get('web_plugin_settings', {})
            blueprint_is_public = plugin_settings.get(request.blueprint, {}).get('public', False)
            if blueprint_is_public:
                return

        if not session.get('logged_in'):
            return "<h1>Zugriff verweigert</h1><p>Bitte authentifiziere dich über das Access-Panel im Discord.</p>", 403

        guild_id = session.get('guild_id')
        guild = bot_instance.get_guild(guild_id) if guild_id else None
        member = guild.get_member(session['user_id']) if guild else None

        if not member:
            session.clear()
            return "<h1>Sitzung abgelaufen</h1><p>Deine Sitzung war ungültig. Bitte authentifiziere dich erneut.</p>", 403

        admin_only_endpoints = ['manage_permissions', 'config', 'manage_web_plugins']
        if request.endpoint in admin_only_endpoints:
            abort(403)

        if request.blueprint and not plugin_settings.get(request.blueprint, {}).get('public', False):
            if not check_user_permission_for_plugin(member, request.blueprint):
                abort(403)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Diese Route ist nur für lokale Admin-Logins."""
    if request.remote_addr not in ('127.0.0.1', '::1'):
        abort(404)

    if session.get('is_local_admin'):
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        password = load_initial_config().get('dashboard_password')
        if request.form.get('password') == password:
            session.clear()
            session['is_local_admin'] = True
            session['user_id'] = 'local_admin'
            flash('Erfolgreich als lokaler Admin angemeldet!', 'success')
            return redirect(url_for('dashboard'))
        else: 
            flash('Falsches Passwort!', 'danger')
    return render_template('login.html')

@app.route('/auth/login')
def auth_login():
    """Die Weiche für den sicheren externen Login via Discord-Token."""
    token = request.args.get('token')
    target_plugin = request.args.get('target')
    if not token or not target_plugin:
        abort(400)

    token_data = consume_auth_token(token)
    if not token_data:
        return "<h1>Zugriff verweigert</h1><p>Dein Link ist ungültig oder abgelaufen.</p>", 403

    session.clear()
    session['logged_in'] = True
    session['user_id'] = token_data['user_id']
    session['guild_id'] = token_data['guild_id']
    
    try:
        # Hier wird jetzt der Blueprint-Name verwendet, der mit dem Ordnernamen übereinstimmen sollte
        target_url = url_for(f"{target_plugin}.index")
        return redirect(target_url)
    except Exception as e:
        print(e)
        return f"<h1>Fehler</h1><p>Das Ziel-Plugin '{target_plugin}' konnte nicht gefunden werden.</p>", 500

@app.route('/logout')
def logout():
    session.clear()
    return "<h1>Ausgeloggt</h1><p>Du wurdest erfolgreich abgemeldet.</p>"

@app.route('/')
def dashboard():
    return render_template('dashboard.html', stats={}, logs=get_recent_logs())
    
@app.route('/permissions', methods=['GET', 'POST'])
def manage_permissions():
    if not session.get('is_local_admin'):
        abort(403) # Nur lokale Admins dürfen Berechtigungen sehen

    guild_id_str = session.get('selected_guild_id', str(bot_instance.config['development']['development_guild_id']))

    if 'guild_id' in request.args:
        session['selected_guild_id'] = request.args.get('guild_id')
        return redirect(url_for('manage_permissions'))

    guild = bot_instance.get_guild(int(guild_id_str)) if guild_id_str and guild_id_str.isdigit() else None

    if not guild:
        return f"<h1>Fehler</h1><p>Server nicht gefunden. Bitte wähle einen Server aus oder prüfe die <code>development_guild_id</code> in der config.json.</p>", 404

    if request.method == 'POST':
        plugin_name = request.form.get('plugin_name')
        entity_type = request.form.get('entity_type')
        entity_id = int(request.form.get('entity_id'))
        action = request.form.get('action')
        if action == 'add': add_plugin_permission(guild.id, plugin_name, entity_type, entity_id)
        elif action == 'remove': remove_plugin_permission(guild.id, plugin_name, entity_type, entity_id)
        return redirect(url_for('manage_permissions'))

    all_plugins = [p for p in get_web_plugins() if p['is_enabled'] and not p['is_public']]
    permissions = {p['name']: get_plugin_permissions(guild.id, p['name']) for p in all_plugins}
    roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)
    members = sorted(guild.members, key=lambda m: m.display_name.lower())
    
    return render_template('manage_permissions.html', 
                           plugins=all_plugins, 
                           permissions=permissions, 
                           roles=roles, 
                           members=members,
                           all_guilds=bot_instance.guilds,
                           current_guild=guild)

@app.route('/plugins')
def plugins(): 
    cogs = list(bot_instance.cogs.keys()) if bot_instance else []
    return render_template('plugins.html', cogs=cogs)

@app.route('/web-plugins', methods=['GET', 'POST'])
def manage_web_plugins():
    """Verwalten der Web-Plugin-Einstellungen."""
    if not session.get('is_local_admin'):
        abort(403)
        
    config_data = load_initial_config()
    web_plugin_settings = config_data.get('web_plugin_settings', {})

    if request.method == 'POST':
        all_plugins_raw = get_web_plugins(fetch_from_config=False)
        for plugin in all_plugins_raw:
            plugin_name = plugin['name']
            is_enabled = f'enabled_{plugin_name}' in request.form
            is_public = f'public_{plugin_name}' in request.form
            web_plugin_settings[plugin_name] = {'enabled': is_enabled, 'public': is_public}
        
        config_data['web_plugin_settings'] = web_plugin_settings
        save_config(config_data)
        flash('Web-Plugin-Einstellungen gespeichert! Ein Neustart ist erforderlich, um Änderungen zu übernehmen.', 'success')
        return redirect(url_for('manage_web_plugins'))

    all_plugins_with_settings = get_web_plugins(fetch_from_config=True)
    return render_template('manage_plugins.html', plugins=all_plugins_with_settings)

@app.route('/config', methods=['GET', 'POST'])
def config():
    if not session.get('is_local_admin'):
        abort(403)

    if request.method == 'POST':
        current_config = load_initial_config()
        current_config['bot_prefix'] = request.form.get('bot_prefix', '!')
        if 'dashboard_password' in request.form and request.form['dashboard_password']: current_config['dashboard_password'] = request.form['dashboard_password']
        current_config['crash_handler']['auto_restart'] = 'auto_restart' in request.form
        current_config['crash_handler']['max_restarts'] = int(request.form.get('max_restarts', 5))
        current_config['crash_handler']['restart_delay_seconds'] = int(request.form.get('restart_delay_seconds', 10))
        save_config(current_config)
        flash('Konfiguration gespeichert!', 'success')
        return redirect(url_for('config'))
    display_config = load_initial_config()
    return render_template('config.html', config=display_config)

@app.route('/status', methods=['GET', 'POST'])
def status():
    if not bot_instance or not bot_instance.is_ready():
        flash("Der Bot ist noch nicht bereit.", "warning")
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        status_str = request.form.get("status")
        activity_type = request.form.get("activity_type")
        activity_name = request.form.get("activity_name")
        coro = bot_instance.update_presence(status_str, activity_type, activity_name)
        asyncio.run_coroutine_threadsafe(coro, bot_instance.loop)
        flash("Bot-Status wurde aktualisiert!", "success")
        return redirect(url_for('status'))
    return render_template('status.html', current_status=bot_instance.current_status, current_activity=bot_instance.current_activity)

@app.route('/docs')
def docs():
    return render_template('docs.html')

@app.route('/restart', methods=['POST'])
def restart(): 
    flash('Bot-Neustart wurde eingeleitet...', 'warning')
    os.kill(os.getppid(), signal.SIGTERM)
    return redirect(url_for('dashboard'))

@app.route('/page/<string:page_id>')
def view_page(page_id):
    page_file = Path(f'pages/{page_id}.json')
    if not page_file.exists(): abort(404)
    try:
        with open(page_file, 'r', encoding='utf-8') as f: data = json.load(f)
        return render_template('page.html', page_name=data.get('name', page_id), iframe_url=data.get('url'))
    except Exception: abort(500)

@app.route('/guild/<int:guild_id>')
def view_guild(guild_id):
    if not bot_instance or not bot_instance.is_ready(): abort(503)
    guild = bot_instance.get_guild(guild_id)
    if not guild: abort(404)
    channels = sorted([c for c in guild.channels if isinstance(c, discord.TextChannel)], key=lambda x: x.position)
    return render_template('guild.html', guild=guild, channels=channels)

@app.route('/channel/<int:channel_id>')
def view_channel(channel_id):
    if not bot_instance or not bot_instance.is_ready(): abort(503)
    channel = bot_instance.get_channel(channel_id)
    if not channel or not isinstance(channel, discord.TextChannel): abort(404)
    messages = get_messages_for_channel(channel_id, limit=100)
    return render_template('channel.html', channel=channel, messages=messages)

@app.route('/api/stats')
def api_stats():
    if bot_instance and bot_instance.is_ready():
        stats = bot_instance.get_stats()
        return jsonify({"status": "online", "data": stats})
    else:
        return jsonify({"status": "starting", "message": "Bot fährt hoch, bitte warten..."})

def run_app(bot, config):
    global bot_instance, app_config
    bot_instance = bot
    app_config = config
    if not os.path.exists('pages'): 
        os.makedirs('pages')
    register_cog_blueprints(app)
    # Port 5001, damit es nicht mit dem Bot-Control-Tool (Port 5000) kollidiert
    app.run(host=config.get('web_host', '0.0.0.0'), port=int(config.get('web_port', 5001)), use_reloader=False, debug=False)