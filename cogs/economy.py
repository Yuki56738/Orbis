import asyncpg
from discord.ext import commands
from discord import app_commands

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
        # user_settingsテーブルはUserDBHandlerで作成済み前提

    async def get_balance(self, user_id: int) -> int:
        query = "SELECT value FROM user_settings WHERE user_id = $1 AND key = 'balance'"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id)
            if row is None:
                return 0
            try:
                return int(row["value"])
            except Exception:
                return 0

    async def set_balance(self, user_id: int, amount: int):
        query = """
            INSERT INTO user_settings (user_id, key, value)
            VALUES ($1, 'balance', $2)
            ON CONFLICT (user_id, key)
            DO UPDATE SET value = EXCLUDED.value
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id, str(amount))

    async def add_balance(self, user_id: int, amount: int) -> bool:
        # amountは正の整数で加算。負は使わないで。
        current = await self.get_balance(user_id)
        new_amount = current + amount
        if new_amount < 0:
            return False
        await self.set_balance(user_id, new_amount)
        return True

    async def subtract_balance(self, user_id: int, amount: int) -> bool:
        # 残高不足ならFalse返す
        current = await self.get_balance(user_id)
        if current < amount:
            return False
        new_amount = current - amount
        await self.set_balance(user_id, new_amount)
        return True

    @app_commands.command(name="balance", description="あなたの所持金を表示します。")
    async def balance(self, interaction: commands.Context):
        user_id = interaction.user.id
        bal = await self.get_balance(user_id)
        await interaction.response.send_message(f"💰 {interaction.user.mention} の所持金は {bal} 円です。")

    @app_commands.command(name="pay", description="他のユーザーにお金を送ります。")
    @app_commands.describe(target="送金相手", amount="送金金額")
    async def pay(self, interaction: commands.Interaction, target: commands.MemberConverter, amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ 送金金額は1以上の整数で指定してください。", ephemeral=True)
            return
        if target.bot:
            await interaction.response.send_message("❌ Botには送金できません。", ephemeral=True)
            return
        sender_id = interaction.user.id
        receiver_id = target.id
        if sender_id == receiver_id:
            await interaction.response.send_message("❌ 自分自身には送金できません。", ephemeral=True)
            return
        # 残高チェック
        if not await self.subtract_balance(sender_id, amount):
            await interaction.response.send_message("❌ 残高不足です。", ephemeral=True)
            return
        await self.add_balance(receiver_id, amount)
        await interaction.response.send_message(f"✅ {interaction.user.mention} から {target.mention} に {amount} 円を送金しました。")

    @app_commands.command(name="setbalance", description="管理者用：ユーザーの所持金を設定します。")
    @app_commands.describe(user="対象ユーザー", amount="設定する所持金")
    async def setbalance(self, interaction: commands.Interaction, user: commands.MemberConverter, amount: int):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🚫 管理者のみ使用可能です。", ephemeral=True)
            return
        if amount < 0:
            await interaction.response.send_message("❌ 所持金は0以上の整数で設定してください。", ephemeral=True)
            return
        await self.set_balance(user.id, amount)
        await interaction.response.send_message(f"✅ {user.mention} の所持金を {amount} 円に設定しました。")

async def setup(bot):
    await bot.add_cog(Economy(bot))
