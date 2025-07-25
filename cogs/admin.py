import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import json

class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- BAN コマンド ---
    @app_commands.command(name="ban", description="指定ユーザーをBANします。")
    @app_commands.describe(member="BANするユーザー", reason="理由（任意）")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message("🚫 BAN権限がありません。", ephemeral=True)
            return
        await member.ban(reason=reason)
        await interaction.response.send_message(f"✅ {member.mention} をBANしました。")

    # --- キック ---
    @app_commands.command(name="kick", description="指定ユーザーをキックします。")
    @app_commands.describe(member="キックするユーザー", reason="理由（任意）")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message("🚫 キック権限がありません。", ephemeral=True)
            return
        await member.kick(reason=reason)
        await interaction.response.send_message(f"✅ {member.mention} をキックしました。")

    # --- メッセージ一括削除 ---
    @app_commands.command(name="clear", description="指定数のメッセージを削除します。")
    @app_commands.describe(amount="削除するメッセージ数")
    async def clear(self, interaction: discord.Interaction, amount: int):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("🚫 メッセージ管理権限がありません。", ephemeral=True)
            return
        await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(f"🧹 {amount}件のメッセージを削除しました。", ephemeral=True)

    # --- ユーザー情報 ---
    @app_commands.command(name="userinfo", description="ユーザー情報を表示します。")
    @app_commands.describe(user="対象ユーザー")
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member):
        embed = discord.Embed(title=f"{user.display_name} の情報", color=discord.Color.blue())
        embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)
        embed.add_field(name="ユーザー名", value=user.name, inline=True)
        embed.add_field(name="ID", value=user.id, inline=True)
        embed.add_field(name="参加日", value=user.joined_at.strftime("%Y/%m/%d"), inline=False)
        embed.add_field(name="作成日", value=user.created_at.strftime("%Y/%m/%d"), inline=False)
        await interaction.response.send_message(embed=embed)

    # --- サーバー情報 ---
    @app_commands.command(name="serverinfo", description="サーバーの情報を表示します。")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title=f"{guild.name} の情報", color=discord.Color.green())
        embed.set_thumbnail(url=guild.icon.url if guild.icon else "")
        embed.add_field(name="メンバー数", value=guild.member_count, inline=True)
        embed.add_field(name="チャンネル数", value=len(guild.channels), inline=True)
        embed.add_field(name="作成日", value=guild.created_at.strftime("%Y/%m/%d"), inline=False)
        await interaction.response.send_message(embed=embed)

class RoleSelectView(View):
    def __init__(self, roles: list[discord.Role]):
        super().__init__(timeout=None)
        self.roles = roles
        for role in roles:
            self.add_item(RoleToggleButton(role))

class RoleToggleButton(Button):
    def __init__(self, role: discord.Role):
        super().__init__(label=role.name, custom_id=f"role_toggle_{role.id}", style=discord.ButtonStyle.primary)
        self.role = role

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        if self.role in user.roles:
            await user.remove_roles(self.role)
            await interaction.response.send_message(f"🗑️ {self.role.name} を外しました。", ephemeral=True)
        else:
            await user.add_roles(self.role)
            await interaction.response.send_message(f"✅ {self.role.name} を付与しました。", ephemeral=True)

class AdminPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- ロールパネル設定 ---
    @app_commands.command(name="rolepanel_set", description="ロールパネルを設定します。")
    @app_commands.describe(name="パネル名", roles="対象ロール（スペース区切りで複数可、メンション形式）")
    async def rolepanel_set(self, interaction: discord.Interaction, name: str, roles: str):
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("🚫 ロール管理権限がありません。", ephemeral=True)
            return

        role_ids = []
        for r in roles.split():
            if r.startswith("<@&") and r.endswith(">"):
                rid = int(r[3:-1])
                role_ids.append(rid)
            else:
                await interaction.response.send_message(f"❌ ロール指定の形式が不正です: `{r}`", ephemeral=True)
                return

        db = self.bot.get_cog("DBHandler")
        if db is None:
            await interaction.response.send_message("❌ DB Cog が見つかりません。", ephemeral=True)
            return

        roles_json = json.dumps(role_ids)
        await db.set_setting(interaction.guild.id, f"rolepanel_{name}", roles_json)
        await interaction.response.send_message(f"✅ ロールパネル `{name}` を設定しました。（送信は `/rolepanel_send` で）", ephemeral=True)

    # --- ロールパネル送信 ---
    @app_commands.command(name="rolepanel_send", description="ロールパネルを送信します。")
    @app_commands.describe(name="パネル名", channel="送信先チャンネル（空欄で現在のチャンネル）")
    async def rolepanel_send(self, interaction: discord.Interaction, name: str, channel: discord.TextChannel = None):
        db = self.bot.get_cog("DBHandler")
        if db is None:
            await interaction.response.send_message("❌ DB Cog が見つかりません。", ephemeral=True)
            return

        roles_json = await db.get_setting(interaction.guild.id, f"rolepanel_{name}")
        if roles_json is None:
            await interaction.response.send_message("❌ その名前のパネルは存在しません。", ephemeral=True)
            return

        role_ids = json.loads(roles_json)
        role_objs = [interaction.guild.get_role(rid) for rid in role_ids]
        view = RoleSelectView(role_objs)
        embed = discord.Embed(title=f"ロールパネル：{name}", description="ボタンを押すとロールの付与/解除ができます", color=discord.Color.teal())
        target_channel = channel or interaction.channel
        await target_channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ パネルを送信しました。", ephemeral=True)

    # --- 通報チャンネル設定 ---
    @app_commands.command(name="report_setchannel", description="通報受付チャンネルを設定します。")
    async def report_setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🚫 管理者のみが設定できます。", ephemeral=True)
            return

        db = self.bot.get_cog("DBHandler")
        if db is None:
            await interaction.response.send_message("❌ DB Cog が見つかりません。", ephemeral=True)
            return

        await db.set_setting(interaction.guild.id, "report_channel", str(channel.id))
        await interaction.response.send_message(f"✅ 通報チャンネルを `{channel.name}` に設定しました。", ephemeral=True)

    # --- 通報送信 ---
    @app_commands.command(name="report", description="ユーザーを通報します。")
    @app_commands.describe(target="通報対象", reason="通報の理由")
    async def report(self, interaction: discord.Interaction, target: discord.Member, reason: str):
        db = self.bot.get_cog("DBHandler")
        if db is None:
            await interaction.response.send_message("❌ DB Cog が見つかりません。", ephemeral=True)
            return

        report_channel_id = await db.get_setting(interaction.guild.id, "report_channel")
        if report_channel_id is None:
            await interaction.response.send_message("⚠️ 通報チャンネルが設定されていません。", ephemeral=True)
            return

        channel = self.bot.get_channel(int(report_channel_id))
        if channel is None:
            await interaction.response.send_message("❌ 通報チャンネルが見つかりません。", ephemeral=True)
            return

        embed = discord.Embed(title="📢 通報が届きました", color=discord.Color.red())
        embed.add_field(name="対象ユーザー", value=f"{target.mention}（ID: {target.id}）", inline=False)
        embed.add_field(name="理由", value=reason, inline=False)
        embed.set_footer(text=f"通報者: 匿名（{interaction.user.id}）")
        await channel.send(embed=embed)
        await interaction.response.send_message("✅ 通報が送信されました。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Admin(bot))
    await bot.add_cog(AdminPanel(bot))
