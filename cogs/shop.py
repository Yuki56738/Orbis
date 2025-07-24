import discord
from discord.ext import commands
from discord import app_commands, ui
from ..utils import economy_api, shop as shop_utils, item as item_utils, misc

class PurchaseModal(ui.Modal, title="購入数量を入力"):
    quantity = ui.TextInput(label="数量", placeholder="1", required=True)

    def __init__(self, view: "ShopView", item_id: str):
        super().__init__()
        self.view = view
        self.item_id = item_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.quantity.value)
            if qty < 1:
                raise ValueError
        except:
            return await interaction.response.send_message("1以上の整数を入力してください。", ephemeral=True)
        await self.view.process_purchase(interaction, self.item_id, qty)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f"エラー: {error}", ephemeral=True)


class ShopView(ui.View):
    def __init__(self, author: discord.Member, shop_items: dict[str, dict]):
        super().__init__(timeout=180)
        self.author = author
        self.shop_items = shop_items
        self.selected = None
        self.stock = 0
        self.balance = 0
        self.add_item(self._create_dropdown())

    def _create_dropdown(self):
        opts = [
            discord.SelectOption(label=v["name"], value=key, description=f"{v['price']:,}コイン")
            for key, v in self.shop_items.items()
        ]
        dropdown = ui.Select(placeholder="購入するアイテムを選んでください", options=opts)
        dropdown.callback = self.on_select
        return dropdown

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("あなたしか操作できません。", ephemeral=True)
            return False
        return True

    async def on_select(self, interaction: discord.Interaction):
        self.selected = interaction.data["values"][0]
        gov = misc.get_shared_id(interaction.guild.id, interaction.user.id)

        self.balance = (await economy_api.EconomyAPI(interaction.client.http_session).get_user(gov))["balance"]
        self.stock = await shop_utils.fetch_item_stock(self.selected)
        owned = await item_utils.get_user_item_count(gov, self.selected)  # ← 修正ポイント

        info = self.shop_items[self.selected]
        embed = discord.Embed(
            title=info["name"], description=info["description"], color=discord.Color.blue()
        )
        embed.add_field(name="価格", value=f"{info['price']:,}コイン", inline=True)
        embed.add_field(name="在庫", value=f"{self.stock:,}", inline=True)
        embed.add_field(name="所持数", value=f"{owned:,} / {info['max_own']}", inline=True)
        embed.add_field(name="所持コイン", value=f"{self.balance:,}コイン", inline=False)

        btn = next((b for b in self.children if isinstance(b, ui.Button) and b.custom_id == "buy_btn"), None)
        if btn: btn.disabled = False

        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="購入", style=discord.ButtonStyle.green, custom_id="buy_btn", disabled=True)
    async def buy_button(self, interaction: discord.Interaction, button: ui.Button):
        modal = PurchaseModal(self, self.selected)
        await interaction.response.send_modal(modal)

    async def process_purchase(self, interaction: discord.Interaction, item_id: str, qty: int):
        gov = misc.get_shared_id(interaction.guild.id, interaction.user.id)
        info = self.shop_items[item_id]

        total = info["price"] * qty
        if self.balance < total:
            return await interaction.response.send_message("残高が足りません。", ephemeral=True)

        stock = await shop_utils.fetch_item_stock(item_id)
        if stock < qty:
            return await interaction.response.send_message("在庫が不足しています。", ephemeral=True)

        ok = await shop_utils.purchase_item(gov, item_id, qty)
        ok &= await item_utils.add_item(gov, item_id, qty)
        ok &= await economy_api.EconomyAPI(interaction.client.http_session).update_user(gov, {"balance": self.balance - total})
        if not ok:
            return await interaction.response.send_message("購入に失敗しました。", ephemeral=True)

        await interaction.response.send_message(f"{info['name']}を{qty}個購入しました！", ephemeral=True)
        self.stop()


class Shop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command()
    @app_commands.describe()
    async def shop(self, ctx: commands.Context):
        embed = discord.Embed(title="🏬 ショップ", description="メニューからアイテムを選んでください。", color=discord.Color.blurple())

        # 🔄 DB + JSON連携で取得
        items = await shop_utils.fetch_shop_items()
        item_map = {item["item_id"]: item for item in items if item["active"]}

        view = ShopView(ctx.author, item_map)
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))