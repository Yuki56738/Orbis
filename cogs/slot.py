import discord
from discord.ext import commands
from discord import app_commands
from ..utils import economy_api, item as item_utils
import random
import asyncio

REELS = {
    1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣"
}

class Slot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="slot", description="スロットを回してコインを増やそう！")
    @app_commands.describe(bet="賭けるコインの枚数", use_bonus="ハイリスク・ハイリターンのお守りを使いますか？")
    @economy_api.has_permission(3)
    async def slot(self, ctx: commands.Context, bet: int, use_bonus: bool = False):
        shared_id = f"{ctx.guild.id}-{ctx.author.id}"

        if bet <= 0:
            await ctx.send(embed=discord.Embed(title="エラー", description="掛け金は1以上の整数で指定してください。", color=discord.Color.red()), ephemeral=True)
            return

        user = await economy_api.get_user(shared_id)
        if not user:
            await ctx.send("ユーザー情報を取得できませんでした。", ephemeral=True)
            return

        coins = user.get("coins", 0)
        if coins < bet:
            await ctx.send(embed=discord.Embed(title="エラー", description="コインが足りません。", color=discord.Color.red()), ephemeral=True)
            return

        item_used = False
        charm_name = "risk_charm"
        if use_bonus:
            item_used = await item_utils.use_item(shared_id, charm_name)
            if not item_used:
                await ctx.send(embed=discord.Embed(title="エラー", description="ハイリスク・ハイリターンのお守りを所持していません。", color=discord.Color.red()), ephemeral=True)
                return

        await economy_api.update_user(shared_id, {"coins": coins - bet})

        if item_used and random.random() < 0.20:
            result_numbers = [1, 2, 3, 4, 5]
            random.shuffle(result_numbers)
        else:
            result_numbers = [random.randint(1, 5) for _ in range(5)]

        result_reels = [REELS[n] for n in result_numbers]

        payout_multiplier = 0.0
        payout_reason = "ハズレ..."

        counts = {i: result_numbers.count(i) for i in set(result_numbers)}

        if 5 in counts.values():
            num = result_numbers[0]
            payout_multiplier = 100.0 if num == 1 else 10.0
            payout_reason = f"{REELS[num]} が5つ揃い！"
        elif 4 in counts.values():
            num = [k for k, v in counts.items() if v == 4][0]
            is_straight = any(result_numbers[i:i+4] == [num]*4 for i in range(2))
            payout_multiplier = 5.0 if is_straight else 2.0
            payout_reason = f"{REELS[num]} が4つ揃い！" + (" (並び)" if is_straight else "")
        elif 3 in counts.values():
            num = [k for k, v in counts.items() if v == 3][0]
            is_straight = any(result_numbers[i:i+3] == [num]*3 for i in range(3))
            payout_multiplier = 1.5 if is_straight else 1.25
            payout_reason = f"{REELS[num]} が3つ揃い！" + (" (並び)" if is_straight else "")

        if payout_multiplier > 0 and item_used:
            payout_multiplier *= 1.5
            payout_reason += " (お守りボーナス x1.5)"

        payout = int(bet * payout_multiplier)
        updated_coins = coins - bet + payout
        await economy_api.update_user(shared_id, {"coins": updated_coins})

        initial_embed = discord.Embed(title="スロット", description="**回っています...**", color=discord.Color.light_grey())
        initial_embed.add_field(name="結果", value="❓ ❓ ❓ ❓ ❓")
        msg = await ctx.send(embed=initial_embed)

        await asyncio.sleep(1.5)

        final_embed = discord.Embed(
            title="スロット結果",
            description=f"**{payout_reason}**",
            color=discord.Color.green() if payout > 0 else discord.Color.red()
        )
        final_embed.add_field(name="出目", value=" ".join(result_reels), inline=False)
        final_embed.add_field(name="掛け金", value=f"{bet:,}コイン")
        final_embed.add_field(name="払い戻し", value=f"{payout:,}コイン")
        final_embed.add_field(name="所持コイン", value=f"{updated_coins:,}コイン", inline=False)

        if item_used:
            final_embed.set_footer(text="ハイリスク・ハイリターンのお守りを1個消費しました。")

        await msg.edit(embed=final_embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Slot(bot))
