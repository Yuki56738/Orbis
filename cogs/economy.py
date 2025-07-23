import asyncpg
import random
import datetime
from discord.ext import commands
from discord import app_commands, Interaction, Member, Message
import discord

DB_CONFIG = {
    "user": "orbisuser",
    "password": "orbispass",
    "database": "orbis",
    "host": "orbis-db",
    "port": 5432,
}

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pool = None

    async def cog_load(self):
        self.pool = await asyncpg.create_pool(**DB_CONFIG)

    async def get_setting(self, user_id: int, key: str, default=None, cast_type=int):
        query = "SELECT value FROM user_settings WHERE user_id = $1 AND key = $2"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, key)
            if row:
                try:
                    return cast_type(row["value"])
                except:
                    return default
            return default

    async def set_setting(self, user_id: int, key: str, value: str | int):
        query = """
            INSERT INTO user_settings (user_id, key, value)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, key)
            DO UPDATE SET value = EXCLUDED.value
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id, key, str(value))

    # ------- Balance Management -------

    async def get_balance(self, user_id: int) -> int:
        return await self.get_setting(user_id, "balance", 0)

    async def set_balance(self, user_id: int, amount: int):
        await self.set_setting(user_id, "balance", amount)
        await self.recalculate_level(user_id)

    async def add_balance(self, user_id: int, amount: int) -> bool:
        current = await self.get_balance(user_id)
        new_amount = current + amount
        if new_amount < 0:
            return False
        await self.set_balance(user_id, new_amount)
        return True

    async def subtract_balance(self, user_id: int, amount: int) -> bool:
        current = await self.get_balance(user_id)
        if current < amount:
            return False
        await self.set_balance(user_id, current - amount)
        return True

    # ------- Activity & Level -------

    async def get_activity(self, user_id: int) -> float:
        return await self.get_setting(user_id, "activity_score", 100, float)

    async def set_activity(self, user_id: int, value: float):
        await self.set_setting(user_id, "activity_score", round(value, 2))
        await self.recalculate_level(user_id)

    async def recalculate_level(self, user_id: int):
        activity = await self.get_activity(user_id)
        balance = await self.get_balance(user_id)
        total = activity + balance
        level = 1
        threshold = 500
        increment = 150
        while total >= threshold:
            level += 1
            threshold += increment
            increment += 150  # 累積的に増加
        await self.set_setting(user_id, "level", level)

    async def get_level(self, user_id: int) -> int:
        return await self.get_setting(user_id, "level", 1)

    # ------- Message Rewarding -------

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        if message.author.bot or len(message.content.strip()) < 5:
            return

        user_id = message.author.id
        today = datetime.date.today()
        last_date_str = await self.get_setting(user_id, "last_active_date", None, str)

        # 活発度の更新
        reset = False
        if last_date_str:
            last_date = datetime.date.fromisoformat(last_date_str)
            if (today - last_date).days >= 2:
                await self.set_activity(user_id, 100)
                reset = True
        await self.set_setting(user_id, "last_active_date", today.isoformat())

        # 活発度加算
        activity = await self.get_activity(user_id)
        activity += round(random.uniform(0.5, 1.0), 2)
        await self.set_activity(user_id, activity)

        # 報酬確率チェック
        if random.randint(1, 10) <= 3:
            level = await self.get_level(user_id)
            base_income = int(activity * level * 10)

            # ログインボーナス（当日初投稿）
            if reset or (not last_date_str):
                base_income *= 10

            await self.add_balance(user_id, base_income)

    # ------- /balance -------

    @app_commands.command(name="balance", description="あなたの所持金を表示します。")
    async def balance(self, interaction: Interaction):
        bal = await self.get_balance(interaction.user.id)
        level = await self.get_level(interaction.user.id)
        await interaction.response.send_message(
            f"💰 {interaction.user.mention} の所持金は {bal} 円です。現在のレベルは Lv.{level} です。")

    # ------- /pay -------

    @app_commands.command(name="pay", description="他のユーザーにお金を送ります。")
    @app_commands.describe(target="送金相手", amount="送金金額")
    async def pay(self, interaction: Interaction, target: Member, amount: int):
        if amount <= 0:
            return await interaction.response.send_message("❌ 金額は1以上にしてください。", ephemeral=True)
        if target.bot or target.id == interaction.user.id:
            return await interaction.response.send_message("❌ 無効な相手です。", ephemeral=True)
        if not await self.subtract_balance(interaction.user.id, amount):
            return await interaction.response.send_message("❌ 残高不足です。", ephemeral=True)
        await self.add_balance(target.id, amount)
        await interaction.response.send_message(f"✅ {interaction.user.mention} → {target.mention} に {amount} 円を送金しました。")

    # ------- /setbalance (管理者のみ) -------

    @app_commands.command(name="setbalance", description="管理者用：ユーザーの所持金を設定します。")
    @app_commands.describe(user="対象ユーザー", amount="設定金額")
    async def setbalance(self, interaction: Interaction, user: Member, amount: int):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("🚫 管理者専用です。", ephemeral=True)
        if amount < 0:
            return await interaction.response.send_message("❌ 0以上の金額を入力してください。", ephemeral=True)
        await self.set_balance(user.id, amount)
        await interaction.response.send_message(f"✅ {user.mention} の所持金を {amount} 円に設定しました。")

    # ------- /work -------

    @app_commands.command(name="work", description="働いてお金を稼ぎます。（1時間に1回）")
    async def work(self, interaction: Interaction):
        user_id = interaction.user.id
        now = datetime.datetime.utcnow()
        last_str = await self.get_setting(user_id, "last_work_time", None, str)

        if last_str:
            last_time = datetime.datetime.fromisoformat(last_str)
            if (now - last_time).total_seconds() < 3600:
                remaining = int(3600 - (now - last_time).total_seconds())
                minutes, seconds = divmod(remaining, 60)
                return await interaction.response.send_message(
                    f"⏳ 次の /work まで {minutes}分{seconds}秒 残っています。", ephemeral=True
                )

        activity = await self.get_activity(user_id)
        level = await self.get_level(user_id)
        base = int(activity * level * 10)
        income = random.randint(int(base * 1.5), int(base * 2.0))

        await self.add_balance(user_id, income)
        await self.set_setting(user_id, "last_work_time", now.isoformat())

        await interaction.response.send_message(f"💼 お疲れさまです！{income} 円を獲得しました。")

async def setup(bot):
    await bot.add_cog(Economy(bot))
