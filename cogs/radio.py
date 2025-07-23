import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import asyncpg

DB_CONFIG = {
    "user": "orbisuser",
    "password": "orbispass",
    "database": "orbis",
    "host": "orbis-db",
    "port": 5432,
}

class Radio(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pool = None
        self.voice_clients = {}  # guild_id -> voice_client
        self.radio_tasks = {}    # guild_id -> task for monitoring
        self.radio_urls = {}     # guild_id -> current radio url

    async def cog_load(self):
        self.pool = await asyncpg.create_pool(**DB_CONFIG)
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS radio_settings (
                    guild_id BIGINT PRIMARY KEY,
                    url TEXT NOT NULL
                );
            """)
            # 読み込み済みのラジオURLをキャッシュ
            rows = await conn.fetch("SELECT guild_id, url FROM radio_settings")
            for row in rows:
                self.radio_urls[row["guild_id"]] = row["url"]

    async def set_radio_url(self, guild_id: int, url: str):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO radio_settings (guild_id, url)
                VALUES ($1, $2)
                ON CONFLICT (guild_id) DO UPDATE SET url=EXCLUDED.url
            """, guild_id, url)
        self.radio_urls[guild_id] = url

    async def get_radio_url(self, guild_id: int) -> str | None:
        if guild_id in self.radio_urls:
            return self.radio_urls[guild_id]
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT url FROM radio_settings WHERE guild_id = $1", guild_id)
            if row:
                self.radio_urls[guild_id] = row["url"]
                return row["url"]
        return None

    async def stop_radio(self, guild_id: int):
        # タスクがあればキャンセル
        if guild_id in self.radio_tasks:
            self.radio_tasks[guild_id].cancel()
            del self.radio_tasks[guild_id]
        # VC切断
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_connected():
            await vc.disconnect()
            del self.voice_clients[guild_id]
        # ラジオURLは残す（設定解除は別コマンドで）

    async def play_radio_stream(self, guild_id: int, voice_channel: discord.VoiceChannel):
        url = await self.get_radio_url(guild_id)
        if not url:
            return False

        try:
            # 既にVCにいる場合は移動
            vc = self.voice_clients.get(guild_id)
            if vc is None or not vc.is_connected():
                vc = await voice_channel.connect()
                self.voice_clients[guild_id] = vc
            elif vc.channel != voice_channel:
                await vc.move_to(voice_channel)

            # 再生中なら停止
            if vc.is_playing():
                vc.stop()

            # FFmpegでストリーム再生
            source = discord.FFmpegPCMAudio(
                url,
                options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
            )
            vc.play(source)

            return True
        except Exception as e:
            print(f"Radio play error: {e}")
            return False

    @app_commands.command(name="radio_set", description="受信するラジオのURLを設定を設定します。")
    @app_commands.describe(url="受信するラジオのURLを入力してください。")
    async def radio_set(self, interaction: discord.Interaction, url: str):
        await self.set_radio_url(interaction.guild.id, url)
        await interaction.response.send_message(f"✅ 受信するラジオのURLを設定しました。\nURL: {url}", ephemeral=True)

    @app_commands.command(name="radio_play", description="ラジオ再生を開始します。")
    async def radio_play(self, interaction: discord.Interaction):
        # ユーザーがVCにいるかチェック
        voice_state = interaction.user.voice
        if not voice_state or not voice_state.channel:
            await interaction.response.send_message("⚠️ まずVCに入ってください。", ephemeral=True)
            return

        url = await self.get_radio_url(interaction.guild.id)
        if not url:
            await interaction.response.send_message("❌ 受信するラジオのURLが設定されていません。`/radio_set`で設定してください。", ephemeral=True)
            return

        voice_channel = voice_state.channel

        success = await self.play_radio_stream(interaction.guild.id, voice_channel)
        if success:
            await interaction.response.send_message(f"▶️ ラジオを再生開始しました。", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ラジオの再生に失敗しました。", ephemeral=True)

    @app_commands.command(name="radio_stop", description="ラジオ再生を停止します。")
    async def radio_stop(self, interaction: discord.Interaction):
        await self.stop_radio(interaction.guild.id)
        await interaction.response.send_message("⏹️ ラジオの再生を停止しました。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Radio(bot))
