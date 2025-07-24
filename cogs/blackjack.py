import discord
from discord.ext import commands
from discord import app_commands, ui
from utils.economy_api import EconomyAPI
from utils import item_utils  # インベントリ関連ユーティリティ（後述）
import random
import asyncio
import aiohttp

SUITS = ["♠️", "♥️", "♣️", "♦️"]
RANKS = {
    "A": 11, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "8": 8, "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10
}

class Deck:
    def __init__(self):
        self.cards = []
        self.reset()

    def reset(self):
        self.cards = [(suit, rank) for suit in SUITS for rank in RANKS.keys()]
        random.shuffle(self.cards)

    def draw(self):
        if not self.cards:
            self.reset()
        return self.cards.pop()

def calculate_hand_value(hand):
    value = 0
    num_aces = 0
    for _, rank in hand:
        value += RANKS[rank]
        if rank == "A":
            num_aces += 1
    while value > 21 and num_aces > 0:
        value -= 10
        num_aces -= 1
    return value

def format_hand(hand, is_dealer_hidden=False):
    if is_dealer_hidden:
        return f"`{hand[0][0]}{hand[0][1]}` `[ ? ]`"
    return " ".join([f"`{suit}{rank}`" for suit, rank in hand])

class BlackJackView(ui.View):
    def __init__(self, cog, author_id):
        super().__init__(timeout=180)
        self.cog = cog
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("これはあなたのゲームです。", ephemeral=True)
            return False
        return True

    @ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, _):
        await self.cog.on_hit(interaction)

    @ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, interaction: discord.Interaction, _):
        await self.cog.on_stand(interaction)

    def disable_all_buttons(self):
        for child in self.children:
            if isinstance(child, ui.Button):
                child.disabled = True

class BlackJack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}

    async def fetch_economy(self, session, discord_id):
        async with session.get(f"https://localhost:8000/link?discord_id={discord_id}") as resp:
            link_data = await resp.json()
            shared_id = link_data["universal_id"]
        api = EconomyAPI(session)
        user_data = await api.get_user(shared_id)
        return shared_id, user_data

    async def update_balance(self, session, shared_id, new_balance):
        api = EconomyAPI(session)
        await api.update_user(shared_id, {"balance": new_balance})

    async def on_hit(self, interaction: discord.Interaction):
        game = self.active_games.get(interaction.message.id)
        if not game: return

        game["player_hand"].append(game["deck"].draw())
        game["player_value"] = calculate_hand_value(game["player_hand"])
        embed = self.create_game_embed(game)

        if game["player_value"] > 21:
            embed.color = discord.Color.red()
            embed.set_field_at(0, name="結果: バースト！", value=embed.fields[0].value, inline=False)
            game["view"].disable_all_buttons()
            await self.end_game(interaction, game, "lose", "あなたはバーストしました")

        await interaction.response.edit_message(embed=embed, view=game["view"])

    async def on_stand(self, interaction: discord.Interaction):
        game = self.active_games.get(interaction.message.id)
        if not game: return

        game["view"].disable_all_buttons()
        await interaction.response.edit_message(view=game["view"])

        while game["dealer_value"] < 17:
            game["dealer_hand"].append(game["deck"].draw())
            game["dealer_value"] = calculate_hand_value(game["dealer_hand"])
            embed = self.create_game_embed(game, reveal_dealer=True)
            embed.description = "ディーラーがカードを引いています..."
            await interaction.message.edit(embed=embed)
            await asyncio.sleep(1.5)

        player = game["player_value"]
        dealer = game["dealer_value"]

        if dealer > 21:
            await self.end_game(interaction, game, "win", "ディーラーがバースト！")
        elif player > dealer:
            await self.end_game(interaction, game, "win", "あなたのスコアが高い！")
        elif dealer > player:
            await self.end_game(interaction, game, "lose", "ディーラーの勝ち")
        else:
            await self.end_game(interaction, game, "push", "引き分けです")

    def create_game_embed(self, game, reveal_dealer=False):
        embed = discord.Embed(title="ブラックジャック", color=discord.Color.dark_green())
        embed.add_field(name=f"あなたの手札 ({game['player_value']})", value=format_hand(game["player_hand"]), inline=False)
        dealer_hand = format_hand(game["dealer_hand"], is_dealer_hidden=not reveal_dealer)
        dealer_val = game["dealer_value"] if reveal_dealer else "?"
        embed.add_field(name=f"ディーラーの手札 ({dealer_val})", value=dealer_hand, inline=False)
        return embed

    async def end_game(self, interaction, game, result: str, reason: str):
        payout_multiplier = {"win": 2.0, "lose": 0.0, "push": 1.0}[result]
        color = {"win": discord.Color.green(), "lose": discord.Color.red(), "push": discord.Color.light_grey()}[result]
        title = {"win": "あなたの勝ち！", "lose": "あなたの負け", "push": "引き分け"}[result]

        if game["item_used"] and result == "win":
            payout_multiplier *= 1.5

        payout = int(game["bet"] * payout_multiplier)

        async with aiohttp.ClientSession() as session:
            new_balance = game["economy"]["balance"] + payout
            await self.update_balance(session, game["shared_id"], new_balance)

        embed = self.create_game_embed(game, reveal_dealer=True)
        embed.title = f"決着: {title}"
        embed.description = f"理由: {reason}"
        embed.color = color
        embed.add_field(name="掛け金", value=f"{game['bet']:,}コイン")
        embed.add_field(name="払い戻し", value=f"{payout:,}コイン")
        embed.add_field(name="所持コイン", value=f"{game['economy']['balance'] + payout:,}コイン", inline=False)

        if game["item_used"]:
            embed.set_footer(text="インシュランスカードを1枚消費しました。")

        await interaction.message.edit(embed=embed, view=None)
        self.active_games.pop(interaction.message.id, None)

    @commands.hybrid_command(name="blackjack", aliases=["bj"], description="ブラックジャックで勝負！")
    @app_commands.describe(bet="掛けるコイン数", use_bonus="インシュランス・カードを使うか")
    async def blackjack(self, ctx: commands.Context, bet: int, use_bonus: bool = False):
        if bet <= 0:
            return await ctx.send("掛け金は1以上で指定してください。", ephemeral=True)

        async with aiohttp.ClientSession() as session:
            shared_id, user = await self.fetch_economy(session, ctx.author.id)
            if user["balance"] < bet:
                return await ctx.send("コインが足りません。", ephemeral=True)

            item_used = False
            if use_bonus:
                has_card = await item_utils.consume_item(shared_id, "insurance_card")
                if not has_card:
                    return await ctx.send("インシュランス・カードを持っていません。", ephemeral=True)
                item_used = True

            await self.update_balance(session, shared_id, user["balance"] - bet)

        deck = Deck()
        player_hand = [deck.draw(), deck.draw()]
        dealer_hand = [deck.draw(), deck.draw()]

        if item_used and random.random() < 0.20:
            while calculate_hand_value(dealer_hand) < 10:
                deck.reset()
                dealer_hand = [deck.draw(), deck.draw()]

        view = BlackJackView(self, ctx.author.id)
        game = {
            "deck": deck,
            "player_hand": player_hand,
            "dealer_hand": dealer_hand,
            "player_value": calculate_hand_value(player_hand),
            "dealer_value": calculate_hand_value(dealer_hand),
            "bet": bet,
            "economy": user,
            "shared_id": shared_id,
            "item_used": item_used,
            "view": view
        }

        if game["player_value"] == 21:
            embed = self.create_game_embed(game, reveal_dealer=True)
            msg = await ctx.send(embed=embed, view=None)
            await self.end_game(type("obj", (object,), {"message": msg}), game, "win", "ブラックジャック！")
            return

        embed = self.create_game_embed(game)
        msg = await ctx.send(embed=embed, view=view)
        self.active_games[msg.id] = game

async def setup(bot):
    await bot.add_cog(BlackJack(bot))
