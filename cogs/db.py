import asyncpg
from discord.ext import commands

DB_CONFIG = {
    "user": "orbisuser",
    "password": "orbispass",
    "database": "orbis",
    "host": "orbis-db",
    "port": 5432,
}

class DBHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pool = None

    async def cog_load(self):
        self.pool = await asyncpg.create_pool(**DB_CONFIG)
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    guild_id BIGINT,
                    key TEXT,
                    value TEXT,
                    PRIMARY KEY (guild_id, key)
                );
            """)

    async def set_setting(self, guild_id: int, key: str, value: str):
        query = """
            INSERT INTO settings (guild_id, key, value)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, key)
            DO UPDATE SET value = EXCLUDED.value
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, guild_id, key, value)

    async def get_setting(self, guild_id: int, key: str) -> str | None:
        query = "SELECT value FROM settings WHERE guild_id = $1 AND key = $2"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, guild_id, key)
            return row["value"] if row else None

    async def delete_setting(self, guild_id: int, key: str):
        query = "DELETE FROM settings WHERE guild_id = $1 AND key = $2"
        async with self.pool.acquire() as conn:
            await conn.execute(query, guild_id, key)

    async def delete_all_settings_for_guild(self, guild_id: int):
        query = "DELETE FROM settings WHERE guild_id = $1"
        async with self.pool.acquire() as conn:
            await conn.execute(query, guild_id)

async def setup(bot):
    await bot.add_cog(DBHandler(bot))
