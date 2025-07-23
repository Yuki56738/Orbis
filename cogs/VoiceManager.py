import discord
from discord.ext import commands
from discord import app_commands
import asyncio

class VoiceManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.vc_clients = {}  # guild_id: VoiceClient
        self.db = None  # DBHandlerを起動後に取得予定
        self.volume_default = 0.5  # 音量デフォルト(0.0~1.0)

    async def cog_load(self):
        # DBHandler Cogを取得
        self.db = self.bot.get_cog("DBHandler")
        # 起動時にDBから音量設定をロード（任意）
        for guild in self.bot.guilds:
            vol_str = await self.db.get_setting(guild.id, "voice_volume") if self.db else None
            vol = float(vol_str) if vol_str else self.volume_default
            self.vc_clients[guild.id] = {"client": None, "volume": vol}

    async def join_vc(self, guild: discord.Guild, channel: discord.VoiceChannel):
        if guild.id in self.vc_clients and self.vc_clients[guild.id]["client"] and self.vc_clients[guild.id]["client"].is_connected():
            return self.vc_clients[guild.id]["client"]
        vc_client = await channel.connect()
        volume = self.vc_clients.get(guild.id, {}).get("volume", self.volume_default)
        vc_client.source = discord.PCMVolumeTransformer(vc_client.source, volume=volume)
        self.vc_clients[guild.id] = {"client": vc_client, "volume": volume}
        return vc_client

    async def leave_vc(self, guild: discord.Guild):
        if guild.id in self.vc_clients and self.vc_clients[guild.id]["client"]:
            vc_client = self.vc_clients[guild.id]["client"]
            if vc_client.is_connected():
                await vc_client.disconnect()
            self.vc_clients[guild.id]["client"] = None

    async def set_volume(self, guild_id: int, volume: float):
        if guild_id not in self.vc_clients:
            self.vc_clients[guild_id] = {"client": None, "volume": volume}
        else:
            self.vc_clients[guild_id]["volume"] = volume
            vc_client = self.vc_clients[guild_id]["client"]
            if vc_client and vc_client.source:
                vc_client.source.volume = volume
        if self.db:
            await self.db.set_setting(guild_id, "voice_volume", str(volume))

    @app_commands.command(name="join", description="Botを指定VCに入室させます。")
    @app_commands.describe(channel="VCチャンネル")
    async def join(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        if not interaction.user.guild_permissions.connect:
            await interaction.response.send_message("🚫 VC接続権限がありません。", ephemeral=True)
            return
        try:
            await interaction.response.defer()
            vc_client = await self.join_vc(interaction.guild, channel)
            await interaction.followup.send(f"✅ `{channel.name}` にBotが入りました。")
        except Exception as e:
            await interaction.followup.send(f"❌ 入室に失敗しました: {e}")

    @app_commands.command(name="rejoin", description="BotのVC接続を切断して再接続します。")
    async def rejoin(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.connect:
            await interaction.response.send_message("🚫 VC接続権限がありません。", ephemeral=True)
            return
        try:
            await interaction.response.defer()
            guild_id = interaction.guild.id
            vc_info = self.vc_clients.get(guild_id)
            if not vc_info or not vc_info["client"]:
                await interaction.followup.send("❌ BotはVCに接続していません。")
                return
            vc_client = vc_info["client"]
            channel = vc_client.channel
            await vc_client.disconnect()
            await asyncio.sleep(1)  # 少し待機してから再接続
            new_vc = await channel.connect()
            volume = vc_info["volume"]
            new_vc.source = discord.PCMVolumeTransformer(new_vc.source, volume=volume)
            self.vc_clients[guild_id]["client"] = new_vc
            await interaction.followup.send(f"✅ `{channel.name}` に再接続しました。")
        except Exception as e:
            await interaction.followup.send(f"❌ 再接続に失敗しました: {e}")

    @app_commands.command(name="leave", description="BotをVCから退出させます。")
    async def leave(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.connect:
            await interaction.response.send_message("🚫 VC接続権限がありません。", ephemeral=True)
            return
        try:
            await interaction.response.defer()
            await self.leave_vc(interaction.guild)
            await interaction.followup.send("✅ BotはVCから退出しました。")
        except Exception as e:
            await interaction.followup.send(f"❌ 退出に失敗しました: {e}")

    @app_commands.command(name="volum", description="BotのVC内での音量を設定します。（0〜100）")
    @app_commands.describe(volume="音量(0〜100)")
    async def volum(self, interaction: discord.Interaction, volume: int):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("🚫 サーバー管理権限が必要です。", ephemeral=True)
            return
        if volume < 0 or volume > 100:
            await interaction.response.send_message("⚠️ 音量は0から100の範囲で指定してください。", ephemeral=True)
            return
        try:
            await interaction.response.defer()
            vol = volume / 100
            await self.set_volume(interaction.guild.id, vol)
            await interaction.followup.send(f"✅ 音量を{volume}%に設定しました。")
        except Exception as e:
            await interaction.followup.send(f"❌ 音量設定に失敗しました: {e}")

async def setup(bot):
    await bot.add_cog(VoiceManager(bot))
