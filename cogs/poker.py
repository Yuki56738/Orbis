import discord
from discord.ext import commands
from discord import app_commands, ui
import random
from collections import Counter
from utils.economy_api import EconomyAPI
from utils.item_utils import get_inventory, use_item

SUITS = ["♠️", "♥️", "♣️", "♦️"]
RANKS_ORDER = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
RANK_VALUES = {rank: i for i, rank in enumerate(RANKS_ORDER)}

PAYOUTS = {
    "ロイヤルストレートフラッシュ": 200,
    "ストレートフラッシュ": 50,
    "フォーカード": 25,
    "フルハウス": 12,
    "フラッシュ": 8,
    "ストレート": 5,
    "スリーカード": 3,
    "ツーペア": 2,
    "ワンペア": 1.2,
    "ハイカード": 0,
}

class Deck:
    def __init__(self):
        self.cards = [(suit, rank) for suit in SUITS for rank in RANKS_ORDER]
        random.shuffle(self.cards)

    def draw(self, count=1):
        drawn = []
        for _ in range(count):
            if not self.cards:
                self.__init__()
            drawn.append(self.cards.pop())
        return drawn

def evaluate_hand(hand):
    ranks = sorted([RANK_VALUES[r] for s, r in hand])
    suits = [s for s, r in hand]
    is_flush = len(set(suits)) == 1
    is_straight = (ranks == list(range(ranks[0], ranks[0] + 5))) or (ranks == [0, 1, 2, 3, 12])
    if is_straight and is_flush:
        return ("ロイヤルストレートフラッシュ" if ranks == [8, 9, 10, 11, 12] else "ストレートフラッシュ",
                PAYOUTS["ロイヤルストレートフラッシュ" if ranks == [8, 9, 10, 11, 12] else "ストレートフラッシュ"])
    count = Counter([r for s, r in hand])
    freq = sorted(count.values(), reverse=True)
    if freq[0] == 4: return "フォーカード", PAYOUTS["フォーカード"]
    if freq == [3, 2]: return "フルハウス", PAYOUTS["フルハウス"]
    if is_flush: return "フラッシュ", PAYOUTS["フラッシュ"]
    if is_straight: return "ストレート", PAYOUTS["ストレート"]
    if freq[0] == 3: return "スリーカード", PAYOUTS["スリーカード"]
    if freq == [2, 2, 1]: return "ツーペア", PAYOUTS["ツーペア"]
    if freq[0] == 2: return "ワンペア", PAYOUTS["ワンペア"]
    return "ハイカード", PAYOUTS["ハイカード"]

def format_hand_str(hand):
    return " ".join([f"`{suit}{rank}`" for suit, rank in hand])

class CardSelect(ui.Select):
    def __init__(self, hand):
        options = [discord.SelectOption(label=f"{suit}{rank}", value=str(i)) for i, (suit, rank) in enumerate(hand)]
        super().__init__(placeholder="交換するカードを選択...", min_values=0, max_values=len(hand), options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

class PokerView(ui.View):
    def __init__(self, cog, user_id, hand):
        super().__init__(timeout=180)
        self.add_item(CardSelect(hand))
        self.cog = cog
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("操作できるのはゲーム参加者のみです。", ephemeral=True)
            return False
        return True

    @ui.button(label="ドロー (交換)", style=discord.ButtonStyle.primary, row=1)
    async def draw_btn(self, interaction: discord.Interaction, button: ui.Button):
        select: CardSelect = next(i for i in self.children if isinstance(i, CardSelect))
        indices = [int(i) for i in select.values]
        await self.cog.on_draw(interaction, indices)

    @ui.button(label="スタンド (勝負)", style=discord.ButtonStyle.green, row=1)
    async def stand_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self.cog.on_stand(interaction)

class Poker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}  # user_id: game_state

    def create_embed(self, state, final=False):
        hand = state["hand"]
        hand_str = format_hand_str(hand)
        if final:
            hand_name, multi = evaluate_hand(hand)
            color = discord.Color.green() if multi > 0 else discord.Color.red()
            embed = discord.Embed(title=f"ポーカー結果: {hand_name}", color=color)
        else:
            embed = discord.Embed(title="ポーカー", description="交換するカードを選択して「ドロー」", color=discord.Color.blue())
        embed.add_field(name="手札", value=hand_str, inline=False)
        return embed

    async def end_game(self, interaction, final_hand, state):
        hand_name, multi = evaluate_hand(final_hand)
        bet = state["bet"]
        used = state["item_used"]
        if used and multi > 0:
            multi *= 1.5
        payout = int(bet * multi)

        # 経済API反映
        api: EconomyAPI = state["api"]
        shared_id = str(interaction.user.id)
        user = await api.get_user(shared_id)
        new_balance = user["balance"] + payout
        await api.update_user(shared_id, {"balance": new_balance})

        embed = self.create_embed({"hand": final_hand}, final=True)
        embed.add_field(name="掛け金", value=f"{bet:,}コイン", inline=True)
        embed.add_field(name="払い戻し", value=f"{payout:,}コイン", inline=True)
        embed.add_field(name="残高", value=f"{new_balance:,}コイン", inline=False)
        if used:
            inv = await get_inventory(shared_id)
            count = inv.get("poker_chip", {}).get("count", 0)
            embed.set_footer(text=f"幸運のポーカーチップを1枚使用（残り {count}個）")

        await interaction.message.edit(embed=embed, view=None)
        self.games.pop(interaction.user.id, None)

    async def on_draw(self, interaction, indices):
        uid = interaction.user.id
        if uid not in self.games:
            return
        state = self.games[uid]
        if state["draws"] >= 1:
            await interaction.response.send_message("これ以上交換できません。", ephemeral=True)
            return
        if not indices:
            await interaction.response.send_message("交換カードを選択してください。", ephemeral=True)
            return
        state["draws"] += 1
        new_hand = [card for i, card in enumerate(state["hand"]) if i not in indices]
        new_hand += state["deck"].draw(len(indices))
        state["hand"] = new_hand
        embed = self.create_embed(state)
        embed.set_footer(text=f"ドロー回数: {state['draws']} / 1")
        view = PokerView(self, uid, new_hand)
        await interaction.response.edit_message(embed=embed, view=view)

    async def on_stand(self, interaction):
        uid = interaction.user.id
        if uid in self.games:
            await interaction.response.defer()
            await self.end_game(interaction, self.games[uid]["hand"], self.games[uid])

    @commands.hybrid_command(name="poker", description="ファイブカードポーカーで勝負！")
    @app_commands.describe(bet="賭ける金額", use_bonus="チップ使用")
    async def poker(self, ctx, bet: int, use_bonus: bool = False):
        uid = ctx.author.id
        if uid in self.games:
            return await ctx.send("既にゲーム中です。", ephemeral=True)
        if bet <= 0:
            return await ctx.send("掛け金は1以上で指定してください。", ephemeral=True)

        session = self.bot.aiohttp_session
        api = EconomyAPI(session)
        shared_id = str(ctx.author.id)
        user = await api.get_user(shared_id)
        if not user or user["balance"] < bet:
            return await ctx.send("コインが足りません。", ephemeral=True)

        item_used = False
        if use_bonus:
            if await use_item(shared_id, "poker_chip"):
                item_used = True
            else:
                return await ctx.send("ポーカーチップがありません。", ephemeral=True)

        await api.update_user(shared_id, {"balance": user["balance"] - bet})

        deck = Deck()
        if item_used and random.random() < 0.2:
            # 高ランクが揃いやすい初期手札
            hand, seen = [], set()
            while len(hand) < 5:
                c = deck.draw(1)[0]
                if c[1] not in seen:
                    hand.append(c)
                    seen.add(c[1])
        else:
            hand = deck.draw(5)

        view = PokerView(self, uid, hand)
        state = {
            "deck": deck,
            "hand": hand,
            "bet": bet,
            "draws": 0,
            "item_used": item_used,
            "api": api
        }
        self.games[uid] = state
        embed = self.create_embed(state)
        embed.set_footer(text="ドロー回数: 0 / 1")
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Poker(bot))
