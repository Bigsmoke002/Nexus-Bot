# cogs/VoiceCreator/web.py
from flask import Blueprint, render_template, request, jsonify
import sqlite3
import json

# WICHTIG: Der Blueprint muss einen eindeutigen Namen haben
blueprint = Blueprint('voice_creator_web', __name__,
                      template_folder='templates',
                      static_folder='static',
                      static_url_path='/cogs/VoiceCreator/static')

# Diese Variable wird in der Haupt-Webapp mit dem Bot-Objekt belegt
blueprint.bot = None 
blueprint.db_path = "plugin_data/VoiceCreator/voicecreate.db"

def get_db():
    return sqlite3.connect(blueprint.db_path)

@blueprint.route('/')
def index():
    return render_template('voice_creator_index.html')

# --- API-ROUTEN ---

@blueprint.route('/api/join-channels', methods=['GET'])
def get_join_channels():
    with get_db() as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT id, category_id as categoryId, channel_format as channelFormat, use_sequential as useSequential FROM join_channels")
        rows = cur.fetchall()
        # Konvertiere 0/1 zu boolean für JSON
        channels = [dict(row, useSequential=bool(row['useSequential'])) for row in rows]
        return jsonify(channels)

@blueprint.route('/api/join-channels', methods=['POST'])
def add_join_channel():
    data = request.json
    with get_db() as con:
        con.execute("INSERT OR REPLACE INTO join_channels (id, category_id, channel_format, use_sequential) VALUES (?, ?, ?, ?)",
                    (data['joinChannelId'], data['categoryId'], data['channelFormat'], data['useSequential']))
        con.commit()
    return jsonify({'success': True})

@blueprint.route('/api/join-channels/<channel_id>', methods=['DELETE'])
def remove_join_channel(channel_id):
    with get_db() as con:
        con.execute("DELETE FROM join_channels WHERE id = ?", (channel_id,))
        con.commit()
    return jsonify({'success': True})

@blueprint.route('/api/join-channel/<channel_id>', methods=['PUT'])
def update_join_channel(channel_id):
    data = request.json
    with get_db() as con:
        con.execute("UPDATE join_channels SET category_id = ?, channel_format = ?, use_sequential = ? WHERE id = ?",
                    (data['categoryId'], data['channelFormat'], data['useSequential'], channel_id))
        con.commit()
    return jsonify({'success': True})

@blueprint.route('/api/channel-names', methods=['GET'])
def get_channel_names():
    ids_str = request.args.get('ids', '')
    ids = [int(i) for i in ids_str.split(',') if i.isdigit()]
    names = {}
    for channel_id in ids:
        channel = blueprint.bot.get_channel(channel_id)
        names[str(channel_id)] = channel.name if channel else 'Unknown'
    return jsonify(names)

@blueprint.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.json
    with get_db() as con:
        for key, value in data.items():
            con.execute("UPDATE config SET value = ? WHERE key = ?", (str(value), key))
        con.commit()
    # Lade die Konfiguration im Cog neu
    blueprint.bot.loop.create_task(blueprint.bot.get_cog('VoiceCreator').load_config_to_cache())
    return jsonify({'success': True})
    
@blueprint.route('/api/reset-counter', methods=['POST'])
def reset_counter():
    with get_db() as con:
        con.execute("UPDATE config SET value = '0' WHERE key = 'lastRoomNumber'")
        con.commit()
    blueprint.bot.get_cog('VoiceCreator').config_cache['lastRoomNumber'] = 0
    return jsonify({'success': True})

@blueprint.route('/api/message-delete-settings', methods=['GET'])
def get_message_delete_settings():
    settings = {}
    with get_db() as con:
        con.row_factory = sqlite3.Row
        # Allgemeine Einstellungen
        cur = con.cursor()
        cur.execute("SELECT key, value FROM config")
        config_rows = cur.fetchall()
        for row in config_rows:
             settings[row['key']] = row['value']

        # Kanal-spezifische Einstellungen
        cur.execute("SELECT slot, channel_id, minutes FROM message_delete_channels")
        channel_rows = cur.fetchall()
        for row in channel_rows:
            settings[row['slot']] = {'id': row['channel_id'], 'minutes': row['minutes']}
    return jsonify(settings)

@blueprint.route('/api/message-delete-channel', methods=['POST'])
def save_delete_channel():
    data = request.json
    with get_db() as con:
        con.execute("UPDATE message_delete_channels SET channel_id = ?, minutes = ? WHERE slot = ?",
                    (data['channelId'], data['minutes'], f"channel{data['slot']}"))
        con.commit()
    return jsonify({'success': True})
    
@blueprint.route('/api/channel-templates', methods=['GET'])
def get_templates():
    with get_db() as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT id, name, format FROM channel_templates")
        templates = [dict(row) for row in cur.fetchall()]
        return jsonify(templates)

@blueprint.route('/api/channel-templates', methods=['POST'])
def add_template():
    data = request.json
    with get_db() as con:
        con.execute("INSERT INTO channel_templates (name, format) VALUES (?, ?)", (data['name'], data['format']))
        con.commit()
    return jsonify({'success': True})

@blueprint.route('/api/channel-templates/<int:template_id>', methods=['PUT'])
def update_template(template_id):
    data = request.json
    with get_db() as con:
        con.execute("UPDATE channel_templates SET name = ?, format = ? WHERE id = ?", (data['name'], data['format'], template_id))
        con.commit()
    return jsonify({'success': True})

@blueprint.route('/api/channel-templates/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    with get_db() as con:
        con.execute("DELETE FROM channel_templates WHERE id = ?", (template_id,))
        con.commit()
    return jsonify({'success': True})