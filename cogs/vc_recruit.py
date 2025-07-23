import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite

DB_PATH = "./orbis.db"

class VCRecruit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_guild_setting(self, guild_id: int, key: str):
        cog = self.bot.get_cog("DBHandler")
        if cog:
            return await cog.get_setting(guild_id, key)
        return None
    
    async def set_guild_setting(self, guild_id: int, key: str, value: str):
        cog = self.bot.get_cog("DBHandler")
        if cog:
            await cog.set_setting(guild_id, key, value)

    @app_commands.command(name="vc_recruit_setrole", description="VC募集用のロールを設定します。")
    @app_commands.describe(role="募集用ロール")
    async def vc_recruit_setrole(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("🚫 権限がありません。", ephemeral=True)
            return
        await self.set_guild_setting(interaction.guild.id, "vc_recruit_role_id", str(role.id))
        await interaction.response.send_message(f"✅ 募集用ロールを `{role.name}` に設定しました。", ephemeral=True)

    @app_commands.command(name="vc_recruit_setchannel", description="募集告知用チャンネルを設定します。")
    @app_commands.describe(channel="募集告知用テキストチャンネル")
    async def vc_recruit_setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("🚫 権限がありません。", ephemeral=True)
            return
        await self.set_guild_setting(interaction.guild.id, "vc_recruit_channel_id", str(channel.id))
        await interaction.response.send_message(f"✅ 募集告知チャンネルを `{channel.name}` に設定しました。", ephemeral=True)

    @app_commands.command(name="vc_recruit", description="VC募集を告知します。")
    @app_commands.describe(message="募集メッセージ")
    async def vc_recruit(self, interaction: discord.Interaction, message: str):
        role_id = await self.get_guild_setting(interaction.guild.id, "vc_recruit_role_id")
        channel_id = await self.get_guild_setting(interaction.guild.id, "vc_recruit_channel_id")
        if not role_id or not channel_id:
            await interaction.response.send_message("⚠️ 募集用ロールまたは告知用チャンネルが設定されていません。", ephemeral=True)
            return
        role = interaction.guild.get_role(int(role_id))
        channel = interaction.guild.get_channel(int(channel_id))
        if not role or not channel:
            await interaction.response.send_message("⚠️ 設定されたロールまたはチャンネルが見つかりません。", ephemeral=True)
            return
        embed = discord.Embed(title="🎤 VC募集", description=message, color=discord.Color.green())
        embed.set_footer(text=f"募集者: {interaction.user.display_name}")
        await channel.send(content=role.mention, embed=embed)
        await interaction.response.send_message("✅ 募集を告知しました。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(VCRecruit(bot))
