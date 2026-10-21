import socket
import time
import threading
import json
import os
import uuid
from collections import deque
from pythonosc.osc_message_builder import OscMessageBuilder

class OSCManager:
    def __init__(self, bot_ports_config, data_path):
        self.clients = {}
        self.bot_ports_config = bot_ports_config
        self.host = '127.0.0.1'
        self.chatbox_rate_limit = {}
        self.chat_loops = {}
        self.custom_templates_path = os.path.join(data_path, 'custom_templates.json')
        self.custom_templates = {}
        self.lock = threading.Lock()
        self._load_custom_templates()
        self._initialize_clients()
        self.rate_limit_thread = threading.Thread(target=self._process_rate_limits, daemon=True)
        self.rate_limit_thread.start()

    def _initialize_clients(self):
        for bot_id, port in self.bot_ports_config.items():
            self.clients[bot_id] = {'socket': socket.socket(socket.AF_INET, socket.SOCK_DGRAM), 'port': port}
            self.chatbox_rate_limit[bot_id] = {'last_sent': 0, 'min_interval': 1.5, 'queue': deque()}

    def _load_custom_templates(self):
        if os.path.exists(self.custom_templates_path):
            with open(self.custom_templates_path, 'r', encoding='utf-8') as f: self.custom_templates = json.load(f)

    def _save_custom_templates(self):
        with open(self.custom_templates_path, 'w', encoding='utf-8') as f: json.dump(self.custom_templates, f, indent=4)

    def send_message_to_bot(self, bot_id, address, *args):
        if bot_id not in self.clients: return False
        builder = OscMessageBuilder(address=address)
        for arg in args: builder.add_arg(arg)
        self.clients[bot_id]['socket'].sendto(builder.build().dgram, (self.host, self.clients[bot_id]['port']))
        return True

    def send_chatbox_message(self, bot_id, text, immediate=True, notification=True):
        if bot_id not in self.chatbox_rate_limit: return False
        message = {'address': '/chatbox/input', 'args': [text[:144], immediate, notification]}
        with self.lock: self.chatbox_rate_limit[bot_id]['queue'].append(message)
        return True
        
    def send_multi_bot_chatbox_message(self, bot_ids, text, immediate=True, notification=True):
        return [{"botId": bot_id, "success": self.send_chatbox_message(bot_id, text, immediate, notification)} for bot_id in bot_ids]
    
    def get_all_templates(self):
        return {"builtin": ['time', 'date', 'datetime'], "custom": [{'name': name, **data} for name, data in self.custom_templates.items()]}
    
    def get_status(self):
        with self.lock:
            return {
                "connected": True, "config": {"host": self.host}, "botPorts": self.bot_ports_config,
                "chatboxQueue": sum(len(q['queue']) for q in self.chatbox_rate_limit.values()),
                "activeChatLoops": len(self.chat_loops), "chatLoops": list(self.chat_loops.keys()),
                "totalCustomTemplates": len(self.custom_templates),
            }

    def _process_rate_limits(self):
        while True:
            with self.lock:
                for bot_id, limit in self.chatbox_rate_limit.items():
                    if limit['queue'] and time.time() - limit['last_sent'] >= limit['min_interval']:
                        message = limit['queue'].popleft()
                        self.send_message_to_bot(bot_id, message['address'], *message['args'])
                        limit['last_sent'] = time.time()
            time.sleep(0.1)

# Leere setup-Funktion, um Ladefehler zu verhindern
async def setup(bot):
    pass