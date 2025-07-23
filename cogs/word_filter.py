import discord
from discord.ext import commands
from discord import app_commands
import re

class WordFilter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        db = self.bot.get_cog("DBHandler")
        ngwords = await db.get_ngwords(message.guild.id, message.channel.id)

        for word in ngwords:
            if re.search(re.escape(word), message.content, re.IGNORECASE):
                await message.delete()
                timeout_seconds = int(await db.get_setting(message.guild.id, "ngword_timeout") or 600)
                try:
                    await message.author.timeout(discord.utils.utcnow() + discord.timedelta(seconds=timeout_seconds),
                                                 reason=f"NGワード検出（'{word}'）")
                    await message.channel.send(
                        f"🚫 {message.author.mention} がNGワードによりタイムアウトされました（{timeout_seconds // 60}分）",
                        delete_after=10
                    )
                except Exception:
                    pass
                break

    @app_commands.command(name="ngword_add", description="NGワードを追加します。")
    async def ngword_add(self, interaction: discord.Interaction, word: str, channel: discord.TextChannel = None):
        db = self.bot.get_cog("DBHandler")
        await db.add_ngword(interaction.guild.id, word, channel.id if channel else None)
        await interaction.response.send_message(f"✅ NGワード `{word}` を追加しました。")

    @app_commands.command(name="ngword_remove", description="NGワードを削除します。")
    async def ngword_remove(self, interaction: discord.Interaction, word: str):
        db = self.bot.get_cog("DBHandler")
        await db.remove_ngword(interaction.guild.id, word)
        await interaction.response.send_message(f"🗑️ NGワード `{word}` を削除しました。")

    @app_commands.command(name="ngword_set_timeout", description="NGワード検出時のタイムアウト秒数を設定します。")
    async def ngword_set_timeout(self, interaction: discord.Interaction, seconds: int):
        db = self.bot.get_cog("DBHandler")
        await db.set_setting(interaction.guild.id, "ngword_timeout", str(seconds))
        await interaction.response.send_message(f"✅ タイムアウト時間を {seconds}秒 に設定しました。")

async def setup(bot):
    await bot.add_cog(WordFilter(bot))
