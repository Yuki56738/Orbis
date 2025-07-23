import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.voice_client import VoiceClient
import asyncio
import yt_dlp
import asyncpg
import random
import traceback
from userdb import UserDBHandler
from db import DBHandler



YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "extractaudio": True,
    "audioformat": "mp3",
    "outtmpl": "%(id)s.%(ext)s",
    "restrictfilenames": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0"
}

FFMPEG_OPTIONS = {
    "options": "-vn"
}

class YTDLSource(discord.PCMVolumeTransformer):
    ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.url = data.get("url")

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: cls.ytdl.extract_info(url, download=not stream))
        if data is None:
            raise Exception("情報取得に失敗しました。")
        if "entries" in data:
            data = data["entries"][0]
        filename = data["url"] if stream else cls.ytdl.prepare_filename(data)
        source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)
        return cls(source, data=data)

class MusicPlayer:
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        self.current = None  # 現在のYTDLSource
        self.voice_client: VoiceClient | None = None
        self.loop = False
        self.shuffle = False
        self.play_task = None
        self.stopped = False

    async def connect_voice(self, channel: discord.VoiceChannel):
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.move_to(channel)
        else:
            self.voice_client = await channel.connect()

    def is_playing(self):
        return self.voice_client and self.voice_client.is_playing()

    async def play_loop(self):
        while not self.stopped:
            self.next.clear()
            try:
                if self.loop and self.current:
                    source = self.current
                else:
                    source = await self.queue.get()
                    self.current = source
            except asyncio.CancelledError:
                break

            if not self.voice_client or not self.voice_client.is_connected():
                break

            self.voice_client.play(source, after=lambda e: self.bot.loop.call_soon_threadsafe(self.next.set))
            await self.next.wait()

            # ループオフかつキュー空なら停止
            if self.queue.empty() and not self.loop:
                self.current = None
                break

            # シャッフル時はキューをシャッフルしループさせる
            if self.queue.empty() and self.shuffle:
                # キューシャッフルは一旦queueからリスト取り出してシャッフルして再投入
                new_items = []
                while not self.queue.empty():
                    new_items.append(await self.queue.get())
                random.shuffle(new_items)
                for item in new_items:
                    await self.queue.put(item)

    async def start_playing(self):
        if self.play_task is None or self.play_task.done():
            self.stopped = False
            self.play_task = self.bot.loop.create_task(self.play_loop())

    async def stop(self):
        self.stopped = True
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
        if self.play_task:
            self.play_task.cancel()
        self.current = None
        # キュークリアは呼び出し側で行うことが多い

    async def pause(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()

    async def resume(self):
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()

    async def skip(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

    def get_queue_list(self):
        # queue._queueはdequeなのでリストに変換
        return list(self.queue._queue)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}  # guild.id -> MusicPlayer
        # DBハンドラはUserDBHandlerをbotにセット済みと想定
        self.userdb: UserDBHandler = bot.get_cog("UserDBHandler")
        self.db: DBHandler = bot.get_cog("DBHandler")

    def get_player(self, guild: discord.Guild) -> MusicPlayer:
        if guild.id not in self.players:
            self.players[guild.id] = MusicPlayer(self.bot, guild)
        return self.players[guild.id]

    @app_commands.command(name="music_play", description="音楽を再生・キューに追加します。")
    @app_commands.describe(url="YouTubeなどのURLか音声ファイルのパス")
    async def music_play(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer()
        player = self.get_player(interaction.guild)
        voice_state = interaction.user.voice
        if not voice_state or not voice_state.channel:
            await interaction.followup.send("❌ ボイスチャンネルに参加してから使ってください。", ephemeral=True)
            return

        if player.voice_client is None or not player.voice_client.is_connected():
            await player.connect_voice(voice_state.channel)

        try:
            source = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
            await player.queue.put(source)
            await interaction.followup.send(f"✅ キューに追加しました: **{source.title}**")
            if not player.is_playing():
                await player.start_playing()
        except Exception as e:
            await interaction.followup.send(f"❌ エラーが発生しました: {e}")

    @app_commands.command(name="music_stop", description="音楽の再生を停止します。")
    async def music_stop(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        await player.stop()
        await interaction.response.send_message("⏹ 再生を停止しました。")

    @app_commands.command(name="music_pause", description="音楽の再生を一時停止します。")
    async def music_pause(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        await player.pause()
        await interaction.response.send_message("⏸ 再生を一時停止しました。")

    @app_commands.command(name="music_resume", description="音楽の再生を再開します。")
    async def music_resume(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        await player.resume()
        await interaction.response.send_message("▶️ 再生を再開しました。")

    @app_commands.command(name="music_skip", description="現在の曲をスキップします。")
    async def music_skip(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        await player.skip()
        await interaction.response.send_message("⏭ 曲をスキップしました。")

    @app_commands.command(name="music_queue", description="キューの内容を表示します。")
    async def music_queue(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        queue = player.get_queue_list()
        if not queue:
            await interaction.response.send_message("キューは空です。", ephemeral=True)
            return
        embed = discord.Embed(title="再生キュー", color=discord.Color.blue())
        for i, song in enumerate(queue, start=1):
            embed.add_field(name=f"{i}.", value=song.title, inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="music_clear", description="キューを空にします。")
    async def music_clear(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        # キュー全クリア
        while not player.queue.empty():
            try:
                player.queue.get_nowait()
                player.queue.task_done()
            except asyncio.QueueEmpty:
                break
        await interaction.response.send_message("🗑 キューを空にしました。")

    @app_commands.command(name="music_loop", description="ループ再生のON/OFFを切り替えます。")
    async def music_loop(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        player.loop = not player.loop
        await interaction.response.send_message(f"🔁 ループ再生を {'ON' if player.loop else 'OFF'} にしました。")

    @app_commands.command(name="music_shuffle", description="シャッフル再生のON/OFFを切り替えます。")
    async def music_shuffle(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        player.shuffle = not player.shuffle
        await interaction.response.send_message(f"🔀 シャッフル再生を {'ON' if player.shuffle else 'OFF'} にしました。")

    @app_commands.command(name="music_nowplaying", description="現在再生中の曲を表示します。")
    async def music_nowplaying(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild)
        if player.current:
            await interaction.response.send_message(f"🎶 現在再生中: **{player.current.title}**")
        else:
            await interaction.response.send_message("現在再生中の曲はありません。", ephemeral=True)

    # プレイリスト関連コマンドはUserDBHandlerを使う

    @app_commands.command(name="playlist_create", description="プレイリストを作成します。")
    @app_commands.describe(name="プレイリスト名")
    async def playlist_create(self, interaction: discord.Interaction, name: str):
        user_id = interaction.user.id
        key = f"playlist:{name}"
        existing = await self.userdb.get_user_setting(user_id, key)
        if existing is not None:
            await interaction.response.send_message("⚠️ その名前のプレイリストはすでに存在します。", ephemeral=True)
            return
        await self.userdb.set_user_setting(user_id, key, "[]")
        await interaction.response.send_message(f"✅ プレイリスト「{name}」を作成しました。")

    @app_commands.command(name="playlist_remove", description="プレイリストを削除します。")
    @app_commands.describe(name="プレイリスト名")
    async def playlist_remove(self, interaction: discord.Interaction, name: str):
        user_id = interaction.user.id
        key = f"playlist:{name}"
        existing = await self.userdb.get_user_setting(user_id, key)
        if existing is None:
            await interaction.response.send_message("⚠️ そのプレイリストは存在しません。", ephemeral=True)
            return
        await self.userdb.delete_user_setting(user_id, key)
        await interaction.response.send_message(f"✅ プレイリスト「{name}」を削除しました。")

    @app_commands.command(name="playlist_list", description="自分のプレイリスト一覧を表示します。")
    async def playlist_list(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        query = "SELECT key FROM user_settings WHERE user_id = $1 AND key LIKE 'playlist:%'"
        async with self.userdb.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
        names = [row["key"][9:] for row in rows]  # 'playlist:'除去
        if not names:
            await interaction.response.send_message("プレイリストがありません。", ephemeral=True)
            return
        await interaction.response.send_message("🎵 プレイリスト一覧:\n" + "\n".join(names))

    @app_commands.command(name="playlist_see", description="プレイリストの中身を表示します。")
    @app_commands.describe(name="プレイリスト名")
    async def playlist_see(self, interaction: discord.Interaction, name: str):
        user_id = interaction.user.id
        key = f"playlist:{name}"
        data = await self.userdb.get_user_setting(user_id, key)
        if data is None:
            await interaction.response.send_message("⚠️ そのプレイリストは存在しません。", ephemeral=True)
            return
        import json
        try:
            playlist = json.loads(data)
        except Exception:
            playlist = []
        if not playlist:
            await interaction.response.send_message("プレイリストは空です。", ephemeral=True)
            return
        desc = "\n".join(f"{i+1}. {item['title']}" for i, item in enumerate(playlist))
        await interaction.response.send_message(f"🎶 プレイリスト「{name}」の曲:\n{desc}")

    @app_commands.command(name="playlist_song_add", description="プレイリストに曲を追加します。")
    @app_commands.describe(playlist_name="プレイリスト名", url="曲のURL")
    async def playlist_song_add(self, interaction: discord.Interaction, playlist_name: str, url: str):
        user_id = interaction.user.id
        key = f"playlist:{playlist_name}"
        data = await self.userdb.get_user_setting(user_id, key)
        if data is None:
            await interaction.response.send_message("⚠️ そのプレイリストは存在しません。", ephemeral=True)
            return
        import json
        try:
            playlist = json.loads(data)
        except Exception:
            playlist = []
        # YTDLでタイトル取得(同期処理はasyncioでラップ)
        try:
            info = await asyncio.get_event_loop().run_in_executor(None, lambda: yt_dlp.YoutubeDL(YTDL_OPTIONS).extract_info(url, download=False))
            if "entries" in info:
                info = info["entries"][0]
            title = info.get("title", url)
        except Exception:
            title = url
        playlist.append({"url": url, "title": title})
        await self.userdb.set_user_setting(user_id, key, json.dumps(playlist))
        await interaction.response.send_message(f"✅ プレイリスト「{playlist_name}」に曲を追加しました。")

    @app_commands.command(name="playlist_song_queue", description="今のキューの曲をプレイリストに追加します。")
    @app_commands.describe(playlist_name="プレイリスト名")
    async def playlist_song_queue(self, interaction: discord.Interaction, playlist_name: str):
        user_id = interaction.user.id
        key = f"playlist:{playlist_name}"
        data = await self.userdb.get_user_setting(user_id, key)
        if data is None:
            await interaction.response.send_message("⚠️ そのプレイリストは存在しません。", ephemeral=True)
            return
        import json
        try:
            playlist = json.loads(data)
        except Exception:
            playlist = []
        player = self.get_player(interaction.guild)
        queue = player.get_queue_list()
        if not queue:
            await interaction.response.send_message("キューは空です。", ephemeral=True)
            return
        for song in queue:
            playlist.append({"url": song.data.get("webpage_url", ""), "title": song.title})
        await self.userdb.set_user_setting(user_id, key, json.dumps(playlist))
        await interaction.response.send_message(f"✅ プレイリスト「{playlist_name}」にキューの曲を追加しました。")

    @app_commands.command(name="playlist_song_nowplaying", description="現在再生中の曲をプレイリストに追加します。")
    @app_commands.describe(playlist_name="プレイリスト名")
    async def playlist_song_nowplaying(self, interaction: discord.Interaction, playlist_name: str):
        user_id = interaction.user.id
        key = f"playlist:{playlist_name}"
        data = await self.userdb.get_user_setting(user_id, key)
        if data is None:
            await interaction.response.send_message("⚠️ そのプレイリストは存在しません。", ephemeral=True)
            return
        import json
        player = self.get_player(interaction.guild)
        if not player.current:
            await interaction.response.send_message("現在再生中の曲はありません。", ephemeral=True)
            return
        try:
            playlist = json.loads(data)
        except Exception:
            playlist = []
        playlist.append({"url": player.current.data.get("webpage_url", ""), "title": player.current.title})
        await self.userdb.set_user_setting(user_id, key, json.dumps(playlist))
        await interaction.response.send_message(f"✅ プレイリスト「{playlist_name}」に現在再生中の曲を追加しました。")

    @app_commands.command(name="playlist_song_remove", description="プレイリストの曲を削除します。")
    @app_commands.describe(playlist_name="プレイリスト名", number="曲番号")
    async def playlist_song_remove(self, interaction: discord.Interaction, playlist_name: str, number: int):
        user_id = interaction.user.id
        key = f"playlist:{playlist_name}"
        data = await self.userdb.get_user_setting(user_id, key)
        if data is None:
            await interaction.response.send_message("⚠️ そのプレイリストは存在しません。", ephemeral=True)
            return
        import json
        try:
            playlist = json.loads(data)
        except Exception:
            playlist = []
        if number < 1 or number > len(playlist):
            await interaction.response.send_message("⚠️ 無効な曲番号です。", ephemeral=True)
            return
        playlist.pop(number - 1)
        await self.userdb.set_user_setting(user_id, key, json.dumps(playlist))
        await interaction.response.send_message(f"✅ プレイリスト「{playlist_name}」から曲を削除しました。")

async def setup(bot):
    await bot.add_cog(Music(bot))
