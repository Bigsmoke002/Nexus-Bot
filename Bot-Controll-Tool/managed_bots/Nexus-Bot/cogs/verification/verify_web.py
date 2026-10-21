# cogs/verification/verify_web.py
from flask import Blueprint, render_template, request
import sqlite3
import os
from datetime import datetime

blueprint = Blueprint('verify_web', __name__, template_folder='templates')

plugin_name = "Verification"
data_folder = os.path.join('plugin_data', plugin_name)
db_path = os.path.join(data_folder, 'verify.db')

@blueprint.route('/verify', methods=['GET'])
def verify_page():
    user_id = request.args.get('user')
    lang = request.args.get('lang', 'de')
    return render_template('verify.html', user_id=user_id, lang=lang)

@blueprint.route('/verify/submit', methods=['POST'])
def verify_submit():
    user_id = request.form.get('user_id')
    lang = request.form.get('lang', 'de')
    fingerprint_id = request.form.get('fingerprint_id', 'N/A')
    cookies_enabled_str = request.form.get('cookies_enabled', 'false')
    cookies_enabled = cookies_enabled_str == 'true'
    
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    os.makedirs(data_folder, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT guild_id FROM config LIMIT 1")
        guild_id_row = cursor.fetchone()
        if not guild_id_row:
             return "<h1>Fehler</h1><p>Bot ist nicht konfiguriert.</p>"

        guild_id = guild_id_row[0]
        verified_at = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT OR REPLACE INTO verifications 
            (user_id, guild_id, verified_at, ip_address, user_agent, fingerprint_id, cookies_enabled) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, guild_id, verified_at, ip_address, user_agent, fingerprint_id, cookies_enabled))
        conn.commit()
    
    if lang == 'de':
        return "<h1>Verifizierung erfolgreich!</h1><p>Du kannst dieses Fenster jetzt schließen und zu Discord zurückkehren.</p>"
    else:
        return "<h1>Verification Successful!</h1><p>You can now close this window and return to Discord.</p>"