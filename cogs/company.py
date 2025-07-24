import discord
from discord.ext import commands
from discord import app_commands

from typing import Optional

class Company(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.companies = {}  # 仮のメモリDB（本番はSQLとAPIで）

    # -------------------------------------
    # /company create [名前]
    # -------------------------------------
    @app_commands.command(name="company_create", description="新しい企業を設立します")
    async def company_create(self, interaction: discord.Interaction, name: str):
        user_id = str(interaction.user.id)
        if user_id in self.companies:
            await interaction.response.send_message("既にあなたは企業に所属しています。", ephemeral=True)
            return

        company_id = f"cmp_{user_id}"
        self.companies[user_id] = {
            "name": name,
            "leader": user_id,
            "members": {user_id: "リーダー"},
            "balance": 0
        }
        await interaction.response.send_message(f"企業「{name}」を設立しました！", ephemeral=True)

    # -------------------------------------
    # /company info [企業ID]
    # -------------------------------------
    @app_commands.command(name="company_info", description="企業の情報を表示します")
    async def company_info(self, interaction: discord.Interaction, company_id: str):
        for uid, data in self.companies.items():
            if f"cmp_{uid}" == company_id:
                embed = discord.Embed(title=f"企業情報：{data['name']}", color=discord.Color.blue())
                embed.add_field(name="設立者", value=f"<@{data['leader']}>", inline=False)
                embed.add_field(name="メンバー数", value=str(len(data['members'])), inline=True)
                embed.add_field(name="所持資産", value=f"{data['balance']} Gold", inline=True)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

        await interaction.response.send_message("その企業IDは存在しません。", ephemeral=True)

    # -------------------------------------
    # /company invite [@ユーザー]
    # -------------------------------------
    @app_commands.command(name="company_invite", description="他のユーザーを企業に招待します")
    async def company_invite(self, interaction: discord.Interaction, user: discord.User):
        inviter_id = str(interaction.user.id)
        company = self.companies.get(inviter_id)
        if not company or company["leader"] != inviter_id:
            await interaction.response.send_message("あなたは企業のリーダーではありません。", ephemeral=True)
            return

        # 永久有効なボタン付きDM
        view = CompanyInviteView(inviter_id, user.id, self.companies)
        try:
            await user.send(f"{interaction.user.mention} から企業「{company['name']}」への招待が届いています。", view=view)
            await interaction.response.send_message("招待を送信しました。", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("相手がDMを受け取れないようです。", ephemeral=True)

    # -------------------------------------
    # /company balance
    # -------------------------------------
    @app_commands.command(name="company_balance", description="企業の資産情報を表示します")
    async def company_balance(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        company = self.companies.get(user_id)
        if not company:
            await interaction.response.send_message("企業に所属していません。", ephemeral=True)
            return
        await interaction.response.send_message(f"企業資産：{company['balance']} Gold", ephemeral=True)

    # -------------------------------------
    # /company disband
    # -------------------------------------
    @app_commands.command(name="company_disband", description="企業を解散します（リーダー専用）")
    async def company_disband(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        company = self.companies.get(user_id)
        if not company or company["leader"] != user_id:
            await interaction.response.send_message("あなたは企業のリーダーではありません。", ephemeral=True)
            return

        del self.companies[user_id]
        await interaction.response.send_message("企業を解散しました。", ephemeral=True)

# -------------------------------------
# ボタン付き招待のビュー
# -------------------------------------
class CompanyInviteView(discord.ui.View):
    def __init__(self, inviter_id, invitee_id, companies):
        super().__init__(timeout=None)
        self.inviter_id = inviter_id
        self.invitee_id = invitee_id
        self.companies = companies

    @discord.ui.button(label="企業に参加する", style=discord.ButtonStyle.green)
    async def join_company(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != str(self.invitee_id):
            await interaction.response.send_message("このボタンはあなたのものではありません。", ephemeral=True)
            return

        inviter_company = self.companies.get(self.inviter_id)
        if not inviter_company:
            await interaction.response.send_message("企業が既に解散されている可能性があります。", ephemeral=True)
            return

        inviter_company["members"][str(self.invitee_id)] = "メンバー"
        self.companies[self.invitee_id] = inviter_company
        await interaction.response.send_message(f"企業「{inviter_company['name']}」に参加しました。", ephemeral=True)

# -------------------------------------
# セットアップ関数
# -------------------------------------
async def setup(bot):
    await bot.add_cog(Company(bot))
