from utils.permission import is_event_admin
import discord
from discord import app_commands, Interaction, Embed, ui
from discord.ext import commands
import random
import string
from utils.event_db import UserDBHandler  # ← これを作成済み前提
import datetime
import asyncpg

class EventCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.userdb

    async def generate_see_id(self):
        while True:
            see_id = "see" + ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            if not await self.db.get_event_submission_by_see_id(see_id):
                return see_id

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

        await self.db.add_event_submission(user_id=interaction.user.id, image_url=image_url, comment=comment, see_id=see_id)

        embed = discord.Embed(
            title="📷 投稿が完了しました！",
            description=f"**コメント：** {comment}\n**投稿ID：** `{see_id}`",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        embed.set_image(url=image_url)
        embed.set_footer(text="Orbis 季節イベント投稿")

        await interaction.followup.send(embed=embed)


    # ------------------------------
    # 投稿削除コマンド
    # ------------------------------
    @app_commands.command(name="event_delete", description="自分の投稿を削除します")
    async def event_delete(self, interaction: Interaction):
        submissions = await self.db.get_user_event_submissions(interaction.user.id)

        if not submissions:
            return await interaction.response.send_message("あなたの投稿は見つかりませんでした。", ephemeral=True)

        options = [
            ui.SelectOption(
                label=sub["title"][:100] if sub["title"] else "(No Title)",
                description=sub["comment"][:100] if sub["comment"] else "(No Comment)",
                value=sub["see_id"]
            )
            for sub in submissions
        ]

        class DeleteSelect(ui.View):
            def __init__(self):
                super().__init__(timeout=60)

                self.select = ui.Select(placeholder="削除する投稿を選んでください", options=options)
                self.select.callback = self.select_callback
                self.add_item(self.select)

            async def select_callback(self, interaction2: Interaction):
                see_id = self.select.values[0]

                confirm_view = ConfirmDeleteView(see_id)
                await interaction2.response.send_message(
                    f"以下の投稿を削除しますか？\n`{see_id}`",
                    view=confirm_view,
                    ephemeral=True
                )

        await interaction.response.send_message("削除する投稿を選んでください：", view=DeleteSelect(), ephemeral=True)

        # --- 削除確認用ビュー ---
        class ConfirmDeleteView(ui.View):
            def __init__(self, see_id):
                super().__init__(timeout=30)
                self.see_id = see_id

            @ui.button(label="✅ 削除", style=discord.ButtonStyle.danger)
            async def delete_button(self, interaction2: Interaction, button: ui.Button):
                await self.db.delete_event_submission(self.see_id)
                await interaction2.response.edit_message(content="削除しました。", view=None)

            @ui.button(label="❌ キャンセル", style=discord.ButtonStyle.secondary)
            async def cancel_button(self, interaction2: Interaction, button: ui.Button):
                await interaction2.response.edit_message(content="キャンセルしました。", view=None)

    # ------------------------------
    # 投稿編集コマンド
    # ------------------------------
    @app_commands.command(name="event_edit", description="自分の投稿を編集します")
    async def event_edit(self, interaction: Interaction):
        submissions = await self.db.get_user_event_submissions(interaction.user.id)

        if not submissions:
            return await interaction.response.send_message("あなたの投稿は見つかりませんでした。", ephemeral=True)

        options = [
            ui.SelectOption(
                label=sub["title"][:100] if sub["title"] else "(No Title)",
                description=sub["comment"][:100] if sub["comment"] else "(No Comment)",
                value=sub["see_id"]
            )
            for sub in submissions
        ]

        class EditSelect(ui.View):
            def __init__(self):
                super().__init__(timeout=60)

                self.select = ui.Select(placeholder="編集する投稿を選んでください", options=options)
                self.select.callback = self.select_callback
                self.add_item(self.select)

            async def select_callback(self, interaction2: Interaction):
                see_id = self.select.values[0]
                # モーダルで編集画面
                await interaction2.response.send_modal(EditModal(see_id))

        await interaction.response.send_message("編集する投稿を選んでください：", view=EditSelect(), ephemeral=True)

        # --- 編集用モーダル ---
        class EditModal(ui.Modal, title="投稿を編集"):
            def __init__(self, see_id):
                super().__init__()
                self.see_id = see_id

                self.title_input = ui.TextInput(label="タイトル", required=True, max_length=100)
                self.comment_input = ui.TextInput(label="コメント", required=True, style=discord.TextStyle.paragraph, max_length=500)

                self.add_item(self.title_input)
                self.add_item(self.comment_input)

            async def on_submit(self, interaction2: Interaction):
                await self.db.edit_event_submission(self.see_id, self.title_input.value, self.comment_input.value)

                embed = Embed(
                    title="✅ 投稿を更新しました",
                    description=f"**see_id:** `{self.see_id}`\n**タイトル:** {self.title_input.value}\n**コメント:** {self.comment_input.value}",
                    color=discord.Color.green()
                )
                await interaction2.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="event_vote", description="投稿IDに投票します。")
    @app_commands.describe(see_id="投票する投稿のID（例：seeXXXX）")
    async def event_vote(self, interaction: discord.Interaction, see_id: str):
        success = await self.db.vote_event_submission(see_id)
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