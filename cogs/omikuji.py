import discord
from discord.ext import commands
from discord import app_commands
import random
import json
import datetime

from utils import fortune

class Omikuji(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_last_draw = {}  # user_id: date の辞書
    
    def has_drawn_today(self, user_id: int) -> bool:
        today = datetime.date.today()
        last_draw = self.user_last_draw.get(user_id)
        return last_draw == today

    def set_last_draw_date(self, user_id: int):
        self.user_last_draw[user_id] = datetime.date.today()

    @app_commands.command(name="omikuji", description="今日の運勢を占おう！")
    async def omikuji(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        if self.has_drawn_today(user_id):
            await interaction.response.send_message("今日はもうおみくじを引いたよ！また明日ね🌅", ephemeral=True)
            return

        result = fortune.draw_fortune()  # ランダムにおみくじを引く
        self.set_last_draw_date(user_id)

        embed = discord.Embed(
            title=f"🎴 {result['fortune']}の運勢 🎴",
            description=result['message'],
            color=discord.Color.gold()
        )
        embed.set_footer(text="効果は冒険や経済活動にも反映されます✨")

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # 将来的に：運勢の効果をプレイヤー情報に保存したり、適用する処理
        # 例: apply_fortune_effects(user_id, result["effects"])

async def setup(bot: commands.Bot):
    await bot.add_cog(Omikuji(bot))
