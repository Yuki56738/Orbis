import discord
from discord.ext import commands
import aiosqlite
import os

DB_PATH = "./orbis.db"

class DBHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.db = None

    async def create_table_if_needed(self, guild_id: int):
        table_name = f"settings_{guild_id}"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            await db.commit()

    async def set_setting(self, guild_id: int, key: str, value: str):
        table_name = f"settings_{guild_id}"
        await self.create_table_if_needed(guild_id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(f"""
                INSERT INTO {table_name} (key, value) 
                VALUES (?, ?) 
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """, (key, value))
            await db.commit()

    async def get_setting(self, guild_id: int, key: str) -> str | None:
        table_name = f"settings_{guild_id}"
        await self.create_table_if_needed(guild_id)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(f"SELECT value FROM {table_name} WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def delete_setting(self, guild_id: int, key: str):
        table_name = f"settings_{guild_id}"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(f"DELETE FROM {table_name} WHERE key = ?", (key,))
            await db.commit()

    # 新規追加：guild専用設定テーブルを丸ごと削除
    async def drop_guild_table(self, guild_id: int):
        table_name = f"settings_{guild_id}"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(f"DROP TABLE IF EXISTS {table_name}")
            await db.commit()

async def setup(bot):
    await bot.add_cog(DBHandler(bot))
