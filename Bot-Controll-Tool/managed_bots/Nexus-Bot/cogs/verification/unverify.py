# cogs/verification/unverify.py
import discord
from discord.ext import commands
from discord import app_commands, Interaction
import sqlite3
import os
from datetime import datetime

class UnverifySystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        plugin_name = "Verification"
        data_folder = os.path.join('plugin_data', plugin_name)
        self.db_path = os.path.join(data_folder, 'verify.db')

    def get_config(self, guild_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM config WHERE guild_id = ?", (guild_id,))
            config = cursor.fetchone()
            if config: 
                return dict(config)
            return {}

    def get_verification_data(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM verifications WHERE user_id = ?", (user_id,))
            return cursor.fetchone()

    @app_commands.command(name="unverify", description="Entfernt die Verifizierung eines Users und löscht alle Daten aus der Datenbank.")
    @app_commands.describe(user="Der User, dessen Verifizierung entfernt werden soll.")
    @app_commands.default_permissions(administrator=True)
    async def unverify(self, interaction: Interaction, user: discord.Member):
        config = self.get_config(interaction.guild.id)
        
        # Prüfe ob User verifiziert ist
        verification_data = self.get_verification_data(user.id)
        if not verification_data:
            await interaction.response.send_message(
                f"❌ **User nicht verifiziert**\n\n{user.mention} ist nicht in der Verifizierungs-Datenbank.", 
                ephemeral=True
            )
            return
        
        try:
            # Verifizierungs-Rolle entfernen (falls konfiguriert)
            if (role_id := config.get('role_id')) and (role := interaction.guild.get_role(role_id)):
                if role in user.roles:
                    await user.remove_roles(role, reason=f"Unverify by {interaction.user}")
            
            # "Unverified" Rolle wieder hinzufügen (falls konfiguriert) 
            if (remove_role_id := config.get('remove_role_id')) and (remove_role := interaction.guild.get_role(remove_role_id)):
                if remove_role not in user.roles:
                    await user.add_roles(remove_role, reason=f"Unverify - restore unverified role by {interaction.user}")
            
            # Komplett aus Datenbank löschen
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM verifications WHERE user_id = ?", (user.id,))
                deleted_rows = cursor.rowcount
                conn.commit()
            
            # Log-Nachricht senden
            if (log_channel_id := config.get('log_channel_id')) and (log_channel := interaction.guild.get_channel(log_channel_id)):
                embed = discord.Embed(
                    title="🔄 Verifizierung entfernt", 
                    color=discord.Color.orange(), 
                    timestamp=datetime.now()
                )
                embed.set_author(name=str(user), icon_url=user.display_avatar.url)
                embed.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=False)
                embed.add_field(name="Entfernt von", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
                
                # Zeige entfernte Daten an
                if verification_data:
                    try:
                        ip_address = verification_data['ip_address'] if verification_data['ip_address'] else 'N/A'
                        fingerprint = verification_data['fingerprint_id'] if verification_data['fingerprint_id'] else 'N/A'
                        embed.add_field(
                            name="Gelöschte Daten", 
                            value=f"**IP:** `{ip_address}`\n**Fingerprint:** `{fingerprint}`", 
                            inline=False
                        )
                    except (KeyError, TypeError):
                        pass
                
                embed.set_footer(text="Unverify-Aktion - Alle Daten gelöscht")
                await log_channel.send(embed=embed)
            
            # Erfolgsmeldung
            success_msg = f"✅ **Unverify erfolgreich**\n\n{user.mention} wurde **komplett entverifiziert**:\n\n"
            success_msg += f"🗑️ **Gelöschte Datensätze:** {deleted_rows}\n"
            success_msg += f"❌ **Verifizierungs-Rolle entfernt**\n"
            success_msg += f"➕ **Unverified-Rolle hinzugefügt**\n"
            success_msg += f"🔄 **Kann sich komplett neu verifizieren**\n\n"
            success_msg += f"*Alle Datenbank-Einträge (IP, Fingerprint, etc.) wurden gelöscht.*"
            
            await interaction.response.send_message(success_msg, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ **Berechtigungsfehler**\n\nKeine Berechtigung um Rollen von {user.mention} zu verwalten.\n\nPrüfe die Bot-Rollen-Hierarchie!", 
                ephemeral=True
            )
        except sqlite3.Error as e:
            await interaction.response.send_message(
                f"❌ **Datenbank-Fehler**\n\nFehler beim Löschen aus der Datenbank: {str(e)}", 
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ **Unerwarteter Fehler**\n\nFehler beim Entfernen der Verifizierung: {str(e)}", 
                ephemeral=True
            )

    @app_commands.command(name="unverify_bulk", description="Entfernt die Verifizierung mehrerer User auf einmal.")
    @app_commands.describe(users="Mehrere User getrennt durch Leerzeichen (z.B. @user1 @user2 @user3)")
    @app_commands.default_permissions(administrator=True)
    async def unverify_bulk(self, interaction: Interaction, users: str):
        await interaction.response.defer(ephemeral=True)
        
        # Parse user mentions
        user_ids = []
        for word in users.split():
            if word.startswith('<@') and word.endswith('>'):
                try:
                    user_id = int(word.replace('<@', '').replace('!', '').replace('>', ''))
                    user_ids.append(user_id)
                except ValueError:
                    continue
        
        if not user_ids:
            await interaction.followup.send("❌ Keine gültigen User-Mentions gefunden.", ephemeral=True)
            return
        
        config = self.get_config(interaction.guild.id)
        processed = 0
        errors = []
        
        for user_id in user_ids:
            try:
                user = interaction.guild.get_member(user_id)
                if not user:
                    errors.append(f"User ID {user_id} nicht gefunden")
                    continue
                
                verification_data = self.get_verification_data(user_id)
                if not verification_data:
                    errors.append(f"{user.display_name} war nicht verifiziert")
                    continue
                
                # Rollen verwalten
                if (role_id := config.get('role_id')) and (role := interaction.guild.get_role(role_id)):
                    if role in user.roles:
                        await user.remove_roles(role, reason=f"Bulk unverify by {interaction.user}")
                
                if (remove_role_id := config.get('remove_role_id')) and (remove_role := interaction.guild.get_role(remove_role_id)):
                    if remove_role not in user.roles:
                        await user.add_roles(remove_role, reason=f"Bulk unverify by {interaction.user}")
                
                # Aus Datenbank löschen
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM verifications WHERE user_id = ?", (user_id,))
                    conn.commit()
                
                processed += 1
                
            except Exception as e:
                errors.append(f"{user.display_name if 'user' in locals() else user_id}: {str(e)}")
        
        # Ergebnis anzeigen
        result_msg = f"✅ **Bulk Unverify abgeschlossen**\n\n"
        result_msg += f"🔄 **Erfolgreich verarbeitet:** {processed} User\n"
        if errors:
            result_msg += f"❌ **Fehler:** {len(errors)}\n\n**Fehler-Details:**\n"
            for error in errors[:5]:  # Zeige max 5 Fehler
                result_msg += f"• {error}\n"
            if len(errors) > 5:
                result_msg += f"• ... und {len(errors) - 5} weitere"
        
        await interaction.followup.send(result_msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(UnverifySystem(bot))