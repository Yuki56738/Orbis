import asyncpg
from discord.ext import commands
import json
import datetime

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
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_pet_actions (
                    guild_id BIGINT,
                    user_id BIGINT,
                    action_date DATE,
                    command_count INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id, action_date)
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS global_events (
                    user_id BIGINT,
                    image_url TEXT,
                    comment TEXT,
                    votes INT DEFAULT 0,
                    see_id TEXT
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

    # 冒険状態JSON操作
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

    # ペット行動回数の取得
    async def get_pet_action_count(self, guild_id: int) -> int:
        query = "SELECT total_pet_actions FROM pet_reward_stats WHERE guild_id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, guild_id)
            return row["total_pet_actions"] if row else 0

    # 新コマンド実行履歴をインクリメント
    async def increment_pet_action_count(self, guild_id: int, user_id: int):
        today = datetime.utcnow().date()
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_pet_actions (guild_id, user_id, action_date, command_count)
                VALUES ($1, $2, $3, 1)
                ON CONFLICT (guild_id, user_id, action_date)
                DO UPDATE SET command_count = user_pet_actions.command_count + 1
            """, guild_id, user_id, today)

    # その日の合計アクション数を取得（数値A）
    async def get_today_action_count(self, guild_id: int, user_id: int) -> int:
        today = datetime.utcnow().date()
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT command_count FROM user_pet_actions
                WHERE guild_id = $1 AND user_id = $2 AND action_date = $3
            """, guild_id, user_id, today)
            return row["command_count"] if row else 0

    # 全ユーザー分の今日のコマンド履歴を取得（自動報酬用途）
    async def get_all_today_pet_actions(self):
        today = datetime.utcnow().date()
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT guild_id, user_id, command_count FROM user_pet_actions
                WHERE action_date = $1
            """, today)

    # 履歴を削除（報酬配布後リセット用）
    async def reset_pet_action_counts(self):
        today = datetime.utcnow().date()
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM user_pet_actions WHERE action_date = $1", today)
    
    # キャラ選択
    async def set_partner_character(self, user_id: int, character_id: str):
        await self.set_user_setting(user_id, "partner_character", character_id)

    # キャラ取得
    async def get_partner_character(self, user_id: int) -> str | None:
        return await self.get_user_setting(user_id, "partner_character")
    
    # ───────── 恋愛系ステータスの保存と取得 ───────── #

    # 恋愛度（キャラの依存度）
    async def get_affection(self, user_id: int) -> int:
        val = await self.get_user_setting(user_id, "affection")
        return int(val) if val else 0

    async def set_affection(self, user_id: int, value: int):
        await self.set_user_setting(user_id, "affection", str(value))

    async def increment_affection(self, user_id: int, delta: int = 1):
        current = await self.get_affection(user_id)
        await self.set_affection(user_id, current + delta)

    # 好感度（キャラの好きの強さ）
    async def get_likeability(self, user_id: int) -> int:
        val = await self.get_user_setting(user_id, "likeability")
        return int(val) if val else 0

    async def set_likeability(self, user_id: int, value: int):
        await self.set_user_setting(user_id, "likeability", str(value))

    async def increment_likeability(self, user_id: int, delta: int = 1):
        current = await self.get_likeability(user_id)
        await self.set_likeability(user_id, current + delta)

    # 親密度（キャラがユーザーをどれだけ受け入れているか）
    async def get_intimacy(self, user_id: int) -> int:
        val = await self.get_user_setting(user_id, "intimacy")
        return int(val) if val else 0

    async def set_intimacy(self, user_id: int, value: int):
        await self.set_user_setting(user_id, "intimacy", str(value))

    async def increment_intimacy(self, user_id: int, delta: int = 1):
        current = await self.get_intimacy(user_id)
        await self.set_intimacy(user_id, current + delta)

    # ───────── 季節別イベント ───────── #

    # 投稿の追加
    async def add_event_submission(self, user_id: int, image_url: str, comment: str, see_id: int):
        query = """
            INSERT INTO global_events (user_id, image_url, comment, votes, see_id)
            VALUES ($1, $2, $3, 0, $4)
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id, image_url, comment, see_id)

    # 投稿の取得（全件 or 特定see_id）
    async def get_event_submissions(self, see_id: int = None):
        async with self.pool.acquire() as conn:
            if see_id is not None:
                query = "SELECT * FROM global_events WHERE see_id = $1 ORDER BY votes DESC"
                return await conn.fetch(query, see_id)
            else:
                query = "SELECT * FROM global_events ORDER BY votes DESC"
                return await conn.fetch(query)

    # 投票を追加
    async def vote_event_submission(self, see_id: int):
        query = "UPDATE global_events SET votes = votes + 1 WHERE see_id = $1"
        async with self.pool.acquire() as conn:
            await conn.execute(query, see_id)

    # 投票数のリセット（イベント終了時）
    async def reset_event_votes(self):
        query = "UPDATE global_events SET votes = 0"
        async with self.pool.acquire() as conn:
            await conn.execute(query)

    # イベントデータの削除（初期化）
    async def clear_event_submissions(self):
        query = "DELETE FROM global_events"
        async with self.pool.acquire() as conn:
            await conn.execute(query)

    # 次に使えるsee_idを取得（最大値+1）
    async def get_next_see_id(self) -> int:
        query = "SELECT MAX(see_id) AS max_id FROM global_events"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query)
            return (row["max_id"] or 0) + 1

    # see_idから投稿を1件取得
    async def get_event_submission_by_see_id(self, see_id: int):
        query = "SELECT * FROM global_events WHERE see_id = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, see_id)


async def setup(bot):
    await bot.add_cog(UserDBHandler(bot))
