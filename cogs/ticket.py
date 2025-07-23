import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite

DB_PATH = "./orbis.db"

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_open_ticket(self, guild_id: int, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT channel_id FROM tickets WHERE guild_id=? AND user_id=?", (guild_id, user_id)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def create_ticket_record(self, guild_id: int, user_id: int, channel_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO tickets (guild_id, user_id, channel_id) VALUES (?, ?, ?)", (guild_id, user_id, channel_id))
            await db.commit()

    async def delete_ticket_record(self, guild_id: int, user_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM tickets WHERE guild_id=? AND user_id=?", (guild_id, user_id))
            await db.commit()

    @app_commands.command(name="ticket_create", description="チケット用テキストチャンネルを作成します。")
    async def ticket_create(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild
        # 既存チケットチェック
        existing_channel_id = await self.get_open_ticket(guild.id, user.id)
        if existing_channel_id:
            await interaction.response.send_message("❌ あなたは既にチケットを開いています。", ephemeral=True)
            return
        # カテゴリ取得(DB設定想定)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT value FROM settings_{} WHERE key='ticket_category_id'".format(guild.id)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await interaction.response.send_message("⚠️ チケット用カテゴリが設定されていません。管理者に問い合わせてください。", ephemeral=True)
                    return
                category_id = int(row[0])
        category = guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("⚠️ チケット用カテゴリが見つかりません。", ephemeral=True)
            return
        # チャンネル作成
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        channel = await guild.create_text_channel(f"ticket-{user.display_name}", category=category, overwrites=overwrites, reason="Ticket created")
        await self.create_ticket_record(guild.id, user.id, channel.id)
        await interaction.response.send_message(f"✅ チケットチャンネル {channel.mention} を作成しました。", ephemeral=True)

    @app_commands.command(name="ticket_close", description="自分のチケットを閉じて削除します。")
    async def ticket_close(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel
        # チケットDB確認
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id FROM tickets WHERE guild_id=? AND channel_id=?", (guild.id, channel.id)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await interaction.response.send_message("❌ このチャンネルはチケットチャンネルではありません。", ephemeral=True)
                    return
                ticket_user_id = row[0]
        if user.id != ticket_user_id:
            await interaction.response.send_message("🚫 あなたはこのチケットの所有者ではありません。", ephemeral=True)
            return
        # 削除処理
        await self.delete_ticket_record(guild.id, user.id)
        await channel.delete(reason="Ticket closed by user")
        # 返信はできないので無音

async def setup(bot):
    # チケットDBテーブル作成
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                guild_id INTEGER,
                user_id INTEGER,
                channel_id INTEGER PRIMARY KEY
            )
        """)
        await db.commit()
    await bot.add_cog(Tickets(bot))
