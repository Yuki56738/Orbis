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
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pet_reward_stats (
                    guild_id BIGINT PRIMARY KEY,
                    total_pet_actions INTEGER DEFAULT 0
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
    # ペット行動回数の加算
    async def increment_pet_action_count(self, guild_id: int):
        query = """
            INSERT INTO pet_reward_stats (guild_id, total_pet_actions)
            VALUES ($1, 1)
            ON CONFLICT (guild_id)
            DO UPDATE SET total_pet_actions = pet_reward_stats.total_pet_actions + 1
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, guild_id)

    # ペット行動回数の取得
    async def get_pet_action_count(self, guild_id: int) -> int:
        query = "SELECT total_pet_actions FROM pet_reward_stats WHERE guild_id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, guild_id)
            return row["total_pet_actions"] if row else 0


async def setup(bot):
    await bot.add_cog(UserDBHandler(bot))
