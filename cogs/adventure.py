import discord
from discord.ext import commands
from discord import app_commands
import random
import json
import aiohttp

from utils import adventure as adventure_utils
from utils import item as item_utils
from utils import economy_api as economy_utils
from utils import fortune

class Adventure(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        await self.session.close()

    @app_commands.command(name="adventure_start", description="冒険を開始します（ステージと難易度を選択）")
    async def start(self, interaction: discord.Interaction):
        stages = await adventure_utils.load_stages()
        options = [discord.SelectOption(label=s["name"], value=s["id"], description=s["description"]) for s in stages]

        select = discord.ui.Select(placeholder="ステージを選んでください", options=options)

        async def select_callback(interact: discord.Interaction):
            selected_stage = next((s for s in stages if s["id"] == select.values[0]), None)
            await adventure_utils.start_adventure(interaction.user.id, selected_stage["id"])
            await interact.response.send_message(f"🌄 {selected_stage['name']} で冒険を開始しました！ `/adventure_explore` で探索を続けてください。", ephemeral=True)

        view = discord.ui.View()
        select.callback = select_callback
        view.add_item(select)
        await interaction.response.send_message("🌍 冒険ステージを選択してください：", view=view, ephemeral=True)

    @app_commands.command(name="adventure_explore", description="冒険を探索してイベントを進行させます")
    async def explore(self, interaction: discord.Interaction):
        fortune_effects = await fortune.get_today_fotune_effects(interaction.user.id)
        bonus = fortune_effects.get("event_success_rate_bonus",0)
        event = await adventure_utils.get_random_event()
        roll_result, passed, message = await adventure_utils.resolve_event(interaction.user.id, event,bonus_modifier=bonus)

        embed = discord.Embed(title=f"📜 イベント: {event['name']}", description=event["description"], color=0x66ccff)
        embed.add_field(name="🎲 判定", value=message, inline=False)
        embed.set_footer(text="/adventure_explore で続けて探索、 /adventure_end で冒険終了")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="adventure_status", description="現在の冒険の状態を確認します")
    async def status(self, interaction: discord.Interaction):
        status = await adventure_utils.get_adventure_status(interaction.user.id)
        if not status:
            await interaction.response.send_message("❌ 現在冒険中ではありません。`/adventure_start` で冒険を開始してください。", ephemeral=True)
            return

        embed = discord.Embed(title="📊 冒険ステータス", color=0x44cc88)
        embed.add_field(name="🗺️ ステージ", value=status["stage"], inline=True)
        embed.add_field(name="🔁 探索回数", value=status["turns"], inline=True)
        embed.add_field(name="💥 成功イベント数", value=status["success"], inline=True)
        embed.add_field(name="☠️ 失敗イベント数", value=status["fail"], inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="adventure_end", description="冒険を終了して報酬を獲得します")
    async def end(self, interaction: discord.Interaction):
        result = await adventure_utils.end_adventure(interaction.user.id, self.session)
        if not result:
            await interaction.response.send_message("❌ 冒険していません。`/adventure_start` で始めましょう。", ephemeral=True)
            return

        embed = discord.Embed(title="🎉 冒険終了！", color=0xffcc00)
        embed.add_field(name="🏅 獲得経験値", value=str(result["exp"]))
        embed.add_field(name="💰 獲得ゴールド", value=str(result["gold"]))
        embed.add_field(name="🎁 アイテム", value=", ".join(result["items"]) if result["items"] else "なし")
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Adventure(bot))
