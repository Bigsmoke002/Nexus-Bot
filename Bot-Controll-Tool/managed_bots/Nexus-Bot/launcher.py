# launcher.py
import subprocess
import time
import sys
from database import log_event, init_db
from config_handler import load_config

def main():
    """Startet und überwacht den Haupt-Bot-Prozess."""
    init_db()
    
    config = load_config()
    crash_config = config.get('crash_handler', {})
    auto_restart = crash_config.get('auto_restart', False)
    max_restarts = crash_config.get('max_restarts', 5)
    delay = crash_config.get('restart_delay_seconds', 10)
    
    restart_count = 0
    
    while True:
        log_event("LAUNCHER", "INFO", "Starte Bot-Prozess...")
        
        process = subprocess.Popen([sys.executable, 'run.py'])
        process.wait()

        if process.returncode != 0:
            log_event("LAUNCHER", "CRITICAL", f"Bot-Prozess ist mit Code {process.returncode} abgestürzt!")
            
            if auto_restart and (restart_count < max_restarts or max_restarts == -1):
                restart_count += 1
                log_event("LAUNCHER", "WARNING", f"Automatischer Neustart wird versucht ({restart_count}/{max_restarts})... Warte {delay} Sekunden.")
                time.sleep(delay)
                continue
            else:
                log_event("LAUNCHER", "ERROR", "Maximale Anzahl an Neustarts erreicht. Bot bleibt aus.")
                break
        else:
            log_event("LAUNCHER", "INFO", "Bot-Prozess wurde sauber beendet. Kein Neustart erforderlich.")
            break

if __name__ == "__main__":
    main()