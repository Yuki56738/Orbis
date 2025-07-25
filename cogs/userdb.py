import asyncpg
from discord.ext import commands
import json

DB_CONFIG = {
    "user": "orbisuser",
    "password": "orbispass",
    "database": "orbis",
    "host": "orbis-db",
    "port": 5432,
}

class UserDBHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pool = None

    async def cog_load(self):
        self.pool = await asyncpg.create_pool(**DB_CONFIG)
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id BIGINT,
                    key TEXT,
                    value TEXT,
                    PRIMARY KEY (user_id, key)
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_adventure_states (
                    user_id BIGINT PRIMARY KEY,
                    adventure_state JSONB
                );
            """)

    # 既存のキー・バリュー操作
    async def set_user_setting(self, user_id: int, key: str, value: str):
        query = """
            INSERT INTO user_settings (user_id, key, value)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, key)
            DO UPDATE SET value = EXCLUDED.value
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id, key, value)

    async def get_user_setting(self, user_id: int, key: str) -> str | None:
        query = "SELECT value FROM user_settings WHERE user_id = $1 AND key = $2"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, key)
            return row["value"] if row else None

    async def delete_user_setting(self, user_id: int, key: str):
        query = "DELETE FROM user_settings WHERE user_id = $1 AND key = $2"
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id, key)

    # 【追加】冒険状態JSON操作
    async def set_adventure_state(self, user_id: int, state: dict):
        query = """
            INSERT INTO user_adventure_states (user_id, adventure_state)
            VALUES ($1, $2)
            ON CONFLICT (user_id)
            DO UPDATE SET adventure_state = EXCLUDED.adventure_state
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id, json.dumps(state))

    async def get_adventure_state(self, user_id: int) -> dict | None:
        query = "SELECT adventure_state FROM user_adventure_states WHERE user_id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id)
            return row["adventure_state"] if row else None

    async def clear_adventure_state(self, user_id: int):
        query = "DELETE FROM user_adventure_states WHERE user_id = $1"
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id)

async def setup(bot):
    await bot.add_cog(UserDBHandler(bot))
