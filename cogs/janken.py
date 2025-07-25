import discord
from discord.ext import commands
from discord import app_commands
import random
from utils import economy_api

CHOICES = {
    "✊": "rock",
    "✌️": "scissors",
    "🖐️": "paper"
}

MULTIPLIERS = {
    1: 1.5,
    2: 2.25,
    3: 5.0
}

class JankenButton(discord.ui.Button):
    def __init__(self, label, emoji, callback_fn):
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.primary)
        self.callback_fn = callback_fn

    async def callback(self, interaction: discord.Interaction):
        await self.callback_fn(interaction, self.emoji.name)


class JankenView(discord.ui.View):
    def __init__(self, shared_id, bet_amount, session, timeout=60):
        super().__init__(timeout=timeout)
        self.shared_id = shared_id
        self.bet_amount = bet_amount
        self.session = session
        self.rounds = 0
        self.user_wins = 0
        self.dealer_wins = 0
        self.result_log = []

        for emoji in CHOICES.keys():
            self.add_item(JankenButton(label="", emoji=emoji, callback_fn=self.handle_choice))

    async def handle_choice(self, interaction: discord.Interaction, user_emoji: str):
        if interaction.user.id != interaction.user.id:
            await interaction.response.send_message("これはあなたのゲームではありません。", ephemeral=True)
            return

        user_choice = CHOICES[user_emoji]
        dealer_choice = random.choice(list(CHOICES.values()))

        result = self.judge(user_choice, dealer_choice)
        self.result_log.append((user_choice, dealer_choice, result))

        if result == "win":
            self.user_wins += 1
        elif result == "lose":
            self.dealer_wins += 1

        self.rounds += 1

        if self.rounds >= 3:
            for child in self.children:
                child.disabled = True
            await self.process_results(interaction)
        else:
            await interaction.response.edit_message(content=f"あなた: {user_choice} vs ディーラー: {dealer_choice} → {result.upper()}！\n"
                                                            f"{self.rounds}/3 回戦", view=self)

    def judge(self, user, dealer):
        if user == dealer:
            return "draw"
        elif (user == "rock" and dealer == "scissors") or \
             (user == "scissors" and dealer == "paper") or \
             (user == "paper" and dealer == "rock"):
            return "win"
        else:
            return "lose"

    async def process_results(self, interaction: discord.Interaction):
        multiplier = MULTIPLIERS.get(self.user_wins, 0)
        winnings = int(self.bet_amount * multiplier)

        api = economy_api.EconomyAPI(self.session)
        if multiplier > 0:
            await api.update_user(self.shared_id, {"delta": winnings})
            result_text = f"🎉 {self.user_wins}勝で{winnings}円ゲット！（倍率x{multiplier}）"
        else:
            result_text = f"💸 全敗でした……残念！掛け金は戻りません。"

        log = "\n".join([f"Round {i+1}: あなた {u} vs ディーラー {d} → {r.upper()}" for i, (u, d, r) in enumerate(self.result_log)])

        await interaction.response.edit_message(
            content=f"{log}\n\n{result_text}",
            view=self
        )


class Janken(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    @app_commands.command(name="janken", description="じゃんけんでお金を稼ごう！3本勝負です")
    @app_commands.describe(bet="掛け金（所持金の範囲内で）")
    async def janken(self, interaction: discord.Interaction, bet: int):
        if bet <= 0:
            await interaction.response.send_message("掛け金は正の整数である必要があります。", ephemeral=True)
            return

        shared_id = f"{interaction.guild_id}-{interaction.user.id}"
        api = economy_api.EconomyAPI(self.session)
        user = await api.get_user(shared_id)
        if not user:
            await interaction.response.send_message("ユーザー情報が取得できませんでした。", ephemeral=True)
            return

        if user["balance"] < bet:
            await interaction.response.send_message(f"所持金が不足しています。現在の所持金：{user['balance']}円", ephemeral=True)
            return

        await api.update_user(shared_id, {"delta": -bet})  # 掛け金を引く

        view = JankenView(shared_id, bet, self.session)
        await interaction.response.send_message(
            content=f"🎲 じゃんけんスタート！掛け金：{bet}円\n3回じゃんけんしましょう！ボタンを押して選んでください！",
            view=view
        )

    def cog_unload(self):
        asyncio.create_task(self.session.close())


async def setup(bot: commands.Bot):
    await bot.add_cog(Janken(bot))