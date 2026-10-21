# cogs/access_panel/cog.py
import discord
from discord.ext import commands
from discord import app_commands, ui, ButtonStyle, Interaction
import secrets
import glob
from database import create_auth_token, check_user_permission_for_plugin

def get_web_plugins():
    web_files = glob.glob('cogs/**/*_web.py', recursive=True)
    plugins = []
    for file in web_files:
        module_name = file.replace('\\', '.').replace('/', '.').replace('.py', '')
        try:
            module = __import__(module_name, fromlist=['blueprint'])
            if hasattr(module, 'blueprint'):
                plugins.append({
                    'name': module.blueprint.name,
                    'display_name': getattr(module.blueprint, 'display_name', module.blueprint.name.replace("_web", "").replace("verify", "Verification").capitalize()),
                    'is_public': getattr(module.blueprint, 'is_public', False)
                })
        except Exception:
            pass
    return plugins

class AccessPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(self.AccessPanelView())

    class AccessPanelView(ui.View):
        def __init__(self):
            super().__init__(timeout=None)
            plugins = get_web_plugins()
            for plugin in plugins:
                # Öffentliche Plugins bekommen einen direkten Link
                if plugin['is_public']:
                    # Die Basis-URL wird hier hartcodiert, da die View keine Bot-Config kennt.
                    # Für eine dynamische Lösung müsste die URL in der DB stehen.
                    base_url = "http://127.0.0.1:5001" 
                    self.add_item(ui.Button(label=f"Öffne {plugin['display_name']}", style=ButtonStyle.link, url=f"{base_url}/{plugin['name'].replace('_web','')}"))
                else: # Private Plugins bekommen den sicheren Auth-Button
                    self.add_item(ui.Button(label=f"Zugriff auf {plugin['display_name']}", style=ButtonStyle.secondary, custom_id=f"access_plugin_{plugin['name']}"))

        @ui.button(label="Platzhalter", style=ButtonStyle.primary, custom_id="access_plugin_placeholder", row=4)
        async def handle_plugin_access(self, interaction: Interaction, button: ui.Button):
            plugin_name = button.custom_id.split('_')[-1]
            
            has_permission = check_user_permission_for_plugin(interaction.user, plugin_name)

            if not has_permission:
                await interaction.response.send_message("❌ Du hast keine Berechtigung für dieses Tool.", ephemeral=True)
                return

            token = secrets.token_urlsafe(32)
            create_auth_token(token, interaction.user.id, interaction.guild_id)
            
            base_url = interaction.client.config.get("base_url", "http://127.0.0.1:5001")
            auth_link = f"{base_url}/auth/login?token={token}&target={plugin_name}"

            embed = discord.Embed(
                title="✅ Sicherer Zugriffs-Link generiert",
                description=f"Dein persönlicher Einmal-Link für **{plugin_name.replace('_web','').capitalize()}** ist bereit.\n\n"
                            f"**[Klicke hier, um das Tool zu öffnen]({auth_link})**\n\n"
                            f"⚠️ Dieser Link ist nur für dich und nur **60 Sekunden** gültig.",
                color=discord.Color.green())
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="accesspanel", description="Erstellt das Zugriffs-Panel für Web-Plugins.")
    @app_commands.default_permissions(administrator=True)
    async def access_panel(self, interaction: Interaction):
        embed = discord.Embed(
            title="🌐 Web-Tool Zugriff",
            description="Klicke auf einen Button, um ein Web-Tool zu öffnen oder einen sicheren Zugriffs-Link anzufordern.",
            color=discord.Color.blurple())
        await interaction.channel.send(embed=embed, view=self.AccessPanelView())
        await interaction.response.send_message("Access-Panel wurde erstellt.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AccessPanel(bot))