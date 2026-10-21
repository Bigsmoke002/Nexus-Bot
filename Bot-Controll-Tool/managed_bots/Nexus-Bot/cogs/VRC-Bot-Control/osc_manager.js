import socket
import time
import threading
import json
import os
from collections import deque
from pythonosc.osc_message_builder import OscMessageBuilder
from pythonosc.osc_bundle_builder import IMMEDIATELY

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
            with open(self.custom_templates_path, 'r') as f:
                self.custom_templates = json.load(f)

    def _save_custom_templates(self):
        with open(self.custom_templates_path, 'w') as f:
            json.dump(self.custom_templates, f, indent=4)

    def send_message_to_bot(self, bot_id, address, *args):
        if bot_id not in self.clients:
            return False
        
        builder = OscMessageBuilder(address=address)
        for arg in args:
            builder.add_arg(arg)
        msg = builder.build()
        
        client_info = self.clients[bot_id]
        client_info['socket'].sendto(msg.dgram, (self.host, client_info['port']))
        return True

    def send_chatbox_message(self, bot_id, text, immediate=True, notification=True):
        if bot_id not in self.chatbox_rate_limit:
            return False
        
        message_text = text[:144]
        message = {'address': '/chatbox/input', 'args': [message_text, immediate, notification]}
        with self.lock:
            self.chatbox_rate_limit[bot_id]['queue'].append(message)
        return True
        
    def send_multi_bot_chatbox_message(self, bot_ids, text, immediate=True, notification=True):
        results = []
        for bot_id in bot_ids:
            success = self.send_chatbox_message(bot_id, text, immediate, notification)
            results.append({"botId": bot_id, "success": success})
        return results

    def start_chatbox_loop(self, bot_id, template_name=None, interval_ms=5000, custom_message=None):
        self.stop_chatbox_loop(bot_id)
        
        def loop_func():
            if bot_id not in self.chat_loops or not self.chat_loops[bot_id]['active']:
                return
            
            message = self._render_template(bot_id, template_name, custom_message)
            if message:
                self.send_chatbox_message(bot_id, message, immediate=True, notification=False)
            
            # Reschedule
            if self.chat_loops.get(bot_id, {}).get('active'):
                self.chat_loops[bot_id]['timer'] = threading.Timer(interval_ms / 1000.0, loop_func)
                self.chat_loops[bot_id]['timer'].start()
        
        with self.lock:
            self.chat_loops[bot_id] = {'active': True, 'type': 'single'}
            timer = threading.Timer(interval_ms / 1000.0, loop_func)
            timer.start()
            self.chat_loops[bot_id]['timer'] = timer
        return True
        
    def start_multi_bot_chatbox_loop(self, bot_ids, template_name, interval_ms, custom_message, live_instances):
        loop_id = f"multi_{uuid.uuid4().hex[:8]}"
        
        def loop_func():
            if loop_id not in self.chat_loops or not self.chat_loops[loop_id]['active']:
                return

            for bot_id in bot_ids:
                message = self._render_template(bot_id, template_name, custom_message, live_instances)
                if message:
                    self.send_chatbox_message(bot_id, message, immediate=True, notification=False)

            if self.chat_loops.get(loop_id, {}).get('active'):
                self.chat_loops[loop_id]['timer'] = threading.Timer(interval_ms / 1000.0, loop_func)
                self.chat_loops[loop_id]['timer'].start()

        with self.lock:
            self.chat_loops[loop_id] = {'active': True, 'type': 'multi', 'bot_ids': bot_ids}
            timer = threading.Timer(interval_ms / 1000.0, loop_func)
            timer.start()
            self.chat_loops[loop_id]['timer'] = timer
        return loop_id

    def stop_chatbox_loop(self, bot_id):
        with self.lock:
            if bot_id in self.chat_loops and self.chat_loops[bot_id]['type'] == 'single':
                self.chat_loops[bot_id]['active'] = False
                if 'timer' in self.chat_loops[bot_id]:
                    self.chat_loops[bot_id]['timer'].cancel()
                del self.chat_loops[bot_id]
                return True
        return False
        
    def stop_multi_bot_chatbox_loop(self, loop_id):
        with self.lock:
            if loop_id in self.chat_loops and self.chat_loops[loop_id]['type'] == 'multi':
                self.chat_loops[loop_id]['active'] = False
                if 'timer' in self.chat_loops[loop_id]:
                    self.chat_loops[loop_id]['timer'].cancel()
                del self.chat_loops[loop_id]
                return True
        return False
        
    def _render_template(self, bot_id, template_name=None, custom_message=None, live_instances=None):
        if custom_message:
            return custom_message
        
        if not template_name:
            return None
        
        if template_name in self.custom_templates:
            content = self.custom_templates[template_name].get('content', '')
            # Replace placeholders
            content = content.replace('{time}', time.strftime('%H:%M:%S'))
            content = content.replace('{date}', time.strftime('%d.%m.%Y'))
            content = content.replace('{datetime}', time.strftime('%d.%m.%Y %H:%M:%S'))
            content = content.replace('{bot}', bot_id)
            if live_instances and bot_id in live_instances:
                uptime_ms = live_instances[bot_id].get('uptime', 0)
                hours = int(uptime_ms / 3600000)
                minutes = int((uptime_ms % 3600000) / 60000)
                content = content.replace('{uptime}', f'{hours}h {minutes}m')
            return content
            
        # Built-in templates
        if template_name == 'time':
            return time.strftime('%H:%M:%S')
        if template_name == 'date':
            return time.strftime('%d.%m.%Y')
        if template_name == 'datetime':
            return time.strftime('%d.%m.%Y %H:%M:%S')
        return f"Unknown template: {template_name}"

    def get_all_templates(self):
        builtin = ['time', 'date', 'datetime']
        custom = [{'name': name, **data} for name, data in self.custom_templates.items()]
        return {"builtin": builtin, "custom": custom}

    def save_custom_template(self, name, content, description=''):
        with self.lock:
            self.custom_templates[name] = {'content': content, 'description': description, 'created': time.time()}
            self._save_custom_templates()

    def delete_custom_template(self, name):
        with self.lock:
            if name in self.custom_templates:
                del self.custom_templates[name]
                self._save_custom_templates()
                return True
        return False

    def get_status(self):
        with self.lock:
            total_queue = sum(len(q['queue']) for q in self.chatbox_rate_limit.values())
            return {
                "connected": True,
                "config": {"host": self.host},
                "botPorts": self.bot_ports_config,
                "chatboxQueue": total_queue,
                "activeChatLoops": len(self.chat_loops),
                "chatLoops": list(self.chat_loops.keys()),
                "totalCustomTemplates": len(self.custom_templates),
            }

    def _process_rate_limits(self):
        while True:
            with self.lock:
                for bot_id, limit in self.chatbox_rate_limit.items():
                    if limit['queue']:
                        now = time.time()
                        if now - limit['last_sent'] >= limit['min_interval']:
                            message = limit['queue'].popleft()
                            self.send_message_to_bot(bot_id, message['address'], *message['args'])
                            limit['last_sent'] = now
            time.sleep(0.1)