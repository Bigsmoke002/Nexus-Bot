import discord
from discord import app_commands, Interaction, Embed, ButtonStyle, MessageFlags
from discord.ui import Button, View, Select, Modal, TextInput
from typing import Literal, List
import time

# Interne Modulimporte für das VRC-Plugin
from .vrc_manager import VRCManager


# --- HELPER FUNCTIONS (für Embeds) ---

def create_status_embed(instances):
    embed = Embed(
        title="📊 VRChat Bots Status",
        color=0x8A2BE2
    )
    embed.set_timestamp(discord.utils.utcnow())

    if not instances or not any(instances.values()):
        embed.description = "Keine Bot-Instanzen gefunden."
        return embed

    running_count, stopped_count, error_count, total_ram = 0, 0, 0, 0.0
    fields = []
    for bot_id, instance in sorted(instances.items()):
        status = instance.get('status', 'unknown')
        status_map = {
            'running': ('🟢', 'Läuft'), 'starting': ('🟡', 'Startet...'), 
            'waiting_pid': ('🟡', 'Warte auf VRChat.exe...'), 'stopped': ('🔴', 'Gestoppt'),
            'error': ('💥', 'Fehler'), 'unknown': ('❓', 'Unbekannt')
        }
        status_emoji, status_text = status_map.get(status, ('❓', 'Unbekannt'))
        
        if status == 'running': running_count += 1
        elif status == 'stopped': stopped_count += 1
        elif status == 'error': error_count += 1

        field_value = f"{status_emoji} **Status:** {status_text}"
        if instance.get('pid'): field_value += f"\n🆔 **PID:** {instance['pid']}"
        if instance.get('ram') and instance['ram'] != 'N/A':
            field_value += f"\n🧠 **RAM:** {instance['ram']}"
            try:
                ram_val, unit = instance['ram'].split(' ')
                total_ram += float(ram_val) if unit == 'GB' else float(ram_val) / 1024
            except (ValueError, IndexError): pass
        
        if instance.get('uptime', 0) > 0:
            uptime_ms = instance.get('uptime', 0)
            days, rem = divmod(uptime_ms / 1000, 86400)
            hours, rem = divmod(rem, 3600)
            minutes, seconds = divmod(rem, 60)
            if days > 0: uptime_str = f"{int(days)}d {int(hours)}h"
            elif hours > 0: uptime_str = f"{int(hours)}h {int(minutes)}m"
            else: uptime_str = f"{int(minutes)}m"
            field_value += f"\n⏱️ **Uptime:** {uptime_str}"

        if instance.get('worldId'):
            world_id = instance['worldId']
            field_value += f"\n🌍 **World:** `{world_id[:30]}{'...' if len(world_id) > 30 else ''}`"
        
        fields.append({'name': instance.get('name', bot_id), 'value': field_value, 'inline': True})

    overview_value = (f"**Gesamt:** {len(instances)} | 🟢 {running_count} | 🔴 {stopped_count} | 💥 {error_count}\n"
                      f"🧠 **Gesamt RAM:** {total_ram:.2f} GB")
    embed.add_field(name="📈 Übersicht", value=overview_value, inline=False)
    for field in fields:
        embed.add_field(name=field['name'], value=field['value'], inline=field['inline'])
    return embed

def create_osc_status_embed(osc_status):
    is_connected = osc_status.get('connected', False)
    embed = Embed(title="📡 Multi-Bot OSC-System Status", color=0x28A745 if is_connected else 0xDC3545)
    embed.set_timestamp(discord.utils.utcnow())
    if not is_connected:
        embed.description = "❌ OSC-System ist nicht verfügbar oder nicht verbunden"
        return embed

    embed.add_field(name="🔗 Verbindung", value=f"🟢 **Multi-Bot OSC Aktiv**\n📤 Bot-Ports: {len(osc_status.get('botPorts', {}))}", inline=False)
    embed.add_field(name="📋 Warteschlangen", value=f"💬 Chatbox: {osc_status.get('chatboxQueue', 0)} wartend", inline=True)
    embed.add_field(name="⚡ Loops", value=f"🔄 Chat-Loops: {osc_status.get('activeChatLoops', 0)}", inline=True)
    
    if osc_status.get('totalCustomTemplates', 0) > 0:
        embed.add_field(name="📝 Custom Templates", value=f"{osc_status['totalCustomTemplates']} Templates verfügbar", inline=True)
    embed.set_footer(text="💡 Nutze das Web-Dashboard für erweiterte OSC-Kontrolle")
    return embed


# --- VIEWS und MODALS (interaktive Discord-Komponenten) ---

class MultiBotSelectView(View):
    def __init__(self, manager: VRCManager, message_content: str, immediate: bool):
        super().__init__(timeout=300)
        self.manager = manager
        self.message_content = message_content
        self.immediate = immediate
        
        instances = self.manager.get_all_instances_status()
        options = [discord.SelectOption(label=inst['name'], value=bot_id, emoji="🤖")
                   for bot_id, inst in instances.items() if inst.get('status') == 'running']
        
        if not options:
            self.add_item(Select(placeholder="Keine laufenden Bots gefunden", disabled=True))
            return

        select_menu = Select(custom_id="multi_bot_select_action", placeholder="Wähle Bots für die Nachricht...",
                             min_values=1, max_values=len(options), options=options)
        select_menu.callback = self.select_callback
        self.add_item(select_menu)

    async def select_callback(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        bot_ids = interaction.data['values']
        
        if not self.manager.osc_manager:
            await interaction.followup.send("❌ OSC-System ist nicht verfügbar.", ephemeral=True)
            return
            
        results = self.manager.osc_manager.send_multi_bot_chatbox_message(
            bot_ids, self.message_content, self.immediate, notification=False)
        success_count = sum(1 for r in results if r['success'])
        
        embed = Embed(color=0x28A745, title=f"📤 Multi-Chatbox Nachricht gesendet ({success_count}/{len(bot_ids)})")
        embed.add_field(name="Nachricht", value=f"`{self.message_content}`", inline=False)
        embed.add_field(name="An Bots", value=", ".join(bot_ids), inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        for item in self.children: item.disabled = True
        await interaction.edit_original_response(view=self)

class DashboardView(View):
    def __init__(self, manager: VRCManager, timeout=300):
        super().__init__(timeout=timeout)
        self.manager = manager

    @discord.ui.button(label="Neue Login-Daten", style=ButtonStyle.primary, custom_id="vrchat_ctrl_refresh_creds", emoji="🔄")
    async def refresh_creds(self, interaction: Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        try:
            new_creds = self.manager.generate_credentials()
            embed = Embed(color=0x28A745, title="✅ Neue Login-Daten generiert", description="**⚠️ WICHTIG: Passwort wird nur JETZT angezeigt!**")
            embed.add_field(name="Username", value=f"```{new_creds['username']}```", inline=False)
            embed.add_field(name="Password", value=f"```{new_creds['password']}```", inline=False)
            embed.set_footer(text="Diese Daten sind 24 Stunden gültig")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Fehler: {e}", ephemeral=True)

    @discord.ui.button(label="Bot Status", style=ButtonStyle.secondary, custom_id="vrchat_ctrl_show_status", emoji="📊")
    async def show_status(self, interaction: Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        status_embed = create_status_embed(self.manager.get_all_instances_status())
        await interaction.followup.send(embed=status_embed, ephemeral=True)

    @discord.ui.button(label="OSC Status", style=ButtonStyle.secondary, custom_id="vrchat_ctrl_osc_status", emoji="📡")
    async def show_osc_status(self, interaction: Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        if self.manager.osc_manager:
            embed = create_osc_status_embed(self.manager.osc_manager.get_status())
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send("❌ OSC-System nicht verfügbar", ephemeral=True)
            
    @discord.ui.button(label="Multi-Bot Chatbox", style=ButtonStyle.success, custom_id="vrchat_ctrl_multi_chatbox", emoji="📢")
    async def multi_chatbox(self, interaction: Interaction, button: Button):
        class MessageModal(Modal, title="Multi-Bot Chatbox Nachricht"):
            message_input = TextInput(label="Nachricht", placeholder="Deine Nachricht hier...", max_length=144)
            async def on_submit(self, modal_interaction: Interaction):
                view = MultiBotSelectView(outer_self.manager, self.message_input.value, immediate=True)
                await modal_interaction.response.send_message("Wähle die Bots:", view=view, ephemeral=True)
        outer_self = self
        await interaction.response.send_modal(MessageModal())


# --- SLASH COMMAND GROUP (die eigentlichen Discord-Befehle) ---

@app_commands.guild_only()
class VRChatControlCog(app_commands.Group, name="vrchat"):
    """VRChat Control System - Verwaltet bis zu 5 VRChat Bots mit Multi-Bot OSC"""
    
    def __init__(self, bot, manager: VRCManager):
        super().__init__()
        self.bot = bot
        self.manager = manager
        
    @app_commands.command(name="dashboard", description="Zeigt den Link zum Web Dashboard an")
    async def dashboard(self, interaction: Interaction):
        config = self.manager.get_config()
        server_url = f"http://{config.get('host', '127.0.0.1')}:{self.bot.config.get('web_port', 5001)}/vrchat"
        
        embed = Embed(color=0x8A2BE2, title='🎮 VRChat Control Dashboard', description="Erweiterte VRChat Multi-Bot Steuerung.")
        embed.add_field(name="🔗 Dashboard URL", value=f"```\n{server_url}\n```", inline=False)
        
        credentials = self.manager.get_credentials()
        credentials_embed = None
        if credentials and credentials.get('expires_at', 0) > time.time():
            expires_in_hours = int((credentials['expires_at'] - time.time()) / 3600)
            credentials_embed = Embed(color=0x28A745, title="🔐 Aktuelle Login-Daten")
            credentials_embed.add_field(name="Username", value=f"```{credentials['username']}```", inline=True)
            credentials_embed.add_field(name="Gültig noch", value=f"~{expires_in_hours} Stunden", inline=True)
        else:
            credentials_embed = Embed(color=0xDC3545, title="❌ Login abgelaufen", description="`/vrchat reset` für neue.")

        await interaction.response.send_message(embeds=[embed, credentials_embed], view=DashboardView(self.manager), ephemeral=True)

    @app_commands.command(name="reset", description="Generiert neue Login-Daten für das Dashboard")
    async def reset(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        new_creds = self.manager.generate_credentials()
        embed = Embed(color=0x28A745, title="✅ Dashboard Login zurückgesetzt")
        embed.add_field(name="👤 Username", value=f"```{new_creds['username']}```", inline=False)
        embed.add_field(name="🔑 Password", value=f"```{new_creds['password']}```", inline=False)
        embed.set_footer(text="⚠️ Diese Daten sind 24 Stunden gültig. Speichere sie sicher!")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="status", description="Zeigt den aktuellen Status aller Bots an")
    async def status(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        status_embed = create_status_embed(self.manager.get_all_instances_status())
        await interaction.followup.send(embed=status_embed, ephemeral=True)
        
    @app_commands.command(name="osc-status", description="Zeigt den Multi-Bot OSC-System Status an")
    async def osc_status(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.manager.osc_manager:
            embed = create_osc_status_embed(self.manager.osc_manager.get_status())
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send("❌ OSC-System ist nicht initialisiert.", ephemeral=True)

    @app_commands.command(name="chatbox", description="Sende eine OSC Chatbox-Nachricht an einen Bot")
    async def chatbox(self, interaction: Interaction, bot: Literal['bot1', 'bot2', 'bot3', 'bot4', 'bot5'], message: str):
        await interaction.response.defer(ephemeral=True)
        if not self.manager.osc_manager:
            await interaction.followup.send("❌ OSC-System nicht verfügbar.", ephemeral=True)
            return
            
        if self.manager.osc_manager.send_chatbox_message(bot, message[:144]):
            embed = Embed(color=0x28A745, title="📤 OSC Chatbox-Nachricht gesendet")
            embed.add_field(name="Bot", value=bot, inline=True)
            embed.add_field(name="Nachricht", value=f"`{message[:100]}{'...' if len(message) > 100 else ''}`", inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send("❌ Fehler beim Senden der Nachricht.", ephemeral=True)

    @app_commands.command(name="multi-chatbox", description="Sende eine Chatbox-Nachricht an mehrere Bots")
    async def multi_chatbox(self, interaction: Interaction, message: str):
        view = MultiBotSelectView(self.manager, message, immediate=True)
        await interaction.response.send_message("Wähle die Bots aus:", view=view, ephemeral=True)