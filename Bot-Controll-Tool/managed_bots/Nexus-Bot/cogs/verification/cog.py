# cogs/verification/cog.py
import discord
from discord.ext import commands
from discord import app_commands, ButtonStyle, TextStyle, Interaction, ui
import sqlite3
import os
import uuid
import random
import io
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

# --- TRANSLATIONS DICTIONARY ---
translations = {
    'de': {
        'verified_already': "Du bist bereits verifiziert.", 'verify_panel_button': "Verifizierung starten", 'switch_lang_button': "Sprache wechseln",
        'verify_title': "Willkommen! Bitte verifiziere dich", 'verify_desc': "Um vollen Zugriff auf den Server zu erhalten, klicke bitte auf den Button unten.",
        'math_success': "✅ Du wurdest erfolgreich verifiziert!", 'panel_created': "Panel wurde erfolgreich erstellt.", 'unverify_success': "Die Verifizierung von {mention} wurde aufgehoben.",
        'config_level_set': "✅ Verifizierungs-Level auf **Stufe {level}** gesetzt.", 'config_role_set': "✅ Verifizierungs-Rolle auf **{role_name}** gesetzt.",
        'config_joinrole_set': "✅ Join-Rolle auf **{role_name}** gesetzt.", 'config_removerole_set': "✅ Die Rolle **{role_name}** wird nach der Verifizierung entfernt.",
        'config_logchannel_set': "✅ Verifizierungs-Logs werden jetzt in {channel} gesendet.", 'config_age_set': "✅ Mitglieder müssen jetzt mindestens {days} Tage alt sein.",
        'config_join_set': "✅ Mitglieder müssen jetzt mindestens {minutes} Minuten auf dem Server sein.", 'config_ruleschannel_set': "✅ Der Regel-Kanal wurde auf {channel} gesetzt.",
        'config_block_duplicates_set': "✅ Der Schutz vor doppelten Fingerprints wurde **{status}**.",
        'lang_select_title': "Sprachauswahl", 'lang_select_desc': "Bitte wähle deine bevorzugte Sprache aus.", 'lang_switched_msg': "✅ Sprache auf **Deutsch** umgestellt.",
        'web_verify_step1_title': "🌐 Schritt {current}/{total}: Web-Verifizierung", 'web_verify_step1_desc': "Bitte klicke auf den Button, um unsere Webseite zu besuchen. Kehre danach hierher zurück und klicke auf 'Abschließen'.",
        'web_verify_weblink_button': "Webseite besuchen", 'web_verify_complete_button': "Verifizierung abschließen", 'web_verify_not_completed': "❌ Du hast den Prozess auf der Webseite noch nicht abgeschlossen.",
        'verification_success_discord': "🎉 **Verifizierung erfolgreich!**\n\nDu hast nun Zugriff auf alle Kanäle. Willkommen!",
        'math_button_prompt': "Was ist das Ergebnis von **{problem}**?", 'math_modal_prompt': "Bitte löse die folgende Mathe-Aufgabe:",
        'math_modal_title': "Sicherheitsfrage", 'math_error_wrong': "❌ Falsche Antwort. Bitte starte den Prozess erneut.",
        'captcha_prompt': "Bitte gib den Text aus dem Bild in das Feld ein.", 'captcha_modal_title': "CAPTCHA-Verifizierung",
        'account_too_new': "❌ Dein Discord-Account ist zu neu.", 'joined_too_recently': "❌ Du bist erst vor Kurzem dem Server beigetreten.",
        'log_message_title': "✅ Erfolgreiche Verifizierung", 'log_message_user': "Benutzer", 'log_message_details': "Details",
        'log_message_ip': "IP Adresse", 'log_message_ua': "User Agent", 'log_message_fingerprint': "Browser-Fingerprint", 'log_message_cookies': "Cookies aktiviert",
        'rules_step_title': "📜 Schritt 1: Regeln akzeptieren", 'rules_step_desc': "Bitte lies dir zuerst die Regeln im Kanal {channel} durch, bevor du fortfährst.",
        'rules_step_button_go': "Zum Regel-Kanal", 'rules_step_button_accept': "Ich habe die Regeln gelesen und akzeptiere sie",
        'duplicate_fingerprint_blocked': "❌ Diese Verifizierung wurde blockiert, da dein Browser bereits für einen anderen Account verwendet wurde.",
        'not_your_interaction': "Dies ist nicht deine Verifizierungs-Aufgabe."
    },
    'en': {
        'verified_already': "You are already verified.", 'verify_panel_button': "Start Verification", 'switch_lang_button': "Switch Language",
        'verify_title': "Welcome! Please verify yourself", 'verify_desc': "To gain full access to the server, please click the button below.",
        'math_success': "✅ You have been successfully verified!", 'panel_created': "Panel has been successfully created.", 'unverify_success': "Verification of {mention} has been removed.",
        'config_level_set': "✅ Verification level set to **Level {level}**.", 'config_role_set': "✅ Verification role set to **{role_name}**.",
        'config_joinrole_set': "✅ Join role set to **{role_name}**.", 'config_removerole_set': "✅ The role **{role_name}** will be removed after verification.",
        'config_logchannel_set': "✅ Verification logs will now be sent to {channel}.", 'config_age_set': "✅ Members must now be at least {days} days old.",
        'config_join_set': "✅ Members must now be on the server for at least {minutes} minutes.", 'config_ruleschannel_set': "✅ The rules channel has been set to {channel}.",
        'config_block_duplicates_set': "✅ Protection against duplicate fingerprints has been **{status}**.",
        'lang_select_title': "Language Selection", 'lang_select_desc': "Please select your preferred language.", 'lang_switched_msg': "✅ Language switched to **English**.",
        'web_verify_step1_title': "🌐 Step {current}/{total}: Web Verification", 'web_verify_step1_desc': "Please click the button to visit our website. Then return here and click 'Complete'.",
        'web_verify_weblink_button': "Visit Website", 'web_verify_complete_button': "Complete Verification", 'web_verify_not_completed': "❌ You have not completed the process on the website yet.",
        'verification_success_discord': "🎉 **Verification successful!**\n\nYou now have access to all channels. Welcome!",
        'math_button_prompt': "What is the result of **{problem}**?", 'math_modal_prompt': "Please solve the following math problem:",
        'math_modal_title': "Security Question", 'math_error_wrong': "❌ Wrong answer. Please restart the process.",
        'captcha_prompt': "Please enter the text from the image in the field.", 'captcha_modal_title': "CAPTCHA Verification",
        'account_too_new': "❌ Your Discord account is too new.", 'joined_too_recently': "❌ You joined the server too recently.",
        'log_message_title': "✅ Successful Verification", 'log_message_user': "User", 'log_message_details': "Details",
        'log_message_ip': "IP Address", 'log_message_ua': "User Agent", 'log_message_fingerprint': "Browser Fingerprint", 'log_message_cookies': "Cookies Enabled",
        'rules_step_title': "📜 Step 1: Accept Rules", 'rules_step_desc': "Please first read the rules in the channel {channel} before continuing.",
        'rules_step_button_go': "Go to Rules Channel", 'rules_step_button_accept': "I have read and accept the rules",
        'duplicate_fingerprint_blocked': "❌ This verification was blocked because your browser has already been used for another account.",
        'not_your_interaction': "This is not your verification task."
    }
}

# --- HELPER CLASSES FOR UI AND CAPTCHA ---
class LanguageSelectView(ui.View):
    def __init__(self, user_cog_instance):
        super().__init__(timeout=60)
        self.cog = user_cog_instance
    @ui.button(label="Deutsch", style=ButtonStyle.secondary, emoji="🇩🇪")
    async def select_de(self, interaction: Interaction, button: ui.Button):
        self.cog.user_languages[interaction.user.id] = 'de'
        await interaction.response.edit_message(content=translations['de']['lang_switched_msg'], view=None, embed=None)
    @ui.button(label="English", style=ButtonStyle.secondary, emoji="🇺🇸")
    async def select_en(self, interaction: Interaction, button: ui.Button):
        self.cog.user_languages[interaction.user.id] = 'en'
        await interaction.response.edit_message(content=translations['en']['lang_switched_msg'], view=None, embed=None)

class MathAnswerButtons(ui.View):
    def __init__(self, correct_answer: int, cog_instance, interaction_user_id: int):
        super().__init__(timeout=180)
        self.correct_answer = correct_answer
        self.cog = cog_instance
        self.interaction_user_id = interaction_user_id
        
        answers = random.sample([i for i in range(1, 19) if i != correct_answer], 2) + [correct_answer]
        random.shuffle(answers)
        
        for answer in answers:
            button = ui.Button(label=str(answer), style=ButtonStyle.secondary, custom_id=f"math_btn_answer_{answer}")
            button.callback = self.button_callback
            self.add_item(button)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.interaction_user_id:
            lang = self.cog.user_languages.get(interaction.user.id, 'de')
            await interaction.response.send_message(translations[lang]['not_your_interaction'], ephemeral=True)
            return False
        return True

    async def button_callback(self, interaction: Interaction):
        lang = self.cog.user_languages.get(interaction.user.id, 'de')
        answer = int(interaction.data['custom_id'].split('_')[-1])
        
        await interaction.response.defer(ephemeral=True)
        
        if answer == self.correct_answer:
            await self.cog.finalize_verification(interaction, lang)
        else:
            await interaction.followup.send(translations[lang]['math_error_wrong'], ephemeral=True)

        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)
        self.stop()

class MathAnswerModal(ui.Modal):
    def __init__(self, problem_text: str, correct_answer: int, cog_instance, lang: str, next_step_data: dict = None):
        super().__init__(title=translations[lang]['math_modal_title'])
        self.correct_answer = correct_answer
        self.cog = cog_instance
        self.lang = lang
        self.next_step_data = next_step_data
        self.answer_input = ui.TextInput(label=problem_text)
        self.add_item(self.answer_input)
    async def on_submit(self, interaction: Interaction):
        try:
            if int(self.answer_input.value) == self.correct_answer:
                await interaction.response.defer(ephemeral=True)
                if self.next_step_data: 
                    await self.cog.start_web_verification_step(interaction, self.lang, 2, was_deferred=True)
                else: 
                    await self.cog.finalize_verification(interaction, self.lang)
            else: await interaction.response.send_message(translations[self.lang]['math_error_wrong'], ephemeral=True)
        except ValueError: await interaction.response.send_message(translations[self.lang]['math_error_wrong'], ephemeral=True)

class CaptchaModal(ui.Modal):
    def __init__(self, correct_answer: str, cog_instance, lang: str):
        super().__init__(title=translations[lang]['captcha_modal_title'])
        self.correct_answer = correct_answer
        self.cog = cog_instance
        self.lang = lang
        self.answer_input = ui.TextInput(label=translations[lang]['captcha_prompt'])
        self.add_item(self.answer_input)
    async def on_submit(self, interaction: Interaction):
        if self.answer_input.value.lower() == self.correct_answer.lower():
            await self.cog.start_web_verification_step(interaction, self.lang, 2, check_accounts=True, was_deferred=False)
        else:
            await interaction.response.send_message(translations[self.lang]['math_error_wrong'], ephemeral=True)

class VerifyListPaginator(ui.View):
    def __init__(self, cog_instance, guild, entries, per_page=5):
        super().__init__(timeout=180)
        self.cog = cog_instance
        self.guild = guild
        self.entries = entries
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = (len(self.entries) - 1) // self.per_page
    async def get_page_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_entries = self.entries[start:end]
        embed = discord.Embed(title=f"Verifizierte Benutzer (Seite {self.current_page + 1}/{self.total_pages + 1})", color=discord.Color.blue())
        if not page_entries:
            embed.description = "Keine verifizierten Benutzer gefunden."
            return embed
        for entry in page_entries:
            user = self.guild.get_member(entry['user_id'])
            verified_at = discord.utils.format_dt(datetime.fromisoformat(entry['verified_at']), style='R')
            
            # Sichere Behandlung von sqlite3.Row Objekten
            try:
                fingerprint = entry['fingerprint_id'] if entry['fingerprint_id'] else 'N/A'
            except (KeyError, TypeError):
                fingerprint = 'N/A'
            
            try:
                ip_address = entry['ip_address'] if entry['ip_address'] else 'N/A'
            except (KeyError, TypeError):
                ip_address = 'N/A'
                
            field_value = (f"**Verifiziert:** {verified_at}\n**IP:** `{ip_address}`\n**Fingerprint:** `{fingerprint}`")
            embed.add_field(name=f"👤 {user.display_name if user else 'Unbekannter Benutzer'}", value=field_value, inline=False)
        return embed
    @ui.button(label="⬅️", style=ButtonStyle.primary, disabled=True)
    async def previous_page(self, interaction: Interaction, button: ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=await self.get_page_embed(), view=self)
    @ui.button(label="➡️", style=ButtonStyle.primary)
    async def next_page(self, interaction: Interaction, button: ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=await self.get_page_embed(), view=self)
    def update_buttons(self):
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page >= self.total_pages

# --- MAIN COG CLASS ---
class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        plugin_name = self.__class__.__name__
        data_folder = os.path.join('plugin_data', plugin_name)
        self.db_path = os.path.join(data_folder, 'verify.db')
        self.init_database()
        self.user_languages = {}
        self.challenges = {}

    def init_database(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    guild_id INTEGER PRIMARY KEY, role_id INTEGER, join_role_id INTEGER, 
                    remove_role_id INTEGER, level INTEGER DEFAULT 3, log_channel_id INTEGER,
                    min_account_age_days INTEGER DEFAULT 7, min_join_duration_minutes INTEGER DEFAULT 10,
                    rules_channel_id INTEGER, block_duplicate_fingerprints BOOLEAN DEFAULT TRUE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS verifications (
                    user_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, verified_at TEXT NOT NULL, 
                    ip_address TEXT, user_agent TEXT, 
                    fingerprint_id TEXT, cookies_enabled BOOLEAN
                )
            """)
            try:
                cursor.execute("ALTER TABLE verifications ADD COLUMN fingerprint_id TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE verifications ADD COLUMN cookies_enabled BOOLEAN")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    def get_config(self, guild_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM config WHERE guild_id = ?", (guild_id,))
            config = cursor.fetchone()
            if config: return dict(config)
            cursor.execute("INSERT OR IGNORE INTO config (guild_id) VALUES (?)", (guild_id,))
            conn.commit()
            return self.get_config(guild_id)

    def _update_config(self, guild_id, key, value):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE config SET {key} = ? WHERE guild_id = ?", (value, guild_id))
            conn.commit()

    def get_verification_data(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM verifications WHERE user_id = ?", (user_id,))
            return cursor.fetchone()

    def get_all_verifications(self, guild_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM verifications WHERE guild_id = ? ORDER BY verified_at DESC", (guild_id,))
            return cursor.fetchall()

    def is_user_verified_in_db(self, user_id: int, guild_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM verifications WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
            return cursor.fetchone() is not None
            
    def check_fingerprint_duplicate(self, fingerprint_id: str, user_id: int):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM verifications WHERE fingerprint_id = ? AND user_id != ?", (fingerprint_id, user_id))
            return cursor.fetchone() is not None

    def generate_captcha(self):
        text = ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=6))
        try:
            font = ImageFont.truetype("arial.ttf", 30)
        except IOError:
            font = ImageFont.load_default()
        image = Image.new('RGB', (200, 80), color = 'white')
        draw = ImageDraw.Draw(image)
        draw.text((25,20), text, font=font, fill='black')
        for _ in range(30):
            draw.line(((random.randint(0,200), random.randint(0,80)), (random.randint(0,200), random.randint(0,80))), fill='grey', width=2)
        buffer = io.BytesIO()
        image.save(buffer, 'png')
        buffer.seek(0)
        return text, buffer

    # --- COMMANDS ---
    verifypanel_group = app_commands.Group(name="verifypanel", description="Befehle zum Erstellen eines Verifizierungs-Panels")
    verifyconfig_group = app_commands.Group(name="verifyconfig", description="Konfiguration des Verifizierungssystems", default_permissions=discord.Permissions(administrator=True))

    @verifypanel_group.command(name="create", description="Erstellt ein Verifizierungs-Panel.")
    @app_commands.describe(titel="Die Überschrift im Panel.", sprache="Die Standardsprache des Panels.")
    @app_commands.choices(sprache=[app_commands.Choice(name="Deutsch", value="de"), app_commands.Choice(name="English", value="en")])
    async def panel(self, interaction: Interaction, titel: str, sprache: app_commands.Choice[str]):
        lang = sprache.value
        embed = discord.Embed(title=f"✅ {translations[lang]['verify_title']}", description=f"**{titel}**\n\n{translations[lang]['verify_desc']}", color=discord.Color.green())
        embed.set_thumbnail(url="https://img.icons8.com/plasticine/100/000000/verified-account.png")
        embed.set_footer(text=f"{interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        view = ui.View(timeout=None)
        view.add_item(ui.Button(style=ButtonStyle.success, label=translations[lang]['verify_panel_button'], custom_id=f"verify_start_{lang}"))
        view.add_item(ui.Button(style=ButtonStyle.secondary, label=translations[lang]['switch_lang_button'], custom_id="verify_language_switch", emoji="🌐"))
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message(translations[lang]['panel_created'], ephemeral=True)

    @app_commands.command(name="verifylist", description="Listet alle verifizierten Benutzer auf.")
    @app_commands.default_permissions(administrator=True)
    async def verifylist(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        entries = self.get_all_verifications(interaction.guild_id)
        if not entries:
            await interaction.followup.send("Es sind noch keine Benutzer verifiziert.", ephemeral=True)
            return
        paginator = VerifyListPaginator(self, interaction.guild, entries)
        paginator.update_buttons()
        embed = await paginator.get_page_embed()
        await interaction.followup.send(embed=embed, view=paginator, ephemeral=True)

    @verifyconfig_group.command(name="level", description="Setzt das Sicherheitslevel der Verifizierung.")
    @app_commands.choices(level=[
        app_commands.Choice(name="Stufe 1 (Mathe-Buttons)", value=1), app_commands.Choice(name="Stufe 2 (Mathe-Eingabe)", value=2),
        app_commands.Choice(name="Stufe 3 (Webseite)", value=3), app_commands.Choice(name="Stufe 4 (Mathe-Eingabe + Webseite)", value=4),
        app_commands.Choice(name="Stufe 5 (Webseite + Account-Alter)", value=5), app_commands.Choice(name="Stufe 6 (CAPTCHA + Webseite + Alter)", value=6)
    ])
    async def set_level(self, interaction: Interaction, level: app_commands.Choice[int]):
        lang = self.user_languages.get(interaction.user.id, 'de')
        self._update_config(interaction.guild_id, 'level', level.value)
        await interaction.response.send_message(translations[lang]['config_level_set'].format(level=level.value), ephemeral=True)

    @verifyconfig_group.command(name="role", description="Legt die Rolle fest, die Mitglieder nach der Verifizierung erhalten.")
    async def set_role(self, interaction: Interaction, rolle: discord.Role):
        lang = self.user_languages.get(interaction.user.id, 'de')
        self._update_config(interaction.guild_id, 'role_id', rolle.id)
        await interaction.response.send_message(translations[lang]['config_role_set'].format(role_name=rolle.mention), ephemeral=True)
    
    @verifyconfig_group.command(name="logchannel", description="Legt den Kanal für Verifizierungs-Logs fest.")
    async def set_logchannel(self, interaction: Interaction, kanal: discord.TextChannel):
        lang = self.user_languages.get(interaction.user.id, 'de')
        self._update_config(interaction.guild_id, 'log_channel_id', kanal.id)
        await interaction.response.send_message(translations[lang]['config_logchannel_set'].format(channel=kanal.mention), ephemeral=True)

    @verifyconfig_group.command(name="ruleschannel", description="Legt den Kanal fest, in dem die Regeln stehen.")
    async def set_ruleschannel(self, interaction: Interaction, kanal: discord.TextChannel):
        lang = self.user_languages.get(interaction.user.id, 'de')
        self._update_config(interaction.guild_id, 'rules_channel_id', kanal.id)
        await interaction.response.send_message(translations[lang]['config_ruleschannel_set'].format(channel=kanal.mention), ephemeral=True)

    @verifyconfig_group.command(name="block_duplicates", description="Verhindert, dass sich mehrere Accounts mit demselben Browser verifizieren.")
    async def set_block_duplicates(self, interaction: Interaction, aktiv: bool):
        lang = self.user_languages.get(interaction.user.id, 'de')
        self._update_config(interaction.guild_id, 'block_duplicate_fingerprints', aktiv)
        status = "aktiviert" if aktiv else "deaktiviert"
        await interaction.response.send_message(translations[lang]['config_block_duplicates_set'].format(status=status), ephemeral=True)

    @verifyconfig_group.command(name="min_account_age", description="(Stufe 5+) Legt das Mindestalter des Discord-Accounts fest.")
    async def set_min_account_age(self, interaction: Interaction, tage: app_commands.Range[int, 1, 3650]):
        lang = self.user_languages.get(interaction.user.id, 'de')
        self._update_config(interaction.guild_id, 'min_account_age_days', tage)
        await interaction.response.send_message(translations[lang]['config_age_set'].format(days=tage), ephemeral=True)

    @verifyconfig_group.command(name="min_join_duration", description="(Stufe 5+) Legt die Mindest-Serverzugehörigkeit fest.")
    async def set_min_join_duration(self, interaction: Interaction, minuten: app_commands.Range[int, 1, 10080]):
        lang = self.user_languages.get(interaction.user.id, 'de')
        self._update_config(interaction.guild_id, 'min_join_duration_minutes', minuten)
        await interaction.response.send_message(translations[lang]['config_join_set'].format(minutes=minuten), ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: Interaction):
        if interaction.type != discord.InteractionType.component: return
        custom_id = interaction.data.get("custom_id")
        if not custom_id: return
        
        if custom_id.startswith("math_btn_answer_"):
            return

        user_id = interaction.user.id
        
        if custom_id == "verify_language_switch":
            lang = self.user_languages.get(user_id, 'de')
            embed = discord.Embed(title=f"🌐 {translations[lang]['lang_select_title']}", description=translations[lang]['lang_select_desc'], color=0x7289DA)
            await interaction.response.send_message(embed=embed, view=LanguageSelectView(self), ephemeral=True)
            return

        if custom_id.startswith("verify_start_"):
            panel_lang = custom_id.split('_')[-1]
            lang = self.user_languages.get(user_id, panel_lang)
            config = self.get_config(interaction.guild.id)
            if (role_id := config.get('role_id')) and (role := interaction.guild.get_role(role_id)) and role in interaction.user.roles:
                await interaction.response.send_message(translations[lang]['verified_already'], ephemeral=True)
                return
            if (rules_channel_id := config.get('rules_channel_id')) and (rules_channel := interaction.guild.get_channel(rules_channel_id)):
                await interaction.response.defer(ephemeral=True)
                embed = discord.Embed(title=translations[lang]['rules_step_title'], description=translations[lang]['rules_step_desc'].format(channel=rules_channel.mention), color=discord.Color.orange())
                view = ui.View()
                view.add_item(ui.Button(label=translations[lang]['rules_step_button_go'], style=ButtonStyle.link, url=rules_channel.jump_url))
                view.add_item(ui.Button(label=translations[lang]['rules_step_button_accept'], style=ButtonStyle.success, custom_id=f"verify_rules_accepted_{lang}"))
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                await self._initiate_level_based_flow(interaction, lang, config)

        elif custom_id.startswith("verify_rules_accepted_"):
            lang = custom_id.split('_')[-1]
            config = self.get_config(interaction.guild.id)
            await self._initiate_level_based_flow(interaction, lang, config)

        elif custom_id.startswith("verify_complete_"):
            await interaction.response.defer(ephemeral=True)
            parts = custom_id.split('_')
            lang = parts[2]
            check_accounts = parts[3] == 'acc_check'
            if self.is_user_verified_in_db(user_id, interaction.guild.id):
                await self.finalize_verification(interaction, lang, check_accounts)
            else:
                await interaction.followup.send(translations[lang]['web_verify_not_completed'], ephemeral=True)

    async def _initiate_level_based_flow(self, interaction: Interaction, lang: str, config: dict):
        level = config.get('level', 3)
        if interaction.response.is_done():
            await interaction.edit_original_response(content="Bitte warte...", view=None, embed=None)

        if level in [2, 4, 6]:
            if interaction.response.is_done():
                await interaction.followup.send("Interner Fehler. Bitte den Prozess neu starten.", ephemeral=True)
                return

            if level in [2, 4]:
                num1, num2 = random.randint(1, 9), random.randint(1, 9)
                correct = num1 + num2
                problem_text = translations[lang]['math_button_prompt'].format(problem=f"{num1} + {num2}")
                next_step = {'total_steps': 2} if level == 4 else None
                await interaction.response.send_modal(MathAnswerModal(problem_text, correct, self, lang, next_step_data=next_step))
            elif level == 6:
                captcha_text, captcha_image = self.generate_captcha()
                file = discord.File(captcha_image, filename="captcha.png")
                modal = CaptchaModal(captcha_text, self, lang)
                await interaction.response.send_modal(modal)
                await interaction.followup.send(file=file, ephemeral=True)
        else:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
            
            if level == 1:
                num1, num2 = random.randint(1, 9), random.randint(1, 9)
                correct = num1 + num2
                view = MathAnswerButtons(correct, self, interaction.user.id)
                await interaction.followup.send(translations[lang]['math_button_prompt'].format(problem=f"{num1} + {num2}"), view=view, ephemeral=True)
            
            elif level in [3, 5]:
                await self.start_web_verification_step(interaction, lang, 1, check_accounts=(level == 5))

    async def start_web_verification_step(self, interaction: Interaction, lang: str, total_steps: int, check_accounts: bool = False, was_deferred: bool = True):
        base_url = self.bot.config.get("base_url", "http://127.0.0.1:5001")
        verify_url = f"{base_url}/verify?user={interaction.user.id}&lang={lang}"
        embed = discord.Embed(title=translations[lang]['web_verify_step1_title'].format(current=total_steps, total=total_steps), description=translations[lang]['web_verify_step1_desc'], color=0x3498DB)
        view = ui.View()
        view.add_item(ui.Button(label=translations[lang]['web_verify_weblink_button'], style=ButtonStyle.link, url=verify_url, emoji="🔗"))
        view.add_item(ui.Button(label=translations[lang]['web_verify_complete_button'], style=ButtonStyle.success, custom_id=f"verify_complete_{lang}_{'acc_check' if check_accounts else 'no_check'}"))
        
        responder = interaction.followup.send if was_deferred else interaction.response.send_message
        await responder(embed=embed, view=view, ephemeral=True)

    async def finalize_verification(self, interaction: Interaction, lang: str, check_accounts: bool = False):
        async def respond(**kwargs):
            if interaction.response.is_done():
                await interaction.followup.send(**kwargs, ephemeral=True)
            else:
                await interaction.response.send_message(**kwargs, ephemeral=True)
        
        config = self.get_config(interaction.guild.id)
        if not (role_id := config.get('role_id')) or not (role := interaction.guild.get_role(role_id)):
            await respond(content="Fehler: Verifizierungs-Rolle nicht konfiguriert oder gefunden."); return

        bot_member = interaction.guild.get_member(self.bot.user.id)
        
        # Erweiterte Diagnose
        diagnostic_info = f"🔍 **Erweiterte Diagnose:**\n\n"
        
        # Bot-Berechtigungen prüfen
        guild_perms = bot_member.guild_permissions
        diagnostic_info += f"**Bot Guild-Berechtigungen:**\n"
        diagnostic_info += f"• Administrator: {guild_perms.administrator}\n"
        diagnostic_info += f"• Rollen verwalten: {guild_perms.manage_roles}\n"
        diagnostic_info += f"• Server verwalten: {guild_perms.manage_guild}\n\n"
        
        # Channel-spezifische Berechtigungen prüfen
        channel_perms = interaction.channel.permissions_for(bot_member)
        diagnostic_info += f"**Bot Channel-Berechtigungen:**\n"
        diagnostic_info += f"• Nachrichten senden: {channel_perms.send_messages}\n"
        diagnostic_info += f"• Embed Links: {channel_perms.embed_links}\n\n"
        
        # User-Informationen
        diagnostic_info += f"**Ziel-User Informationen:**\n"
        diagnostic_info += f"• Ist Bot: {interaction.user.bot}\n"
        diagnostic_info += f"• Ist Server-Owner: {interaction.user.id == interaction.guild.owner_id}\n"
        diagnostic_info += f"• Höchste Rolle: {interaction.user.top_role.mention} (Position: {interaction.user.top_role.position})\n"
        diagnostic_info += f"• Hat Admin-Rechte: {interaction.user.guild_permissions.administrator}\n\n"
        
        # Rollen-Informationen
        diagnostic_info += f"**Rollen-Details:**\n"
        diagnostic_info += f"• Bot-Rolle: {bot_member.top_role.mention} (Position: {bot_member.top_role.position})\n"
        diagnostic_info += f"• Ziel-Rolle: {role.mention} (Position: {role.position})\n"
        diagnostic_info += f"• Rolle ist managed: {role.managed}\n"
        diagnostic_info += f"• Rolle ist mentionable: {role.mentionable}\n"
        diagnostic_info += f"• User hat Rolle bereits: {role in interaction.user.roles}\n\n"

        # Basis-Checks
        if not guild_perms.manage_roles and not guild_perms.administrator:
            await respond(content=f"{diagnostic_info}❌ **Fehler:** Bot hat keine Rollen-Verwaltungs-Berechtigung!"); return
        
        if role.managed:
            await respond(content=f"{diagnostic_info}❌ **Fehler:** Die Ziel-Rolle ist eine 'managed' Rolle (z.B. Bot-Rolle, Booster-Rolle) und kann nicht manuell vergeben werden!"); return
        
        if role.position >= bot_member.top_role.position:
            await respond(content=f"{diagnostic_info}❌ **Fehler:** Rollen-Hierarchie Problem! Bot-Rolle muss höher sein."); return

        # Spezielle Checks für den User
        if interaction.user.bot:
            await respond(content=f"{diagnostic_info}❌ **Fehler:** Kann keine Rollen an andere Bots vergeben!"); return

        if role in interaction.user.roles:
            await respond(content=f"{diagnostic_info}ℹ️ **Info:** User hat die Rolle bereits!"); return

        verification_data = self.get_verification_data(interaction.user.id)
        if config.get('block_duplicate_fingerprints', True) and verification_data:
            try:
                fingerprint_id = verification_data.get('fingerprint_id') if hasattr(verification_data, 'get') else verification_data['fingerprint_id']
                if fingerprint_id and fingerprint_id != "error" and fingerprint_id != "N/A":
                    if self.check_fingerprint_duplicate(fingerprint_id, interaction.user.id):
                        await respond(content=translations[lang]['duplicate_fingerprint_blocked']); return
            except (KeyError, IndexError, TypeError):
                pass
        
        if check_accounts:
            if datetime.now(datetime.timezone.utc) - interaction.user.created_at < timedelta(days=config['min_account_age_days']):
                await respond(content=translations[lang]['account_too_new']); return
            if datetime.now(datetime.timezone.utc) - interaction.user.joined_at < timedelta(minutes=config['min_join_duration_minutes']):
                await respond(content=translations[lang]['joined_too_recently']); return
        
        try:
            # Versuche die Rolle zu vergeben
            await interaction.user.add_roles(role, reason="Verification completed")
            
            # Remove-Rolle verwalten (falls konfiguriert)
            if (remove_role_id := config.get('remove_role_id')) and (remove_role := interaction.guild.get_role(remove_role_id)):
                if remove_role in interaction.user.roles and remove_role.position < bot_member.top_role.position: 
                    await interaction.user.remove_roles(remove_role, reason="Verification completed - removing unverified role")
            
            # Logging
            if (log_channel_id := config.get('log_channel_id')) and (log_channel := interaction.guild.get_channel(log_channel_id)):
                embed = discord.Embed(title=translations[lang]['log_message_title'], color=discord.Color.green(), timestamp=datetime.now())
                embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
                embed.add_field(name=translations[lang]['log_message_user'], value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
                if verification_data:
                    try:
                        ip_address = verification_data.get('ip_address') if hasattr(verification_data, 'get') else verification_data['ip_address']
                        user_agent = verification_data.get('user_agent') if hasattr(verification_data, 'get') else verification_data['user_agent']
                        fingerprint_id = verification_data.get('fingerprint_id') if hasattr(verification_data, 'get') else verification_data['fingerprint_id']
                        cookies_enabled = verification_data.get('cookies_enabled') if hasattr(verification_data, 'get') else verification_data['cookies_enabled']
                        
                        embed.add_field(name=translations[lang]['log_message_details'], value=f"**{translations[lang]['log_message_ip']}:** `{ip_address or 'N/A'}`\n**{translations[lang]['log_message_ua']}:** `{user_agent or 'N/A'}`", inline=False)
                        embed.add_field(name=translations[lang]['log_message_fingerprint'], value=f"**ID:** `{fingerprint_id or 'N/A'}`\n**{translations[lang]['log_message_cookies']}:** `{cookies_enabled or 'N/A'}`", inline=False)
                    except (KeyError, IndexError, TypeError):
                        embed.add_field(name=translations[lang]['log_message_details'], value="Keine zusätzlichen Daten verfügbar", inline=False)
                embed.set_footer(text=f"Stufe {config.get('level', 3)} Verifizierung")
                try:
                    await log_channel.send(content=interaction.user.mention, embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
                except Exception as log_error:
                    print(f"Log-Fehler: {log_error}")
            
            await interaction.edit_original_response(content=translations[lang]['verification_success_discord'], view=None, embed=None)
            
        except discord.Forbidden as e:
            error_msg = f"{diagnostic_info}"
            error_msg += f"❌ **403 Forbidden Error aufgetreten!**\n\n"
            error_msg += f"**Mögliche Ursachen:**\n"
            error_msg += f"• Integration-Berechtigungen: Bot wurde möglicherweise mit eingeschränkten Berechtigungen eingeladen\n"
            error_msg += f"• Server-Boosts: Manche Server haben spezielle Rollen-Beschränkungen\n"
            error_msg += f"• Discord-Bug: Versuche den Bot zu kicken und erneut einzuladen\n\n"
            error_msg += f"**Lösungsansätze:**\n"
            error_msg += f"1. Bot erneut einladen mit ALLEN Berechtigungen\n"
            error_msg += f"2. Eine neue Test-Rolle erstellen und testen\n"
            error_msg += f"3. Bot-Rolle temporär auf Position 1 (ganz oben) setzen\n\n"
            error_msg += f"**Discord Error:** `{str(e)}`"
            await respond(content=error_msg)
        except discord.HTTPException as e:
            await respond(content=f"{diagnostic_info}❌ **Discord API Fehler:** {str(e)}")
        except Exception as e:
            await respond(content=f"{diagnostic_info}❌ **Unerwarteter Fehler:** {str(e)}")

async def setup(bot):
    await bot.add_cog(Verification(bot))