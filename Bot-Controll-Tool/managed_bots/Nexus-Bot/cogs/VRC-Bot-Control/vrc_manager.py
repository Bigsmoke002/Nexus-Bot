import os
import json
import time
import subprocess
import platform
import psutil
import threading
import uuid
from werkzeug.security import generate_password_hash

from .osc_manager import OSCManager # <-- Diese Zeile verursacht den Fehler, wenn osc_manager.py fehlt

class VRCManager:
    def __init__(self, data_path):
        self.data_path = data_path
        self.config_file = os.path.join(data_path, 'web_config.json')
        self.instances_file = os.path.join(data_path, 'instances_config.json')
        self.credentials_file = os.path.join(data_path, 'credentials.json')

        self.config = {}
        self.instances = {}
        self.credentials = {}
        
        self.ws_clients = set()
        self.system_start_time = time.time() * 1000
        self.last_bot_start_time = 0
        
        self.is_auto_starting = False
        self.auto_start_queue = []
        self.auto_start_timeout_id = None
        self.lock = threading.Lock()

        self._load_config()
        self._load_instances()
        self._load_credentials()

        self.osc_manager = OSCManager(self.config.get('osc', {}).get('botPorts', {}), self.data_path)
        
        self.update_thread = threading.Thread(target=self._background_update_loop, daemon=True)
        self.update_thread.start()

    def _load_config(self):
        default_config = {
            "host": "0.0.0.0",
            "port": 4545,
            "maxBots": 5,
            "launchExePaths": {
                f"bot{i}": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\VRChat\\launch.exe" for i in range(1, 6)
            },
            "startupDelay": 180000,
            "worldPresets": {
                "Hub": "wrld_8b9b2990-7313-4430-9294-5e482036b483",
            },
            "osc": {
                "enabled": True,
                "inPort": 9001,
                "host": "127.0.0.1",
                "botPorts": { f"bot{i}": 9000 + (i-1)*2 for i in range(1, 6) }
            }
        }
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        else:
            self.config = default_config
            self._save_config()
    
    def _save_config(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4)
            
    def _load_instances(self):
        if os.path.exists(self.instances_file):
            with open(self.instances_file, 'r', encoding='utf-8') as f:
                self.instances = json.load(f)
            for bot_id, instance in self.instances.items():
                if instance.get('status') in ['running', 'starting', 'waiting_pid']:
                    instance['status'] = 'unknown' # Reset status on load
        else:
            max_bots = self.config.get('maxBots', 5)
            self.instances = {
                f"bot{i}": {
                    "name": f"VRChat Bot {i}", "worldId": "", "pid": None, "startTime": None,
                    "status": "stopped", "ram": "N/A", "cpu": "N/A", "uptime": 0
                } for i in range(1, max_bots + 1)
            }
        self._save_instances()
            
    def _save_instances(self):
        with self.lock:
            with open(self.instances_file, 'w', encoding='utf-8') as f:
                json.dump(self.instances, f, indent=4)
    
    def _load_credentials(self):
        if os.path.exists(self.credentials_file):
            with open(self.credentials_file, 'r', encoding='utf-8') as f:
                self.credentials = json.load(f)
        if not self.credentials or self.credentials.get('expires_at', 0) < time.time():
            self.generate_credentials()

    def generate_credentials(self):
        with self.lock:
            username = f'admin_{uuid.uuid4().hex[:6]}'
            password = uuid.uuid4().hex
            self.credentials = {
                'username': username,
                'password': password,
                'hashed_password': generate_password_hash(password),
                'created_at': time.time(),
                'expires_at': time.time() + (24 * 3600)
            }
            creds_to_save = self.credentials.copy()
            del creds_to_save['password'] # Do not save plain password
            with open(self.credentials_file, 'w', encoding='utf-8') as f:
                json.dump(creds_to_save, f, indent=4)
            self.log_to_discord('Credentials generiert', f"Neuer Username: {username}")
        return {'username': username, 'password': password}

    def get_credentials(self, include_password=False):
        if include_password:
             return self.credentials.copy()
        
        creds_safe = self.credentials.copy()
        if 'password' in creds_safe:
            del creds_safe['password']
        return creds_safe
        
    def log_to_discord(self, action, details, user="System"):
        print(f"[DISCORD LOG] User: {user} | Action: {action} | Details: {details}")

    def get_config(self):
        return self.config

    def get_all_instances_status(self):
        with self.lock:
            return self.instances.copy()

    def start_vrchat_instance(self, bot_id, world_id, user="System"):
        with self.lock:
            if bot_id not in self.instances:
                raise ValueError(f"Bot ID {bot_id} nicht gefunden.")
            if self.instances[bot_id]['status'] in ['running', 'starting', 'waiting_pid']:
                raise ValueError(f"{self.instances[bot_id]['name']} läuft bereits oder startet gerade.")
            
            launch_path = self.config.get('launchExePaths', {}).get(bot_id)
            if not launch_path or not os.path.exists(launch_path):
                raise FileNotFoundError(f"launch.exe Pfad für {bot_id} ('{launch_path}') nicht gefunden oder ungültig.")
                
            final_world_id = self.config.get('worldPresets', {}).get(world_id, world_id)
            if not final_world_id.startswith('wrld_'):
                raise ValueError("Ungültige World ID. Muss mit 'wrld_' beginnen oder ein gültiges Preset sein.")
            
            self.instances[bot_id]['worldId'] = final_world_id
            self.instances[bot_id]['status'] = 'starting'
            self.instances[bot_id]['pid'] = None
            self.instances[bot_id]['startTime'] = None
        
        self._save_instances()
        self.broadcast_update()
        
        osc_port = self.config.get('osc', {}).get('botPorts', {}).get(bot_id)
        if not osc_port:
             raise ValueError(f"Kein OSC Port für {bot_id} konfiguriert.")
        
        cmd = [launch_path, "-no-ht", "-batchmode", "-nographics", f"--osc={osc_port}:127.0.0.1:{osc_port+1}", f"vrchat://launch?id={final_world_id}"]
        
        try:
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0)
            with self.lock:
                self.instances[bot_id]['status'] = 'waiting_pid'
                self.instances[bot_id]['startTime'] = time.time() * 1000
                self.last_bot_start_time = time.time() * 1000
            self.log_to_discord("Bot Start-Anfrage", f"Starte {self.instances[bot_id]['name']} (World: {final_world_id})", user)
        except Exception as e:
            with self.lock:
                self.instances[bot_id]['status'] = 'error'
            raise e
        
        self._save_instances()
        self.broadcast_update()
        return f"{self.instances[bot_id]['name']} Startbefehl gesendet."

    def stop_vrchat_instance(self, bot_id, user="System"):
        with self.lock:
            instance = self.instances.get(bot_id)
            if not instance:
                raise ValueError(f"Bot ID {bot_id} nicht gefunden.")
            pid = instance.get('pid')
            if not pid:
                if instance['status'] in ['running', 'starting', 'waiting_pid']:
                    instance['status'] = 'stopped'
                    self._save_instances()
                    self.broadcast_update()
                    return "Instanz hatte keine PID, wurde als gestoppt markiert."
                raise ValueError(f"{instance['name']} hat keine laufende Prozess-ID.")
        
        try:
            p = psutil.Process(pid)
            p.kill()
            self.log_to_discord('Bot Gestoppt', f"{instance['name']} (PID: {pid}) wurde beendet.", user)
        except psutil.NoSuchProcess:
            self.log_to_discord('Bot Gestoppt', f"{instance['name']} (PID: {pid}) war nicht mehr vorhanden.", user)
            pass 
            
        with self.lock:
            self.instances[bot_id].update({"pid": None, "startTime": None, "status": "stopped", "ram": "N/A", "cpu": "N/A", "uptime": 0})
        
        self._save_instances()
        self.broadcast_update()
        return f"{instance['name']} erfolgreich beendet."

    def set_instance_world_id(self, bot_id, world_id, user="Dashboard"):
        with self.lock:
            if bot_id not in self.instances:
                raise ValueError(f"Bot ID {bot_id} nicht gefunden.")
            
            final_world_id = self.config.get('worldPresets', {}).get(world_id, world_id)
            if not final_world_id.startswith('wrld_'):
                raise ValueError("Ungültige World ID oder Preset.")
            
            old_world_id = self.instances[bot_id].get('worldId', '(keine)')
            self.instances[bot_id]['worldId'] = final_world_id
            self.log_to_discord('World ID Geändert', f"{self.instances[bot_id]['name']}: {old_world_id} → {final_world_id}", user)

        self._save_instances()
        self.broadcast_update()
        
    def start_all_bots_auto(self, world_preset=None, user='System'):
        with self.lock:
            if self.is_auto_starting:
                raise Exception("Auto-Start läuft bereits")
            
            stopped_bots = [bot_id for bot_id, inst in self.instances.items() if inst['status'] == 'stopped']
            if not stopped_bots:
                raise Exception("Keine gestoppten Bots gefunden")
                
            self.is_auto_starting = True
            self.auto_start_queue = stopped_bots
            self.world_preset_override = world_preset
        
        self.log_to_discord("Auto-Start Gestartet", f"Starte {len(stopped_bots)} Bots automatisch.", user)
        threading.Thread(target=self._process_auto_start_queue, args=(user,)).start()

        return {"total_bots": len(stopped_bots)}
        
    def _process_auto_start_queue(self, user):
        while True:
            with self.lock:
                if not self.is_auto_starting or not self.auto_start_queue:
                    self.is_auto_starting = False
                    self.log_to_discord('Auto-Start Abgeschlossen', 'Alle Bots wurden gestartet.', user)
                    break
                
                delay = self.config.get("startupDelay", 180000)
                if self.last_bot_start_time > 0 and (time.time() * 1000 - self.last_bot_start_time) < delay:
                    time.sleep(1)
                    continue

                bot_id = self.auto_start_queue.pop(0)
                instance = self.instances[bot_id]
            
            world_id = self.world_preset_override if self.world_preset_override else instance.get('worldId') or "Hub"
            try:
                self.start_vrchat_instance(bot_id, world_id, f"{user} (Auto)")
            except Exception as e:
                self.log_to_discord("Auto-Start Fehler", f"Fehler bei {instance['name']}: {e}", user)
    
    def stop_auto_start(self, user='System'):
        with self.lock:
            if not self.is_auto_starting:
                raise Exception("Kein Auto-Start aktiv")
            
            remaining = len(self.auto_start_queue)
            self.auto_start_queue = []
            self.is_auto_starting = False
        
        self.log_to_discord("Auto-Start Gestoppt", f"{remaining} Bots übersprungen.", user)
        return {"stopped_bots": remaining}

    def get_auto_start_status(self):
        with self.lock:
            return {
                "active": self.is_auto_starting,
                "remaining": len(self.auto_start_queue),
                "rateLimit": self.config.get("startupDelay", 180000),
                "lastStartTime": self.last_bot_start_time,
                "timeSinceLastStart": time.time() * 1000 - self.last_bot_start_time if self.last_bot_start_time > 0 else 0
            }
            
    def get_full_system_info(self):
        with self.lock:
            ram = psutil.virtual_memory()
            cpu_usage = psutil.cpu_percent()
            cpu_cores = psutil.cpu_count(logical=True)
            
            system_info = {
                "ram": {"used": f"{(ram.total - ram.available) / (1024**3):.2f}", "total": f"{ram.total / (1024**3):.2f}", "percentage": ram.percent},
                "cpu": {"usage": cpu_usage, "cores": cpu_cores, "loadAvg": f"{psutil.getloadavg()[0]:.2f}" if hasattr(psutil, 'getloadavg') else 'N/A'},
                "uptime": time.time() * 1000 - self.system_start_time
            }
        
            return {"system": system_info, "instances": self.instances, "worldPresets": self.config.get('worldPresets', {})}

    def _update_instances_status(self):
        vrchat_pids = {p.pid for p in psutil.process_iter(['name', 'pid']) if p.info['name'] == 'VRChat.exe'}
        
        with self.lock:
            current_instance_pids = {inst['pid'] for inst in self.instances.values() if inst.get('pid')}
            unassigned_pids = sorted(list(vrchat_pids - current_instance_pids))

            for bot_id, instance in self.instances.items():
                if instance['status'] == 'waiting_pid' and unassigned_pids:
                    pid = unassigned_pids.pop(0)
                    instance['pid'] = pid
                    instance['status'] = 'running'
                    self.log_to_discord('PID Zugewiesen', f"{instance['name']} läuft jetzt mit PID {pid}.")
                
                if instance.get('pid'):
                    if instance['pid'] in vrchat_pids:
                        try:
                            p = psutil.Process(instance['pid'])
                            mem_info = p.memory_info()
                            ram_gb = mem_info.rss / (1024 ** 3)
                            instance['ram'] = f"{ram_gb:.2f} GB" if ram_gb >= 1 else f"{mem_info.rss / (1024 ** 2):.2f} MB"
                            instance['cpu'] = f"{p.cpu_percent() / psutil.cpu_count():.2f}%"
                            instance['status'] = 'running'
                            instance['uptime'] = (time.time() * 1000) - instance['startTime']
                        except psutil.NoSuchProcess:
                            instance.update({"pid": None, "status": "stopped", "ram": "N/A", "cpu": "N/A"})
                    else:
                        instance.update({"pid": None, "status": "stopped", "ram": "N/A", "cpu": "N/A"})
                
                if instance['status'] == 'unknown' and not instance.get('pid'):
                    instance['status'] = 'stopped'
                    
        self._save_instances()

    def _background_update_loop(self):
        while True:
            self._update_instances_status()
            self.broadcast_update()
            time.sleep(5)
            
    def register_ws_client(self, ws):
        self.ws_clients.add(ws)

    def unregister_ws_client(self, ws):
        self.ws_clients.discard(ws)

    def broadcast_update(self):
        full_info = self.get_full_system_info()
        message = json.dumps({'type': 'update', 'data': full_info})
        
        for client in list(self.ws_clients):
            try:
                client.send(message)
            except Exception:
                self.unregister_ws_client(client)