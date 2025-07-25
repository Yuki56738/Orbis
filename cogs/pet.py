import discord
from discord import app_commands
from discord.ext import commands
import asyncpg
import random
from datetime import datetime
from utils.item import use_item
from utils.economy_api import EconomyAPI
import asyncio

class Pet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pool: asyncpg.Pool = None

    async def cog_load(self):
        self.pool = self.bot.db.pool
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pets (
                    guild_id BIGINT PRIMARY KEY,
                    pet_name TEXT,
                    level INT DEFAULT 1,
                    experience INT DEFAULT 0,
                    affection INT DEFAULT 0,
                    stage TEXT DEFAULT 'egg',
                    emotion TEXT DEFAULT 'neutral',
                    last_fed TIMESTAMP,
                    last_battle TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

    # ---------- 内部ユーティリティ ----------
    async def get_pet(self, guild_id: int):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM pets WHERE guild_id = $1", guild_id)

    async def update_pet(self, guild_id: int, **kwargs):
        keys = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
        values = list(kwargs.values())
        async with self.pool.acquire() as conn:
            await conn.execute(f"UPDATE pets SET {keys} WHERE guild_id = $1", guild_id, *values)

    async def create_pet(self, guild_id: int, name: str):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO pets (guild_id, pet_name)
                VALUES ($1, $2)
            """, guild_id, name)

    async def delete_pet(self, guild_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM pets WHERE guild_id = $1", guild_id)

    async def send_reward_to_user(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        user_id = interaction.user.id

        userdb = self.bot.get_cog("UserDBHandler")
        economy: EconomyAPI = self.bot.get_cog("EconomyAPI")

        total_actions = await userdb.get_pet_action_count(guild_id)
        random_multiplier = random.randint(50, 100)
        reward_amount = total_actions * random_multiplier

        await economy.add_money(guild_id, user_id, reward_amount)

        await asyncio.sleep(3)
        try:
            await interaction.user.send(f"🎉 ペットと遊んだご褒美として {reward_amount} コインを獲得しました！")
        except discord.Forbidden:
            await interaction.response.send_message("💡 DMが送れませんでした！設定を確認してください。", ephemeral=True)

    # ---------- スラッシュコマンド ----------
    @app_commands.command(name="pet_create", description="サーバーにペットを生み出します！")
    async def create(self, interaction: discord.Interaction, name: str):
        if await self.get_pet(interaction.guild_id):
            return await interaction.response.send_message("このサーバーにはすでにペットがいます！", ephemeral=True)
        await self.create_pet(interaction.guild_id, name)
        await interaction.response.send_message(f"🐣 ペット `{name}` が誕生しました！大切に育ててね！")

    @app_commands.command(name="pet_status", description="ペットの状態を確認します。")
    async def status(self, interaction: discord.Interaction):
        pet = await self.get_pet(interaction.guild_id)
        if not pet:
            return await interaction.response.send_message("このサーバーにはまだペットがいません！", ephemeral=True)
        embed = discord.Embed(title=f"🐾 {pet['pet_name']} のステータス", color=0x88ccff)
        embed.add_field(name="レベル", value=pet["level"])
        embed.add_field(name="経験値", value=pet["experience"])
        embed.add_field(name="好感度", value=pet["affection"])
        embed.add_field(name="成長段階", value=pet["stage"])
        embed.add_field(name="感情", value=pet["emotion"])
        embed.add_field(name="誕生日", value=pet["created_at"].strftime("%Y-%m-%d"))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="pet_feed", description="ペットにご飯をあげよう！")
    async def feed(self, interaction: discord.Interaction):
        pet = await self.get_pet(interaction.guild_id)
        if not pet:
            return await interaction.response.send_message("まだペットがいません！", ephemeral=True)

        await self.update_pet(
            interaction.guild_id,
            last_fed=datetime.utcnow(),
            experience=pet["experience"] + 10,
            affection=pet["affection"] + 2,
            emotion="happy"
        )

        userdb = self.bot.get_cog("UserDBHandler")
        await userdb.increment_pet_action_count(interaction.guild_id)
        await self.send_reward_to_user(interaction)

        await interaction.response.send_message("🍎 ペットにご飯をあげました！うれしそう！")

    @app_commands.command(name="pet_gift", description="アイテムをプレゼントして喜ばせよう！")
    async def gift(self, interaction: discord.Interaction, item_id: str):
        gov_id = f"{interaction.guild_id}-{interaction.user.id}"
        success = await use_item(gov_id, item_id)
        if not success:
            return await interaction.response.send_message("そのアイテムは持っていないか、使用できません！", ephemeral=True)

        pet = await self.get_pet(interaction.guild_id)
        await self.update_pet(
            interaction.guild_id,
            affection=pet["affection"] + 10,
            emotion="happy"
        )

        userdb = self.bot.get_cog("UserDBHandler")
        await userdb.increment_pet_action_count(interaction.guild_id)
        await self.send_reward_to_user(interaction)

        await interaction.response.send_message("🎁 プレゼントを渡しました！とっても喜んでいる！")

    @app_commands.command(name="pet_birthday", description="ペットの誕生日を祝おう！")
    async def birthday(self, interaction: discord.Interaction):
        pet = await self.get_pet(interaction.guild_id)
        if not pet:
            return await interaction.response.send_message("ペットがいません！", ephemeral=True)
        created = pet["created_at"].strftime("%Y-%m-%d")
        await interaction.response.send_message(f"🎂 この子の誕生日は `{created}` だよ！おめでとうって言ってあげてね！")

        userdb = self.bot.get_cog("UserDBHandler")
        await userdb.increment_pet_action_count(interaction.guild_id)
        await self.send_reward_to_user(interaction)

    @app_commands.command(name="pet_name", description="ペットの名前を変える")
    async def rename(self, interaction: discord.Interaction, new_name: str):
        pet = await self.get_pet(interaction.guild_id)
        if not pet:
            return await interaction.response.send_message("ペットがいません！", ephemeral=True)
        if pet["affection"] < 10:
            return await interaction.response.send_message("もっと仲良くならないと名前を変えたくないみたい！", ephemeral=True)
        await self.update_pet(interaction.guild_id, pet_name=new_name)
        await interaction.response.send_message(f"📛 ペットの名前が `{new_name}` に変わりました！")

    @app_commands.command(name="pet_reset", description="ペットを削除します。")
    async def reset(self, interaction: discord.Interaction):
        await self.delete_pet(interaction.guild_id)
        await interaction.response.send_message("⚠️ ペットを削除しました。新しい子を育ててみよう！")

    @app_commands.command(name="pet_emotion", description="今の感情を確認します")
    async def emotion(self, interaction: discord.Interaction):
        pet = await self.get_pet(interaction.guild_id)
        if not pet:
            return await interaction.response.send_message("ペットがいません！", ephemeral=True)
        await interaction.response.send_message(f"現在の感情は `{pet['emotion']}` です！")

    @app_commands.command(name="pet_affection", description="好感度を確認します")
    async def affection(self, interaction: discord.Interaction):
        pet = await self.get_pet(interaction.guild_id)
        if not pet:
            return await interaction.response.send_message("ペットがいません！", ephemeral=True)
        await interaction.response.send_message(f"💕 好感度は `{pet['affection']}` です！")

    @app_commands.command(name="pet_talk", description="ペットと会話します。")
    async def talk(self, interaction: discord.Interaction):
        pet = await self.get_pet(interaction.guild_id)
        if not pet:
            return await interaction.response.send_message("ペットがいません！", ephemeral=True)
        emotion = pet["emotion"]
        messages = {
            "happy": "わーい！きみとお話するのだいすき！",
            "sad": "うぅ…ひとりはさみしいよ…",
            "angry": "むーっ！ぼくにかまってくれなかった！",
            "neutral": "こんにちは！今日もがんばろーね！",
        }
        await interaction.response.send_message(messages.get(emotion, "……。"))

    @app_commands.command(name="pet_mood", description="今日の気分をきいてみる")
    async def mood(self, interaction: discord.Interaction):
        moods = ["きょうはいい日になりそう！", "ねむいなぁ…", "おなかすいたかも", "きみにあえてうれしい！"]
        await interaction.response.send_message(random.choice(moods))

async def setup(bot):
    await bot.add_cog(Pet(bot))
