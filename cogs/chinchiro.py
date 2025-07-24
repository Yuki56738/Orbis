import discord
from discord.ext import commands
from discord import app_commands, ui
from ..utils import economy_api, item as item_utils
import random
from collections import Counter
import aiohttp

DICE_EMOJIS = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣"}
PAYOUTS = {
    "ピンゾロ": 5.0,
    "ゾロ目": 3.0,
    "通常の目": 1.0,
    "ヒフミ": -2.0,
    "目なし": 0.0,
}

def evaluate_dice(dice: list[int]):
    dice.sort()
    if len(set(dice)) == 1:
        return ("ピンゾロ", PAYOUTS["ピンゾロ"]) if dice[0] == 1 else (f"{dice[0]}のゾロ目", PAYOUTS["ゾロ目"])
    if dice == [1, 2, 3]:
        return "ヒフミ", PAYOUTS["ヒフミ"]
    counts = Counter(dice)
    if 2 in counts.values():
        for num, count in counts.items():
            if count == 1:
                return f"{num}の目", PAYOUTS["通常の目"]
    return "目なし", PAYOUTS["目なし"]

def format_dice_str(dice: list[int]):
    return " ".join(DICE_EMOJIS[d] for d in dice)

class ChinchiroView(ui.View):
    def __init__(self, game_cog):
        super().__init__(timeout=180)
        self.game_cog = game_cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        game_state = self.game_cog.active_games.get(interaction.user.id)
        if not game_state or interaction.user.id != game_state["author_id"]:
            await interaction.response.send_message("ゲームの参加者のみ操作できます。", ephemeral=True)
            return False
        return True

    @ui.button(label="振り直す", style=discord.ButtonStyle.primary, row=1, custom_id="chinchiro_reroll")
    async def reroll_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.game_cog.on_reroll(interaction, self)

    @ui.button(label="勝負する", style=discord.ButtonStyle.green, row=1, custom_id="chinchiro_stand")
    async def stand_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.game_cog.on_stand(interaction)

class Chinchiro(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_games = {}

    def create_game_embed(self, game_state, final=False, result_text=None):
        dice_str = format_dice_str(game_state["dice"])
        embed = discord.Embed(title="チンチロリン", color=discord.Color.purple())
        embed.description = f"**結果: {result_text}**" if final else "「振り直す」か「勝負する」を押してください。"
        embed.add_field(name="あなたのサイコロ", value=dice_str, inline=False)
        return embed

    async def end_game(self, interaction: discord.Interaction, game_state):
        session = self.bot.http_session
        user_id = interaction.user.id
        shared_id = str(interaction.guild.id) + "_" + str(user_id)
        self.active_games.pop(user_id, None)

        dice = game_state["dice"]
        bet = game_state["bet"]
        item_used = game_state["item_used"]

        user = await economy_api.EconomyAPI(session).get_user(shared_id)
        if not user:
            return await interaction.followup.send("ユーザーデータの取得に失敗しました。", ephemeral=True)

        hand_name, payout_multiplier = evaluate_dice(dice)
        if item_used and payout_multiplier > 0:
            payout_multiplier *= 1.5

        payout = int(bet * payout_multiplier)
        new_balance = user["balance"] + payout

        await economy_api.EconomyAPI(session).update_user(shared_id, {"balance": new_balance})

        embed = self.create_game_embed(game_state, final=True, result_text=hand_name)
        embed.add_field(name="掛け金", value=f"{bet:,}コイン", inline=True)
        result_str = f"{payout:,}コインの払い戻し" if payout >= 0 else f"{abs(payout):,}コインの支払い"
        embed.add_field(name="結果", value=result_str + (" (イカサマボーナス x1.5)" if item_used and payout > 0 else ""), inline=True)
        embed.add_field(name="所持コイン", value=f"{new_balance:,}コイン", inline=False)

        if item_used:
            embed.set_footer(text=f"イカサマの壺を1個消費しました。")

        await interaction.message.edit(embed=embed, view=None)

    async def on_reroll(self, interaction: discord.Interaction, view: ChinchiroView):
        user_id = interaction.user.id
        game_state = self.active_games.get(user_id)
        if not game_state:
            return

        if game_state["roll_count"] >= 3:
            await interaction.response.send_message("これ以上振り直せません。「勝負する」を押してください。", ephemeral=True)
            return

        game_state["roll_count"] += 1
        game_state["dice"] = [random.randint(1, 6) for _ in range(3)]

        embed = self.create_game_embed(game_state)
        embed.set_footer(text=f"振り直し回数: {game_state['roll_count']} / 3")

        if game_state["roll_count"] >= 3:
            reroll_button = discord.utils.get(view.children, custom_id="chinchiro_reroll")
            if reroll_button:
                reroll_button.disabled = True
            embed.description = "最後の振り直しです。「勝負する」を押してください。"

        await interaction.response.edit_message(embed=embed, view=view)

    async def on_stand(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id not in self.active_games:
            return
        await interaction.response.defer()
        await self.end_game(interaction, self.active_games[user_id])

    @commands.hybrid_command(name="chinchiro", aliases=["cc"], description="サイコロを振って役を揃えよう！")
    @app_commands.describe(bet="賭けるコインの枚数", use_bonus="イカサマの壺を使いますか？")
    async def chinchiro(self, ctx: commands.Context, bet: int, use_bonus: bool = False):
        session = self.bot.http_session
        user_id = ctx.author.id
        shared_id = f"{ctx.guild.id}_{user_id}"

        if user_id in self.active_games:
            return await ctx.send("既に進行中のゲームがあります。", ephemeral=True)
        if bet <= 0:
            return await ctx.send("掛け金は1以上の整数で指定してください。", ephemeral=True)

        user = await economy_api.EconomyAPI(session).get_user(shared_id)
        if not user:
            return await ctx.send("ユーザー情報が取得できませんでした。", ephemeral=True)
        if user["balance"] < bet * 2:
            return await ctx.send("コインが足りません（ヒフミ負けの保険も必要）。", ephemeral=True)

        item_used = False
        if use_bonus:
            item_used = await item_utils.use_item(shared_id, "chinchiro_cup")
            if not item_used:
                return await ctx.send("イカサマの壺を所持していません。", ephemeral=True)

        # 先にコイン減算
        await economy_api.EconomyAPI(session).update_user(shared_id, {"balance": user["balance"] - bet})

        if item_used and random.random() < 0.2:
            dice = [1, 2, 4]
        else:
            dice = [random.randint(1, 6) for _ in range(3)]

        game_state = {
            "dice": dice,
            "bet": bet,
            "item_used": item_used,
            "roll_count": 0,
            "author_id": user_id
        }

        hand_name, _ = evaluate_dice(dice)
        if hand_name != "目なし":
            await self.end_game(ctx, game_state)
            return

        view = ChinchiroView(self)
        self.active_games[user_id] = game_state
        embed = self.create_game_embed(game_state)
        embed.set_footer(text="振り直し回数: 0 / 3")
        await ctx.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Chinchiro(bot))
