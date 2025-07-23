import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import random
import datetime

class Useful(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminders = []  # 簡易的にメモリ保持。再起動すると消えます

    # 埋め込み投稿コマンド    
    @app_commands.command(name="embed", description="シンプルな埋め込みメッセージを送信します。")
    @app_commands.describe(title="タイトル", description="説明文", color="色コード（例: #FF0000）")
    async def embed(self, interaction: discord.Interaction, title: str, description: str, color: str = "#3498db"):
        try:
            color_int = int(color.lstrip('#'), 16)
        except:
            color_int = 0x3498db
        embed = discord.Embed(title=title, description=description, color=color_int)
        await interaction.response.send_message(embed=embed)

    # リマインダー設定コマンド
    @app_commands.command(name="remind", description="指定時間後にリマインダーを送信します。（例: 10m, 1h, 30s）")
    @app_commands.describe(time="時間（例：10m、1h、30s）", message="リマインダー内容")
    async def remind(self, interaction: discord.Interaction, time: str, message: str):
        seconds = self.parse_time(time)
        if seconds is None or seconds <= 0:
            await interaction.response.send_message("❌ 時間の指定が不正です。例：10m、1h、30s", ephemeral=True)
            return

        await interaction.response.send_message(f"⏰ {time}後にリマインダーをセットしました。", ephemeral=True)

        async def reminder_task():
            await asyncio.sleep(seconds)
            try:
                await interaction.user.send(f"⏰ リマインダー：{message}")
            except:
                # DM拒否の場合はチャンネルで通知
                await interaction.channel.send(f"{interaction.user.mention} ⏰ リマインダー：{message}")

        self.bot.loop.create_task(reminder_task())

    def parse_time(self, time_str: str) -> int | None:
        try:
            unit = time_str[-1]
            num = int(time_str[:-1])
            if unit == 's':
                return num
            elif unit == 'm':
                return num * 60
            elif unit == 'h':
                return num * 3600
            else:
                return None
        except:
            return None

    # ランダム選択コマンド
    @app_commands.command(name="choose", description="複数の選択肢からランダムに1つ選びます。")
    @app_commands.describe(options="カンマ区切りで選択肢を入力してください")
    async def choose(self, interaction: discord.Interaction, options: str):
        choices = [opt.strip() for opt in options.split(",") if opt.strip()]
        if len(choices) < 2:
            await interaction.response.send_message("❌ 選択肢は2つ以上必要です。", ephemeral=True)
            return
        selected = random.choice(choices)
        await interaction.response.send_message(f"🎲 選ばれた選択肢は: **{selected}** です。")

    # カレンダー表示コマンド
    @app_commands.command(name="calendar", description="指定した年月のカレンダーを表示します。")
    @app_commands.describe(year="西暦の年（省略時は今年）", month="月（1〜12、省略時は今月）")
    async def calendar(self, interaction: discord.Interaction, year: int = None, month: int = None):
        today = datetime.date.today()
        year = year or today.year
        month = month or today.month

        try:
            import calendar
            cal_text = calendar.month(year, month)
            await interaction.response.send_message(f"```\n{cal_text}\n```")
        except Exception as e:
            await interaction.response.send_message(f"❌ エラーが発生しました: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Useful(bot))
