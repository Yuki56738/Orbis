import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import asyncio
import json
import datetime

DB_PATH = "./orbis.db"

class PollButton(discord.ui.Button):
    def __init__(self, label: str, poll_id: int, option_index: int):
        super().__init__(style=discord.ButtonStyle.primary, label=label, custom_id=f"poll_{poll_id}_{option_index}")
        self.poll_id = poll_id
        self.option_index = option_index

    async def callback(self, interaction: discord.Interaction):
        cog: Poll = interaction.client.get_cog("Poll")
        if not cog:
            await interaction.response.send_message("エラー: Cogが見つかりません。", ephemeral=True)
            return
        await cog.register_vote(interaction, self.poll_id, self.option_index)

class PollView(discord.ui.View):
    def __init__(self, poll_id: int, options: list[str], timeout: int):
        super().__init__(timeout=timeout)
        self.poll_id = poll_id
        for i, option in enumerate(options):
            self.add_item(PollButton(option, poll_id, i))

class Poll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_polls = {}  # poll_id: task
        self.poll_timeout_check.start()

    def cog_unload(self):
        self.poll_timeout_check.cancel()

    @tasks.loop(seconds=10)
    async def poll_timeout_check(self):
        # 定期的に期限切れポールを確認し結果送信
        async with aiosqlite.connect(DB_PATH) as db:
            now_ts = int(datetime.datetime.utcnow().timestamp())
            async with db.execute("SELECT poll_id, creator_id FROM polls WHERE ended = 0 AND expires_at <= ?", (now_ts,)) as cursor:
                rows = await cursor.fetchall()
                for poll_id, creator_id in rows:
                    await self.finish_poll(poll_id, creator_id)

    async def finish_poll(self, poll_id: int, creator_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            # 投票結果取得
            async with db.execute("SELECT option_index, COUNT(*) FROM votes WHERE poll_id = ? GROUP BY option_index", (poll_id,)) as cursor:
                vote_counts = await cursor.fetchall()
            # オプション数取得
            async with db.execute("SELECT options FROM polls WHERE poll_id = ?", (poll_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return
                options = json.loads(row[0])
            # 結果集計
            counts = {idx: 0 for idx in range(len(options))}
            for option_index, count in vote_counts:
                counts[option_index] = count

            total_votes = sum(counts.values())
            # メッセージ生成
            msg = f"📊 投票結果（ID: {poll_id}）\n"
            for idx, option in enumerate(options):
                msg += f"**{option}** ： {counts[idx]}票\n"
            msg += f"合計投票数：{total_votes}票"

            # 送信
            creator = self.bot.get_user(creator_id)
            if creator:
                try:
                    await creator.send(msg)
                except:
                    # DM拒否などで送れなかった場合は無視
                    pass

            # pollsテーブルのendedを立てる
            await db.execute("UPDATE polls SET ended = 1 WHERE poll_id = ?", (poll_id,))
            await db.commit()

    async def register_vote(self, interaction: discord.Interaction, poll_id: int, option_index: int):
        user_id = interaction.user.id
        async with aiosqlite.connect(DB_PATH) as db:
            # 既に投票しているかチェック
            async with db.execute("SELECT 1 FROM votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id)) as cursor:
                exists = await cursor.fetchone()
                if exists:
                    await interaction.response.send_message("❌ あなたはすでに投票済みです。", ephemeral=True)
                    return
            # 投票記録追加
            await db.execute("INSERT INTO votes (poll_id, user_id, option_index) VALUES (?, ?, ?)", (poll_id, user_id, option_index))
            await db.commit()
            await interaction.response.send_message(f"✅ `{option_index + 1}`番目の選択肢に投票しました。", ephemeral=True)

    @app_commands.command(name="poll", description="投票を開始します。")
    @app_commands.describe(
        question="投票の質問",
        options="選択肢をカンマ区切りで入力（最大10個）",
        duration="投票時間（秒）"
    )
    async def poll(self, interaction: discord.Interaction, question: str, options: str, duration: int = 60):
        option_list = [opt.strip() for opt in options.split(",") if opt.strip()]
        if len(option_list) < 2 or len(option_list) > 10:
            await interaction.response.send_message("❌ 選択肢は2〜10個で入力してください。", ephemeral=True)
            return
        if duration < 10 or duration > 86400:
            await interaction.response.send_message("❌ 投票時間は10秒以上86400秒（24時間）以内にしてください。", ephemeral=True)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            # pollsテーブル作成
            await db.execute("""
                CREATE TABLE IF NOT EXISTS polls (
                    poll_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    channel_id INTEGER,
                    message_id INTEGER,
                    creator_id INTEGER,
                    question TEXT,
                    options TEXT,
                    expires_at INTEGER,
                    ended INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS votes (
                    vote_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    poll_id INTEGER,
                    user_id INTEGER,
                    option_index INTEGER
                )
            """)
            await db.commit()

            expires_at = int((datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)).timestamp())

            # 投票情報登録
            cur = await db.execute("""
                INSERT INTO polls (guild_id, channel_id, creator_id, question, options, expires_at, ended)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (interaction.guild.id, interaction.channel.id, interaction.user.id, question, json.dumps(option_list), expires_at))
            poll_id = cur.lastrowid
            await db.commit()

        embed = discord.Embed(title="📊 投票開始！", description=question, color=discord.Color.blurple())
        for i, opt in enumerate(option_list):
            embed.add_field(name=f"{i+1}. {opt}", value="\u200b", inline=False)
        embed.set_footer(text=f"投票終了まで{duration}秒")

        view = PollView(poll_id, option_list, timeout=duration)
        msg = await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ 投票を開始しました。", ephemeral=True)

        # 投票メッセージのmessage_id保存
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE polls SET message_id = ? WHERE poll_id = ?", (msg.id, poll_id))
            await db.commit()

async def setup(bot):
    await bot.add_cog(Poll(bot))