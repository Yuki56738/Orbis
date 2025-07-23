import asyncpg
from discord.ext import commands

DB_CONFIG = {
    "user": "orbisuser",
    "password": "orbispass",
    "database": "orbis",
    "host": "orbis-db",  # Docker Compose内のサービス名
    "port": 5432,
}

class DBHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pool = None

    async def cog_load(self):
        self.pool = await asyncpg.create_pool(**DB_CONFIG)

    async def create_table_if_needed(self, guild_id: int):
        table_name = f"settings_{guild_id}"
        query = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query)

    async def set_setting(self, guild_id: int, key: str, value: str):
        await self.create_table_if_needed(guild_id)
        table_name = f"settings_{guild_id}"
        query = f"""
            INSERT INTO {table_name} (key, value) 
            VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, key, value)

    async def get_setting(self, guild_id: int, key: str) -> str | None:
        table_name = f"settings_{guild_id}"
        await self.create_table_if_needed(guild_id)
        query = f"SELECT value FROM {table_name} WHERE key = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, key)
            return row["value"] if row else None

    async def delete_setting(self, guild_id: int, key: str):
        table_name = f"settings_{guild_id}"
        query = f"DELETE FROM {table_name} WHERE key = $1"
        async with self.pool.acquire() as conn:
            await conn.execute(query, key)

    async def drop_guild_table(self, guild_id: int):
        table_name = f"settings_{guild_id}"
        query = f"DROP TABLE IF EXISTS {table_name}"
        async with self.pool.acquire() as conn:
            await conn.execute(query)

async def setup(bot):
    await bot.add_cog(DBHandler(bot))
