from utils.permission import is_event_admin
import discord
from discord import app_commands
from discord.ext import commands
import random
import string
from utils.event_db import UserDBHandler  # ← これを作成済み前提
import datetime

class EventCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = UserDBHandler()

    def generate_see_id(self):
        return "see" + ''.join(random.choices(string.ascii_letters + string.digits, k=10))

    @app_commands.command(name="event_start", description="季節イベントを開始し、全サーバーとDMに通知を送信します。")
    async def event_start(self, interaction: discord.Interaction):
        if not is_event_admin(interaction.user.id):
            await interaction.response.send_message("⚠️ このコマンドは管理者専用です。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="🌸 季節イベント開催開始！",
            description="画像とコメントで季節を感じよう！\n参加は `/event submit` を使ってね！",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="Orbis イベントシステム")

        # DM送信（ユーザー全体）
        for user in self.bot.users:
            try:
                await user.send(embed=embed)
            except Exception:
                continue

        # サーバー送信（通知チャンネル仮定）
        for guild in self.bot.guilds:
            if guild.system_channel:
                try:
                    await guild.system_channel.send(embed=embed)
                except Exception:
                    continue

        await interaction.followup.send("イベント開始通知をすべてのサーバーとユーザーに送信しました！")

    @app_commands.command(name="event_submit", description="イベントに画像とコメントで投稿します。")
    @app_commands.describe(image="投稿する画像", comment="コメントを入力してください")
    async def event_submit(self, interaction: discord.Interaction, image: discord.Attachment, comment: str):
        await interaction.response.defer()
        see_id = self.generate_see_id()
        image_url = image.url

        self.db.submit_entry(user_id=interaction.user.id, image_url=image_url, comment=comment, see_id=see_id)

        embed = discord.Embed(
            title="📷 投稿が完了しました！",
            description=f"**コメント：** {comment}\n**投稿ID：** `{see_id}`",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        embed.set_image(url=image_url)
        embed.set_footer(text="Orbis 季節イベント投稿")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="event_vote", description="投稿IDに投票します。")
    @app_commands.describe(see_id="投票する投稿のID（例：seeXXXX）")
    async def event_vote(self, interaction: discord.Interaction, see_id: str):
        success = self.db.vote(see_id)
        if success:
            embed = discord.Embed(
                title="🗳️ 投票完了！",
                description=f"投稿 `{see_id}` に投票しました！",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="⚠️ 投票失敗",
                description=f"投稿ID `{see_id}` が見つかりませんでした。",
                color=discord.Color.red()
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="event_ranking", description="現在のランキングを表示します。")
    async def event_ranking(self, interaction: discord.Interaction):
        top_entries = self.db.get_top_entries(limit=5)
        if not top_entries:
            await interaction.response.send_message(embed=discord.Embed(
                title="📉 ランキングなし",
                description="まだ投稿がありません。",
                color=discord.Color.dark_gray()
            ))
            return

        embed = discord.Embed(
            title="🏆 イベント ランキングTOP5",
            color=discord.Color.gold()
        )
        for i, entry in enumerate(top_entries, 1):
            embed.add_field(
                name=f"{i}位：投稿ID `{entry['see_id']}`",
                value=f"票数：{entry['votes']}票\nコメント：{entry['comment']}",
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="event_end", description="イベントを終了し、すべてを初期化します（管理者限定）")
    async def event_end(self, interaction: discord.Interaction):
        if not is_event_admin(interaction.user.id):
            await interaction.response.send_message("⚠️ このコマンドは管理者専用です。", ephemeral=True)
            return
            
        self.db.reset_event_votes()
        self.db.export_and_reset_events()

        embed = discord.Embed(
            title="📛 イベント終了",
            description="イベントデータをエクスポートし、すべて初期化しました。",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(EventCog(bot))