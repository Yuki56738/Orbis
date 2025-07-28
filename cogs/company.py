import discord
from discord.ext import commands
from discord import app_commands
from discord import Interaction, Member

from userdb import add_user_to_company, remove_user_from_company, get_company_by_user, get_company_members

class Company(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db  # `bot.db` に DB pool がある前提

    # -------------------------------------
    # /company create [名前]
    # -------------------------------------
    @app_commands.command(name="company_create", description="新しい企業を設立します")
    async def company_create(self, interaction: Interaction, name: str):
        user_id = interaction.user.id

        async with self.db.acquire() as conn:
            current = await get_company_by_user(conn, user_id)
            if current:
                return await interaction.response.send_message("既に企業に所属しています。", ephemeral=True)

            await add_user_to_company(conn, user_id, user_id, "leader")
            await interaction.response.send_message(f"企業「{name}」を設立しました！", ephemeral=True)

    # -------------------------------------
    # /company info [企業ID]
    # -------------------------------------
    @app_commands.command(name="company_info", description="企業の情報を表示します")
    async def company_info(self, interaction: Interaction, company_id: int):
        async with self.db.acquire() as conn:
            members = await get_company_members(conn, company_id)
            if not members:
                return await interaction.response.send_message("その企業IDは存在しません。", ephemeral=True)

            leader = next((m for m in members if m["role"] == "leader"), None)
            total_assets = sum(m["total_assets"] for m in members)

            embed = discord.Embed(title=f"企業情報（ID: {company_id}）", color=discord.Color.green())
            embed.add_field(name="設立者", value=f"<@{leader['user_id']}>" if leader else "不明", inline=False)
            embed.add_field(name="メンバー数", value=str(len(members)), inline=True)
            embed.add_field(name="総資産", value=f"{total_assets:,} Gold", inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)

    # -------------------------------------
    # /company invite [@ユーザー]
    # -------------------------------------
    @app_commands.command(name="company_invite", description="他のユーザーを企業に招待します")
    async def company_invite(self, interaction: Interaction, user: Member):
        inviter_id = interaction.user.id

        async with self.db.acquire() as conn:
            inviter_data = await get_company_by_user(conn, inviter_id)
            if not inviter_data or inviter_data["role"] != "leader":
                return await interaction.response.send_message("あなたは企業のリーダーではありません。", ephemeral=True)

            view = CompanyInviteView(inviter_id, user.id, self.db)
            try:
                await user.send(f"{interaction.user.mention} から企業（ID: {inviter_id}）への招待が届いています。", view=view)
                await interaction.response.send_message("招待を送信しました。", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("相手がDMを受け取れません。", ephemeral=True)

    # -------------------------------------
    # /company balance
    # -------------------------------------
    @app_commands.command(name="company_balance", description="企業の資産情報を表示します")
    async def company_balance(self, interaction: Interaction):
        user_id = interaction.user.id

        async with self.db.acquire() as conn:
            user_company = await get_company_by_user(conn, user_id)
            if not user_company:
                return await interaction.response.send_message("企業に所属していません。", ephemeral=True)

            members = await get_company_members(conn, user_company["company_id"])
            total = sum(m["total_assets"] for m in members)
            await interaction.response.send_message(f"企業の総資産：{total:,} Gold", ephemeral=True)

    # -------------------------------------
    # /company disband
    # -------------------------------------
    @app_commands.command(name="company_disband", description="企業を解散します（リーダー専用）")
    async def company_disband(self, interaction: Interaction):
        user_id = interaction.user.id

        async with self.db.acquire() as conn:
            user_company = await get_company_by_user(conn, user_id)
            if not user_company or user_company["role"] != "leader":
                return await interaction.response.send_message("あなたは企業のリーダーではありません。", ephemeral=True)

            members = await get_company_members(conn, user_company["company_id"])
            for m in members:
                await remove_user_from_company(conn, m["user_id"])

            await interaction.response.send_message("企業を解散しました。", ephemeral=True)

# -------------------------------------
# 招待ビュー
# -------------------------------------
class CompanyInviteView(discord.ui.View):
    def __init__(self, inviter_id, invitee_id, db):
        super().__init__(timeout=None)
        self.inviter_id = inviter_id
        self.invitee_id = invitee_id
        self.db = db

    @discord.ui.button(label="企業に参加する", style=discord.ButtonStyle.green)
    async def join_company(self, interaction: Interaction, button: discord.ui.Button):
        if interaction.user.id != self.invitee_id:
            return await interaction.response.send_message("このボタンはあなた専用です。", ephemeral=True)

        async with self.db.acquire() as conn:
            inviter_company = await get_company_by_user(conn, self.inviter_id)
            if not inviter_company:
                return await interaction.response.send_message("企業が解散された可能性があります。", ephemeral=True)

            await add_user_to_company(conn, inviter_company["company_id"], self.invitee_id, "member")
            await interaction.response.send_message("企業に参加しました！", ephemeral=True)

# -------------------------------------
# セットアップ関数
# -------------------------------------
async def setup(bot):
    await bot.add_cog(Company(bot))
