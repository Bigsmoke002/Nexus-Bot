from flask import Blueprint, render_template, request, session, jsonify, abort
from werkzeug.security import check_password_hash
import time
from flask_sock import Sock

from .vrc_manager import VRCManager
import json

def create_blueprint(manager: VRCManager):
    vrc_bp = Blueprint('vrchat_control', __name__, template_folder='templates', url_prefix='/vrchat')
    sock = Sock(vrc_bp)

    def require_auth():
        if not session.get('authenticated'):
            abort(401, description="Nicht authentifiziert. Bitte einloggen.")

    @vrc_bp.route('/')
    def index():
        return render_template('vrchat_dashboard.html')

    @vrc_bp.route('/api/login', methods=['POST'])
    def login():
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        creds = manager.get_credentials(include_password=True)
        if not creds or creds.get('expires_at', 0) < time.time():
            return jsonify({"error": "Credentials abgelaufen oder nicht initialisiert."}), 401
            
        if username == creds.get('username') and check_password_hash(creds.get('hashed_password', ''), password):
            session['authenticated'] = True
            session['username'] = username
            manager.log_to_discord("Dashboard Login", f"User '{username}' hat sich erfolgreich eingeloggt.")
            return jsonify({"success": True})
        
        return jsonify({"error": "Ungültiger Benutzername oder Passwort."}), 401

    @vrc_bp.route('/api/logout', methods=['POST'])
    def logout():
        username = session.get('username', 'Unbekannt')
        session.clear()
        manager.log_to_discord("Dashboard Logout", f"User '{username}' hat sich ausgeloggt.")
        return jsonify({"success": True})

    @vrc_bp.route('/api/status')
    def api_status():
        # Dieser Endpoint wird auch für die initiale Prüfung der Authentifizierung verwendet
        if not session.get('authenticated'):
            return jsonify({"error": "Nicht authentifiziert"}), 401
        
        full_status = manager.get_full_system_info()
        return jsonify(full_status)

    @vrc_bp.route('/api/instance/<bot_id>/start', methods=['POST'])
    def start_instance(bot_id):
        require_auth()
        world_id = request.json.get('worldId')
        try:
            message = manager.start_vrchat_instance(bot_id, world_id, session.get('username', 'Dashboard'))
            return jsonify({"success": True, "message": message})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @vrc_bp.route('/api/instance/<bot_id>/stop', methods=['POST'])
    def stop_instance(bot_id):
        require_auth()
        try:
            message = manager.stop_vrchat_instance(bot_id, session.get('username', 'Dashboard'))
            return jsonify({"success": True, "message": message})
        except Exception as e:
            return jsonify({"error": str(e)}), 400
            
    @vrc_bp.route('/api/instance/<bot_id>/world', methods=['POST'])
    def set_world_id(bot_id):
        require_auth()
        world_id = request.json.get('worldId')
        if not world_id:
            return jsonify({"error": "World ID ist erforderlich."}), 400
        try:
            manager.set_instance_world_id(bot_id, world_id, session.get('username', 'Dashboard'))
            return jsonify({"success": True})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
            
    # Auto-Start API
    @vrc_bp.route('/api/auto-start/all', methods=['POST'])
    def auto_start_all():
        require_auth()
        world_preset = request.json.get('worldPreset')
        try:
            result = manager.start_all_bots_auto(world_preset, session.get('username', 'Dashboard'))
            return jsonify({
                "success": True, 
                "message": f"Auto-Start für {result['total_bots']} Bots gestartet",
                **result
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @vrc_bp.route('/api/auto-start/stop', methods=['POST'])
    def auto_start_stop():
        require_auth()
        try:
            result = manager.stop_auto_start(session.get('username', 'Dashboard'))
            return jsonify({
                "success": True,
                "message": f"Auto-Start gestoppt. {result['stopped_bots']} Bots übersprungen.",
                **result
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @vrc_bp.route('/api/auto-start/status')
    def auto_start_status():
        require_auth()
        return jsonify(manager.get_auto_start_status())

    # OSC API
    @vrc_bp.route('/api/osc/status')
    def osc_status():
        require_auth()
        if manager.osc_manager:
            return jsonify(manager.osc_manager.get_status())
        return jsonify({"connected": False, "error": "OSC Manager nicht initialisiert"})

    @vrc_bp.route('/api/osc/chatbox/send', methods=['POST'])
    def osc_send_chatbox():
        require_auth()
        data = request.json
        if manager.osc_manager:
            manager.osc_manager.send_chatbox_message(data['botId'], data['message'], data.get('immediate', True), data.get('notification', True))
            return jsonify({"success": True})
        return jsonify({"error": "OSC Manager nicht verfügbar"}), 400
        
    @vrc_bp.route('/api/osc/chatbox/send/multi', methods=['POST'])
    def osc_send_multi_chatbox():
        require_auth()
        data = request.json
        if manager.osc_manager:
            results = manager.osc_manager.send_multi_bot_chatbox_message(data['botIds'], data['message'], data.get('immediate', True), data.get('notification', True))
            return jsonify({"success": True, "results": results})
        return jsonify({"error": "OSC Manager nicht verfügbar"}), 400

    @vrc_bp.route('/api/osc/chatbox/loop/start', methods=['POST'])
    def osc_start_loop():
        require_auth()
        data = request.json
        if manager.osc_manager:
            manager.osc_manager.start_chatbox_loop(data['botId'], data.get('template'), data.get('interval', 5000), data.get('customMessage'))
            return jsonify({"success": True})
        return jsonify({"error": "OSC Manager nicht verfügbar"}), 400
        
    @vrc_bp.route('/api/osc/chatbox/loop/start/multi', methods=['POST'])
    def osc_start_multi_loop():
        require_auth()
        data = request.json
        if manager.osc_manager:
            loop_id = manager.osc_manager.start_multi_bot_chatbox_loop(data['botIds'], data.get('template'), data.get('interval', 5000), data.get('customMessage'), manager.instances)
            if loop_id:
                return jsonify({"success": True, "loopId": loop_id})
            return jsonify({"error": "Fehler beim Starten des Multi-Loops"}), 400
        return jsonify({"error": "OSC Manager nicht verfügbar"}), 400

    @vrc_bp.route('/api/osc/chatbox/loop/stop', methods=['POST'])
    def osc_stop_loop():
        require_auth()
        data = request.json
        if manager.osc_manager:
            if 'loopId' in data:
                manager.osc_manager.stop_multi_bot_chatbox_loop(data['loopId'])
            elif 'botId' in data:
                manager.osc_manager.stop_chatbox_loop(data['botId'])
            return jsonify({"success": True})
        return jsonify({"error": "OSC Manager nicht verfügbar"}), 400

    @vrc_bp.route('/api/osc/templates')
    def osc_templates():
        require_auth()
        if manager.osc_manager:
            return jsonify(manager.osc_manager.get_all_templates())
        return jsonify({"builtin": [], "custom": []})
        
    @vrc_bp.route('/api/osc/templates/custom', methods=['POST'])
    def osc_save_template():
        require_auth()
        data = request.json
        if manager.osc_manager:
            manager.osc_manager.save_custom_template(data['name'], data['content'], data.get('description', ''))
            return jsonify({"success": True})
        return jsonify({"error": "OSC Manager nicht verfügbar"}), 400

    @vrc_bp.route('/api/osc/templates/custom/<name>', methods=['DELETE'])
    def osc_delete_template(name):
        require_auth()
        if manager.osc_manager:
            if manager.osc_manager.delete_custom_template(name):
                return jsonify({"success": True})
            return jsonify({"error": "Template nicht gefunden"}), 404
        return jsonify({"error": "OSC Manager nicht verfügbar"}), 400

    # WebSocket
    @sock.route('/ws')
    def ws(ws):
        manager.register_ws_client(ws)
        try:
            # Sende initiales Update
            initial_data = manager.get_full_system_info()
            ws.send(json.dumps({'type': 'update', 'data': initial_data}))
            
            while True:
                # Halte die Verbindung offen
                message = ws.receive(timeout=60)
                if message is None: # Timeout
                    continue

        except Exception as e:
            # Client hat die Verbindung geschlossen
            pass
        finally:
            manager.unregister_ws_client(ws)
    
    return vrc_bp