# app/process_manager.py
import subprocess
import threading
import sys
import os
from . import socketio

class ProcessManager:
    def __init__(self):
        self.processes = {} # {bot_id: {process: Popen, thread: Thread, status: str, logs: list}}

    def _stream_output(self, bot_id, stream):
        """Liest den Output eines Prozesses und sendet ihn via SocketIO."""
        for line in iter(stream.readline, ''):
            decoded_line = line.strip()
            print(f"[Bot {bot_id}]: {decoded_line}") # Log im Controller
            if len(self.processes[bot_id]['logs']) > 100:
                self.processes[bot_id]['logs'].pop(0) # Logs auf 100 Zeilen begrenzen
            self.processes[bot_id]['logs'].append(decoded_line)
            # Sende die neue Log-Zeile an das Frontend
            socketio.emit('new_log', {'bot_id': bot_id, 'data': decoded_line})
        stream.close()

    def start_bot(self, bot):
        if bot.id in self.processes and self.processes[bot.id]['process'].poll() is None:
            return # Bot läuft bereits

        bot_path = os.path.abspath(bot.path)
        launcher_path = os.path.join(bot_path, 'launcher.py')

        if not os.path.exists(launcher_path):
            print(f"FEHLER: launcher.py nicht in {bot_path} gefunden!")
            socketio.emit('status_update', {'bot_id': bot.id, 'status': 'error'})
            return

        # Starte den launcher.py im richtigen Verzeichnis
        process = subprocess.Popen(
            [sys.executable, launcher_path],
            cwd=bot_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1
        )
        
        self.processes[bot.id] = {
            'process': process,
            'thread': None,
            'status': 'running',
            'logs': []
        }
        
        # Starte einen Thread, um den Output des Bots zu lesen
        thread = threading.Thread(target=self._stream_output, args=(bot.id, process.stdout))
        thread.daemon = True
        thread.start()
        self.processes[bot.id]['thread'] = thread
        
        socketio.emit('status_update', {'bot_id': bot.id, 'status': 'running'})
        print(f"Bot {bot.name} (ID: {bot.id}) gestartet mit PID {process.pid}.")

    def stop_bot(self, bot_id):
        if bot_id in self.processes:
            process_info = self.processes[bot_id]
            if process_info['process'].poll() is None: # Prüfen ob der Prozess noch läuft
                process_info['process'].terminate() # Sanft beenden
                try:
                    process_info['process'].wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process_info['process'].kill() # Hart beenden, wenn sanft nicht klappt
                
                print(f"Bot (ID: {bot_id}) gestoppt.")

            del self.processes[bot_id]
            socketio.emit('status_update', {'bot_id': bot_id, 'status': 'stopped'})

    def get_status(self, bot_id):
        if bot_id not in self.processes:
            return 'stopped'
        
        process = self.processes[bot_id]['process']
        if process.poll() is None:
            return 'running'
        else:
            # Der Prozess ist beendet, prüfe den Exit-Code
            if process.returncode == 0:
                 return 'stopped'
            else:
                 return 'crashed'
    
    def get_logs(self, bot_id):
        return self.processes.get(bot_id, {}).get('logs', [])

# Erstelle eine globale Instanz des Managers
process_manager = ProcessManager()