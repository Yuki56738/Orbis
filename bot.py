import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from dotenv import load_dotenv
import logging

# 環境変数読み込み（.env対応）
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is not set.")
GUILD_ID = int(os.getenv("GUILD_ID", 0))

# ログ設定
logging.basicConfig(level=logging.INFO)

# インテント設定
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# Bot本体
bot = commands.Bot(command_prefix="o/", intents=intents)
tree = bot.tree

# 起動時イベント
@bot.event
async def on_ready():
    print(f"[起動完了] Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await tree.sync(guild=discord.Object(id=GUILD_ID)) if GUILD_ID else await tree.sync()
        print(f"[Slashコマンド同期] {len(synced)} commands synced.")
    except Exception as e:
        print(f"[同期エラー] {e}")

# サーバーのカスタム設定を自動削除する

@bot.event
async def on_guild_remove(guild: discord.Guild):
    db_handler = bot.get_cog("DBHandler")
    if db_handler:
        await db_handler.drop_guild_table(guild.id)
        print(f"Guild {guild.id} の設定テーブルを削除しました。")


# エラー処理（グローバル）
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ コマンドが見つかりません。")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("🚫 権限がありません。")
    else:
        await ctx.send(f"⚠️ エラーが発生しました: {str(error)}")
        raise error

# スラッシュコマンドのエラー処理
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("🚫 必要な権限がありません。", ephemeral=True)
    elif isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message("⌛ クールダウン中です。少し待ってください。", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("⚠️ 実行できません。", ephemeral=True)
    elif isinstance(error, app_commands.CommandNotFound):
        await interaction.response.send_message("❌ コマンドが存在しません。", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ 予期しないエラー: {str(error)}", ephemeral=True)
        raise error

# Cogの自動読み込み
async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and not filename.startswith("_"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            print(f"[ロード成功] Cog: {filename}")

# メイン
async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

# 実行
if __name__ == "__main__":
    asyncio.run(main())