import discord
from discord.ext import commands
from discord import app_commands
import asyncpg

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db: asyncpg.Pool = None

    async def cog_load(self):
        self.db = self.bot.get_cog("DBHandler").pool
        await self.create_tables()

    async def create_tables(self):
        async with self.db.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    guild_id BIGINT,
                    user_id BIGINT,
                    channel_id BIGINT PRIMARY KEY
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    guild_id BIGINT,
                    key TEXT,
                    value TEXT,
                    PRIMARY KEY (guild_id, key)
                )
            """)

    async def get_open_ticket(self, guild_id: int, user_id: int):
        async with self.db.acquire() as conn:
            row = await conn.fetchrow("SELECT channel_id FROM tickets WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
            return row["channel_id"] if row else None

    async def create_ticket_record(self, guild_id: int, user_id: int, channel_id: int):
        async with self.db.acquire() as conn:
            await conn.execute(
                "INSERT INTO tickets (guild_id, user_id, channel_id) VALUES ($1, $2, $3)",
                guild_id, user_id, channel_id
            )

    async def delete_ticket_record(self, guild_id: int, user_id: int):
        async with self.db.acquire() as conn:
            await conn.execute(
                "DELETE FROM tickets WHERE guild_id = $1 AND user_id = $2",
                guild_id, user_id
            )

    @app_commands.command(name="ticket_create", description="チケット用テキストチャンネルを作成します。")
    async def ticket_create(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild

        existing_channel_id = await self.get_open_ticket(guild.id, user.id)
        if existing_channel_id:
            await interaction.response.send_message("❌ あなたは既にチケットを開いています。", ephemeral=True)
            return

        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM settings WHERE guild_id = $1 AND key = 'ticket_category_id'",
                guild.id
            )
            if not row:
                await interaction.response.send_message("⚠️ チケット用カテゴリが設定されていません。管理者に問い合わせてください。", ephemeral=True)
                return
            category_id = int(row["value"])

        category = guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("⚠️ チケット用カテゴリが見つかりません。", ephemeral=True)
            return

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

        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id FROM tickets WHERE guild_id = $1 AND channel_id = $2",
                guild.id, channel.id
            )
            if not row:
                await interaction.response.send_message("❌ このチャンネルはチケットチャンネルではありません。", ephemeral=True)
                return

            ticket_user_id = row["user_id"]
            if user.id != ticket_user_id:
                await interaction.response.send_message("🚫 あなたはこのチケットの所有者ではありません。", ephemeral=True)
                return

        await self.delete_ticket_record(guild.id, user.id)
        await channel.delete(reason="Ticket closed by user")

async def setup(bot):
    await bot.add_cog(Tickets(bot))
