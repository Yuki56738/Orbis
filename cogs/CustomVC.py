import discord
from discord.ext import commands, tasks
from discord import app_commands

class CustomVC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_empty_vcs.start()

    def cog_unload(self):
        self.check_empty_vcs.cancel()

    async def cog_load(self):
        # 起動時に custom_vcs テーブルを作成
        async with self.bot.get_cog("DBHandler").pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS custom_vcs (
                    guild_id BIGINT,
                    vc_id BIGINT PRIMARY KEY,
                    tc_id BIGINT,
                    owner_id BIGINT
                )
            """)

    @tasks.loop(minutes=1)
    async def check_empty_vcs(self):
        db = self.bot.get_cog("DBHandler")
        async with db.pool.acquire() as conn:
            rows = await conn.fetch("SELECT guild_id, vc_id, tc_id FROM custom_vcs")
            for row in rows:
                guild = self.bot.get_guild(row["guild_id"])
                if not guild:
                    await conn.execute("DELETE FROM custom_vcs WHERE guild_id = $1 AND vc_id = $2", row["guild_id"], row["vc_id"])
                    continue
                vc_channel = guild.get_channel(row["vc_id"])
                tc_channel = guild.get_channel(row["tc_id"])
                if not vc_channel or not tc_channel:
                    await conn.execute("DELETE FROM custom_vcs WHERE guild_id = $1 AND vc_id = $2", row["guild_id"], row["vc_id"])
                    continue
                if len(vc_channel.members) == 0:
                    try:
                        await vc_channel.delete(reason="Custom VC empty, deleting")
                    except Exception:
                        pass
                    try:
                        await tc_channel.delete(reason="Custom VC empty, deleting")
                    except Exception:
                        pass
                    await conn.execute("DELETE FROM custom_vcs WHERE guild_id = $1 AND vc_id = $2", row["guild_id"], row["vc_id"])

    async def create_custom_vc(self, guild: discord.Guild, user: discord.Member, vc_name: str):
        db = self.bot.get_cog("DBHandler")
        async with db.pool.acquire() as conn:
            await db.create_table_if_needed(guild.id)
            row = await conn.fetchrow(f"SELECT value FROM settings_{guild.id} WHERE key = $1", "custom_vc_category_id")
            if not row:
                raise Exception("カスタムVC用カテゴリが設定されていません。")
            category_id = int(row["value"])

        category = guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            raise Exception("カスタムVC用カテゴリが見つかりません。")

        # VC作成
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False),
            user: discord.PermissionOverwrite(connect=True, manage_channels=True, mute_members=True, deafen_members=True)
        }
        vc = await guild.create_voice_channel(vc_name, category=category, overwrites=overwrites, reason="Custom VC created")

        # 聞き専テキストチャンネル作成
        tc_overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        tc = await guild.create_text_channel(f"{vc_name}-listener", category=category, overwrites=tc_overwrites, reason="Listener text channel")

        # DB登録
        async with db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO custom_vcs (guild_id, vc_id, tc_id, owner_id)
                VALUES ($1, $2, $3, $4)
            """, guild.id, vc.id, tc.id, user.id)

        return vc, tc

    @app_commands.command(name="customvc_create", description="カスタムVCと聞き専テキストチャンネルを作成します。")
    @app_commands.describe(name="作成するVCの名前")
    async def customvc_create(self, interaction: discord.Interaction, name: str):
        try:
            vc, tc = await self.create_custom_vc(interaction.guild, interaction.user, name)
            await interaction.response.send_message(f"✅ カスタムVC `{vc.name}` と聞き専テキスト `{tc.name}` を作成しました。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ エラー: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(CustomVC(bot))
