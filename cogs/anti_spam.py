import discord
from discord.ext import commands, tasks
from discord import app_commands
from collections import defaultdict
import asyncio

class AntiSpam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.msg_cache = defaultdict(list)
        self.cleanup_task.start()

    @tasks.loop(seconds=1)
    async def cleanup_task(self):
        for user_id in list(self.msg_cache.keys()):
            self.msg_cache[user_id] = [ts for ts in self.msg_cache[user_id] if ts > discord.utils.utcnow().timestamp() - 1]
            if not self.msg_cache[user_id]:
                del self.msg_cache[user_id]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        now = discord.utils.utcnow().timestamp()
        self.msg_cache[message.author.id].append(now)

        max_count = int(await self.bot.get_cog("DBHandler").get_setting(message.guild.id, "spam_limit") or 5)
        timeout_duration = int(await self.bot.get_cog("DBHandler").get_setting(message.guild.id, "spam_timeout") or 3600)

        if len(self.msg_cache[message.author.id]) >= max_count:
            try:
                await message.author.timeout(discord.utils.utcnow() + discord.timedelta(seconds=timeout_duration),
                                             reason="スパム検知")
                await message.channel.send(f"🚨 {message.author.mention} がスパム検知により {timeout_duration // 60}分 タイムアウトされました。", delete_after=10)
            except Exception:
                pass
            self.msg_cache[message.author.id].clear()

    @app_commands.command(name="spam_set_limit", description="スパム検知の投稿上限を設定します（秒間）")
    async def spam_set_limit(self, interaction: discord.Interaction, count: int):
        await self.bot.get_cog("DBHandler").set_setting(interaction.guild.id, "spam_limit", str(count))
        await interaction.response.send_message(f"✅ 秒間メッセージ上限を `{count}` に設定しました。")

    @app_commands.command(name="spam_set_timeout", description="スパム検知時のタイムアウト秒数を設定します")
    async def spam_set_timeout(self, interaction: discord.Interaction, seconds: int):
        await self.bot.get_cog("DBHandler").set_setting(interaction.guild.id, "spam_timeout", str(seconds))
        await interaction.response.send_message(f"✅ スパムタイムアウト時間を `{seconds}` 秒に設定しました。")

async def setup(bot):
    await bot.add_cog(AntiSpam(bot))
