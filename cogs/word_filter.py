import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import re

DB_PATH = "./orbis.db"

class WordFilter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ngword_cache = {}

    async def get_ngwords(self, guild_id: int, channel_id: int | None = None):
        async with aiosqlite.connect(DB_PATH) as db:
            query = "SELECT word FROM ngwords WHERE guild_id = ? AND (channel_id IS NULL OR channel_id = ?)"
            async with db.execute(query, (guild_id, channel_id)) as cursor:
                return [row[0] for row in await cursor.fetchall()]

    async def ensure_tables(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ngwords (
                    guild_id INTEGER,
                    channel_id INTEGER,
                    word TEXT
                )
            """)
            await db.commit()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        await self.ensure_tables()
        ngwords = await self.get_ngwords(message.guild.id, message.channel.id)

        for word in ngwords:
            if re.search(re.escape(word), message.content, re.IGNORECASE):
                await message.delete()
                timeout_seconds = int(await self.bot.get_cog("DBHandler").get_setting(message.guild.id, "ngword_timeout") or 600)
                try:
                    await message.author.timeout(discord.utils.utcnow() + discord.timedelta(seconds=timeout_seconds),
                                                 reason=f"NGワード検出（'{word}'）")
                    await message.channel.send(f"🚫 {message.author.mention} がNGワードによりタイムアウトされました（{timeout_seconds // 60}分）", delete_after=10)
                except Exception:
                    pass
                break

    @app_commands.command(name="ngword_add", description="NGワードを追加します。")
    async def ngword_add(self, interaction: discord.Interaction, word: str, channel: discord.TextChannel = None):
        await self.ensure_tables()
        cid = channel.id if channel else None
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO ngwords (guild_id, channel_id, word) VALUES (?, ?, ?)",
                             (interaction.guild.id, cid, word))
            await db.commit()
        await interaction.response.send_message(f"✅ NGワード `{word}` を追加しました。")

    @app_commands.command(name="ngword_remove", description="NGワードを削除します。")
    async def ngword_remove(self, interaction: discord.Interaction, word: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM ngwords WHERE guild_id = ? AND word = ?", (interaction.guild.id, word))
            await db.commit()
        await interaction.response.send_message(f"🗑️ NGワード `{word}` を削除しました。")

    @app_commands.command(name="ngword_set_timeout", description="NGワード検出時のタイムアウト秒数を設定します。")
    async def ngword_set_timeout(self, interaction: discord.Interaction, seconds: int):
        await self.bot.get_cog("DBHandler").set_setting(interaction.guild.id, "ngword_timeout", str(seconds))
        await interaction.response.send_message(f"✅ タイムアウト時間を {seconds}秒 に設定しました。")

async def setup(bot):
    await bot.add_cog(WordFilter(bot))
