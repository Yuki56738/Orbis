import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncpg
import json
import datetime

class PollButton(discord.ui.Button):
    def __init__(self, label: str, poll_id: int, option_index: int):
        super().__init__(style=discord.ButtonStyle.primary, label=label, custom_id=f"poll_{poll_id}_{option_index}")
        self.poll_id = poll_id
        self.option_index = option_index

    async def callback(self, interaction: discord.Interaction):
        cog: Poll = interaction.client.get_cog("Poll")
        if cog:
            await cog.register_vote(interaction, self.poll_id, self.option_index)

class PollView(discord.ui.View):
    def __init__(self, poll_id: int, options: list[str], timeout: int):
        super().__init__(timeout=timeout)
        for i, option in enumerate(options):
            self.add_item(PollButton(option, poll_id, i))

class Poll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db: asyncpg.Pool = None
        self.poll_timeout_check.start()

    async def cog_load(self):
        self.db = self.bot.get_cog("DBHandler").pool  # DBHandlerのpoolを使う
        await self.create_tables()

    def cog_unload(self):
        self.poll_timeout_check.cancel()

    async def create_tables(self):
        async with self.db.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS polls (
                    poll_id SERIAL PRIMARY KEY,
                    guild_id BIGINT,
                    channel_id BIGINT,
                    message_id BIGINT,
                    creator_id BIGINT,
                    question TEXT,
                    options JSONB,
                    expires_at BIGINT,
                    ended BOOLEAN DEFAULT FALSE
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS votes (
                    vote_id SERIAL PRIMARY KEY,
                    poll_id INTEGER REFERENCES polls(poll_id) ON DELETE CASCADE,
                    user_id BIGINT,
                    option_index INTEGER,
                    UNIQUE(poll_id, user_id)
                )
            """)

    @tasks.loop(seconds=10)
    async def poll_timeout_check(self):
        now_ts = int(datetime.datetime.utcnow().timestamp())
        async with self.db.acquire() as conn:
            rows = await conn.fetch("SELECT poll_id, creator_id, options FROM polls WHERE ended = FALSE AND expires_at <= $1", now_ts)
            for row in rows:
                await self.finish_poll(conn, row["poll_id"], row["creator_id"], row["options"])

    async def finish_poll(self, conn, poll_id: int, creator_id: int, options_json: str):
        options = json.loads(options_json)
        counts = {i: 0 for i in range(len(options))}
        vote_rows = await conn.fetch("SELECT option_index, COUNT(*) AS cnt FROM votes WHERE poll_id = $1 GROUP BY option_index", poll_id)
        for row in vote_rows:
            counts[row["option_index"]] = row["cnt"]

        total_votes = sum(counts.values())
        result = f"📊 投票結果（ID: {poll_id}）\n"
        for i, opt in enumerate(options):
            result += f"**{opt}** ： {counts[i]}票\n"
        result += f"合計投票数：{total_votes}票"

        creator = self.bot.get_user(creator_id)
        if creator:
            try:
                await creator.send(result)
            except:
                pass

        await conn.execute("UPDATE polls SET ended = TRUE WHERE poll_id = $1", poll_id)

    async def register_vote(self, interaction: discord.Interaction, poll_id: int, option_index: int):
        user_id = interaction.user.id
        async with self.db.acquire() as conn:
            exists = await conn.fetchval("SELECT 1 FROM votes WHERE poll_id = $1 AND user_id = $2", poll_id, user_id)
            if exists:
                await interaction.response.send_message("❌ あなたはすでに投票済みです。", ephemeral=True)
                return

            await conn.execute(
                "INSERT INTO votes (poll_id, user_id, option_index) VALUES ($1, $2, $3)",
                poll_id, user_id, option_index
            )
            await interaction.response.send_message(f"✅ `{option_index + 1}`番目の選択肢に投票しました。", ephemeral=True)

    @app_commands.command(name="poll", description="投票を開始します。")
    @app_commands.describe(
        question="投票の質問",
        options="選択肢をカンマ区切りで入力（最大10個）",
        duration="投票時間（秒）"
    )
    async def poll(self, interaction: discord.Interaction, question: str, options: str, duration: int = 60):
        option_list = [opt.strip() for opt in options.split(",") if opt.strip()]
        if not (2 <= len(option_list) <= 10):
            await interaction.response.send_message("❌ 選択肢は2〜10個で入力してください。", ephemeral=True)
            return
        if not (10 <= duration <= 86400):
            await interaction.response.send_message("❌ 投票時間は10〜86400秒（24時間）以内で指定してください。", ephemeral=True)
            return

        expires_at = int((datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)).timestamp())

        async with self.db.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO polls (guild_id, channel_id, creator_id, question, options, expires_at, ended)
                VALUES ($1, $2, $3, $4, $5, $6, FALSE)
                RETURNING poll_id
            """, interaction.guild.id, interaction.channel.id, interaction.user.id, question, json.dumps(option_list), expires_at)

            poll_id = row["poll_id"]

        embed = discord.Embed(title="📊 投票開始！", description=question, color=discord.Color.blurple())
        for i, opt in enumerate(option_list):
            embed.add_field(name=f"{i+1}. {opt}", value="\u200b", inline=False)
        embed.set_footer(text=f"投票終了まで{duration}秒")

        view = PollView(poll_id, option_list, timeout=duration)
        msg = await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ 投票を開始しました。", ephemeral=True)

        # message_id を保存
        async with self.db.acquire() as conn:
            await conn.execute("UPDATE polls SET message_id = $1 WHERE poll_id = $2", msg.id, poll_id)

async def setup(bot):
    await bot.add_cog(Poll(bot))
