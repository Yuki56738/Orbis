import discord
from discord.ext import commands
from discord import app_commands
import httpx
import os

API_BASE_URL = os.getenv("ECONOMY_API_URL", "http://localhost:8000")

class LinkCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # /link-start → ユーザーが自分のshared_idを使ってコードを取得
    @app_commands.command(name="link_start", description="連携コードを取得します")
    async def link_start(self, interaction: discord.Interaction):
        shared_id = str(interaction.user.id)  # ここは共通IDに置き換えてもOK

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(f"{API_BASE_URL}/link-code", json={
                    "source": "discord",
                    "universal_id": shared_id
                })
                resp.raise_for_status()
                data = resp.json()
                code = data["code"]

                await interaction.response.send_message(
                    f"✅ あなたの連携コードは `{code}` です。\nこのコードを連携先のサービスで入力してください。",
                    ephemeral=True
                )
            except httpx.HTTPError as e:
                await interaction.response.send_message("❌ 連携コードの取得に失敗しました。", ephemeral=True)

    # /link-complete <code> → サービスで表示されたコードを入力して連携する
    @app_commands.command(name="link_complete", description="コードを使って連携を完了します")
    @app_commands.describe(code="連携用のワンタイムコード")
    async def link_complete(self, interaction: discord.Interaction, code: str):
        target_id = str(interaction.user.id)

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(f"{API_BASE_URL}/link", json={
                    "code": code,
                    "target_type": "discord",
                    "target_id": target_id
                })
                resp.raise_for_status()
                data = resp.json()

                await interaction.response.send_message(
                    f"✅ 連携が完了しました！\n共通ID: `{data['universal_id']}`",
                    ephemeral=True
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    await interaction.response.send_message("❌ 無効または期限切れのコードです。", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ 連携中にエラーが発生しました。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(LinkCog(bot))
