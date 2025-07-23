import discord
from discord.ext import commands
from discord import app_commands

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        db = self.bot.get_cog("DBHandler")
        channel_id = await db.get_setting(member.guild.id, "welcome_channel")
        message_template = await db.get_setting(member.guild.id, "welcome_message") or "{mention} さん、ようこそ！"

        if channel_id:
            channel = member.guild.get_channel(int(channel_id))
            if channel:
                message = message_template.replace("{mention}", member.mention).replace("{user}", member.name)
                await channel.send(message)

    @app_commands.command(name="welcome_set", description="ウェルカムメッセージとチャンネルを設定します。")
    async def welcome_set(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        db = self.bot.get_cog("DBHandler")
        await db.set_setting(interaction.guild.id, "welcome_channel", str(channel.id))
        await db.set_setting(interaction.guild.id, "welcome_message", message)
        await interaction.response.send_message("✅ ウェルカムメッセージとチャンネルを設定しました。")

async def setup(bot):
    await bot.add_cog(Welcome(bot))
