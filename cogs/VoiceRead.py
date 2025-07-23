import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import aiohttp
import asyncpg

# VoiceVox APIのURL（例。実際のVoiceVoxサーバーのURLに合わせてください）
VOICEVOX_API_BASE = "http://localhost:50021" #ここはまだ仮。どっかからかっさらわないと…

class VoiceRead(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # DBプールは両方のCogで共有してる想定（ここはアクセス用）
        self.server_db = None
        self.user_db = None
        self.tts_lock = asyncio.Lock()
        self.voice_clients = {}  # guild_id -> voice_client

    async def cog_load(self):
        # それぞれのDBハンドラをCogから取得
        self.server_db = self.bot.get_cog("DBHandler")  # サーバ設定DB
        self.user_db = self.bot.get_cog("UserDBHandler")  # ユーザ設定DB
        if not self.server_db or not self.user_db:
            print("VoiceRead: DBHandler/UserDBHandlerが見つかりません。")

    ### サーバーデータベース関連メソッド ###

    async def get_read_channels(self, guild_id: int) -> list[int]:
        # サーバーの読み上げ対象チャンネルIDリスト（カンマ区切り文字列をリストに変換）
        value = await self.server_db.get_setting(guild_id, "read_channels")
        if not value:
            return []
        try:
            return list(map(int, value.split(",")))
        except Exception:
            return []

    async def add_read_channel(self, guild_id: int, channel_id: int):
        channels = await self.get_read_channels(guild_id)
        if channel_id not in channels:
            channels.append(channel_id)
            await self.server_db.set_setting(guild_id, "read_channels", ",".join(map(str, channels)))

    async def remove_read_channel(self, guild_id: int, channel_id: int):
        channels = await self.get_read_channels(guild_id)
        if channel_id in channels:
            channels.remove(channel_id)
            await self.server_db.set_setting(guild_id, "read_channels", ",".join(map(str, channels)))

    async def get_word_dict(self, guild_id: int) -> dict:
        # 単語辞書はJSON文字列で保存（key:単語, value:読み方）
        import json
        raw = await self.server_db.get_setting(guild_id, "word_dict")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}

    async def save_word_dict(self, guild_id: int, word_dict: dict):
        import json
        await self.server_db.set_setting(guild_id, "word_dict", json.dumps(word_dict, ensure_ascii=False))

    ### ユーザーデータベース関連メソッド ###

    async def get_user_voice(self, user_id: int) -> int | None:
        # voicevoxの声IDをintで返す
        val = await self.user_db.get_user_setting(user_id, "voicevox_voice")
        if val is None:
            return None
        try:
            return int(val)
        except Exception:
            return None

    async def set_user_voice(self, user_id: int, voice_id: int):
        await self.user_db.set_user_setting(user_id, "voicevox_voice", str(voice_id))

    async def remove_user_voice(self, user_id: int):
        await self.user_db.delete_user_setting(user_id, "voicevox_voice")

    ### Discordコマンド群 ###

    @app_commands.group(name="readch", description="読み上げ対象チャンネルの管理")
    async def readch(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🚫 管理者権限が必要です。", ephemeral=True)
            return

    @readch.command(name="now", description="現在の読み上げ対象チャンネルを確認します。")
    async def readch_now(self, interaction: discord.Interaction):
        channels = await self.get_read_channels(interaction.guild.id)
        if not channels:
            await interaction.response.send_message("📭 現在読み上げ対象チャンネルは登録されていません。", ephemeral=True)
            return
        channel_mentions = "、".join(f"<#{cid}>" for cid in channels)
        await interaction.response.send_message(f"📢 読み上げ対象チャンネル:\n{channel_mentions}", ephemeral=True)

    @readch.command(name="add", description="読み上げ対象のテキストチャンネルを追加します。")
    @app_commands.describe(channel="読み上げ対象に追加するテキストチャンネル")
    async def readch_add(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.add_read_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(f"✅ {channel.mention} を読み上げ対象チャンネルに追加しました。", ephemeral=True)

    @readch.command(name="remove", description="読み上げ対象からテキストチャンネルを除外します。")
    @app_commands.describe(channel="読み上げ対象から除外するテキストチャンネル")
    async def readch_remove(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self.remove_read_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(f"✅ {channel.mention} を読み上げ対象チャンネルから除外しました。", ephemeral=True)

    @app_commands.group(name="dict", description="読み上げ辞書の管理")
    async def dict(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🚫 管理者権限が必要です。", ephemeral=True)
            return

    @dict.command(name="add", description="単語の読み方を追加します。")
    @app_commands.describe(word="単語", reading="読み方")
    async def dict_add(self, interaction: discord.Interaction, word: str, reading: str):
        word_dict = await self.get_word_dict(interaction.guild.id)
        word_dict[word] = reading
        await self.save_word_dict(interaction.guild.id, word_dict)
        await interaction.response.send_message(f"✅ `{word}` の読み方を `{reading}` に追加しました。", ephemeral=True)

    @dict.command(name="remove", description="単語の読み方を削除します。")
    @app_commands.describe(word="単語")
    async def dict_remove(self, interaction: discord.Interaction, word: str):
        word_dict = await self.get_word_dict(interaction.guild.id)
        if word in word_dict:
            del word_dict[word]
            await self.save_word_dict(interaction.guild.id, word_dict)
            await interaction.response.send_message(f"✅ `{word}` の読み方を削除しました。", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ `{word}` の読み方は登録されていません。", ephemeral=True)

    @app_commands.command(name="voice", description="指定メンバーの読み上げ声を変更します（管理者専用）。メンバー未指定なら自分の声を変更します。")
    @app_commands.describe(member="対象メンバー（省略時は自分）", voicevox_id="VoiceVoxの声のID（数値）")
    async def voice(self, interaction: discord.Interaction, voicevox_id: int, member: discord.Member = None):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("🚫 管理者権限が必要です。", ephemeral=True)
            return
        target = member or interaction.user
        await self.set_user_voice(target.id, voicevox_id)
        await interaction.response.send_message(f"✅ {target.display_name} さんの読み上げ声を VoiceVox ID `{voicevox_id}` に設定しました。", ephemeral=True)

    ### 実際の読み上げ処理（例） ###

    async def text_to_speech(self, guild_id: int, text: str, voice_id: int = 1) -> bytes:
        # VoiceVoxのAPIを使いwavデータを取得する例
        # 音声バイナリを返すので、Discordのplayで再生できるようにする

        async with aiohttp.ClientSession() as session:
            # 1. 音声合成テキスト解析
            params = {"text": text, "speaker": voice_id}
            async with session.post(f"{VOICEVOX_API_BASE}/audio_query", params=params) as resp:
                if resp.status != 200:
                    raise Exception("VoiceVox audio_query API error")
                audio_query = await resp.json()

            # 2. 音声合成
            headers = {"Content-Type": "application/json"}
            async with session.post(f"{VOICEVOX_API_BASE}/synthesis?speaker={voice_id}", json=audio_query, headers=headers) as resp:
                if resp.status != 200:
                    raise Exception("VoiceVox synthesis API error")
                wav_bytes = await resp.read()
                return wav_bytes

    import discord.opus
from discord import PCMVolumeTransformer, FFmpegPCMAudio

class VoiceRead(commands.Cog):
    # ...（前略）

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return  # DM無視

        guild_id = message.guild.id
        channel_id = message.channel.id

        # 読み上げ対象チャンネルかチェック
        read_channels = await self.get_read_channels(guild_id)
        if channel_id not in read_channels:
            return

        voice_state = message.author.voice
        voice_channel = voice_state.channel

        # 辞書置換
        word_dict = await self.get_word_dict(guild_id)
        text = message.content
        for word, reading in word_dict.items():
            text = text.replace(word, reading)

        # 話者の声ID取得（なければデフォルト1）
        voice_id = await self.get_user_voice(message.author.id) or 1

        # TTS音声データ取得
        try:
            async with self.tts_lock:
                wav_data = await self.text_to_speech(guild_id, text, voice_id)
        except Exception as e:
            print(f"VoiceRead TTS error: {e}")
            return

        # VC接続と再生
        try:
            vc = self.voice_clients.get(guild_id)
            if vc is None or not vc.is_connected():
                vc = await voice_channel.connect()
                self.voice_clients[guild_id] = vc
            elif vc.channel != voice_channel:
                await vc.move_to(voice_channel)

            # 再生のためにwavデータを一時ファイルに保存
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
                tmpfile.write(wav_data)
                tmp_path = tmpfile.name

            audio_source = PCMVolumeTransformer(FFmpegPCMAudio(tmp_path))
            play_done = asyncio.Event()

            def after_playing(error):
                if error:
                    print(f"VoiceRead playback error: {error}")
                play_done.set()

            vc.play(audio_source, after=after_playing)
            await play_done.wait()

            # 再生終了後に一時ファイルを削除
            import os
            os.remove(tmp_path)

        except Exception as e:
            print(f"VoiceRead VC playback error: {e}")

async def setup(bot):
    await bot.add_cog(VoiceRead(bot))
