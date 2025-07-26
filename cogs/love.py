import discord
from discord import app_commands
from discord.ext import commands,tasks
import random
from utils.item import use_item
import json
import os
from datetime import datetime,timedelta
import pytz

class Love(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.characters = {}
        self.NIGHT_ONLY_EVENTS = ["night_skay", "co-sleeping", "kiss"]
        json_path = os.path.join("data", "charactor.json")
        self.event_cache = {}
        self.cache_path = os.path.join("data", "love_event_cache.json")
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                self.characters = json.load(f)
        except Exception as e:
            print(f"キャラクターjson読み込み失敗: {e}")
        self.load_event_cache()
        self.event_check_loop.start()

    def is_night_time(self):
        jst = pytz.timezone("Asia/Tokyo")
        now = datetime.now(jst).time()
        return now >= datetime.strptime("20:00", "%H:%M").time() or now <= datetime.strptime("05:00", "%H:%M").time()

    def try_love_event(self, user_id, chara_id, affection, love):
        chara = self.characters.get(chara_id)
        if not chara or "love_event" not in chara:
            return None

        events = chara["love_event"]
        eligible_events = []

        for event_name, event_data in events.items():
            req = event_data.get("requirement", {})
            req_aff = req.get("affection", 0)
            req_love = req.get("love", 0)
            chance = event_data.get("chance", 0)

            if affection >= req_aff and love >= req_love:
                if event_name in self.NIGHT_ONLY_EVENTS and not self.is_night_time():
                    continue
                if random.random() <= chance:
                    eligible_events.append((chance, event_name, event_data))

        if not eligible_events:
            return None

        eligible_events.sort(key=lambda x: x[0])
        _, event_name, event_data = eligible_events[0]

        return {
            "event_name": event_name,
            "text": event_data["text"],
            "image": event_data["image"]
        }

    async def get_user_love_status(self, user_id: int):
        db = self.bot.get_cog("UserDBHandler")
        love = await db.get_user_setting(user_id, "love_level")
        affection = await db.get_user_setting(user_id, "affection_level")
        intimacy = await db.get_user_setting(user_id, "intimacy_level")
        love = int(love) if love else 0
        affection = int(affection) if affection else 0
        intimacy = int(intimacy) if intimacy else 0
        return love, affection, intimacy

    async def update_user_love_status(self, user_id: int, love: int = None, affection: int = None, intimacy: int = None):
        db = self.bot.get_cog("UserDBHandler")
        def clamp(val):
            return max(0, min(100, val))
        if love is not None:
            await db.set_user_setting(user_id, "love_level", str(clamp(love)))
        if affection is not None:
            await db.set_user_setting(user_id, "affection_level", str(clamp(affection)))
        if intimacy is not None:
            await db.set_user_setting(user_id, "intimacy_level", str(clamp(intimacy)))

    async def get_partner_character(self, user_id: int):
        db = self.bot.get_cog("UserDBHandler")
        partner_id = await db.get_partner_character(user_id)
        if partner_id and partner_id in self.characters:
            return partner_id, self.characters[partner_id]
        return None, None
    
    def load_event_cache(self):
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.event_cache = json.load(f)
            except Exception:
                self.event_cache = {}

    def save_event_cache(self):
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self.event_cache, f, ensure_ascii=False, indent=2)

    @tasks.loop(hours=1)
    async def event_check_loop(self):
        jst = pytz.timezone("Asia/Tokyo")
        now = datetime.now(jst)
        today_str = now.strftime("%Y-%m-%d")

        db = self.bot.get_cog("UserDBHandler")
        if not db:
            print("UserDBHandlerが未登録です")
            return

        all_users = await db.get_all_user_ids()

        for user_id in all_users:
            last_trigger = self.event_cache.get(str(user_id))
            if last_trigger == today_str:
                continue  # 今日すでに発火済み

            partner_id, _ = await self.get_partner_character(user_id)
            if not partner_id:
                continue

            love, affection, _ = await self.get_user_love_status(user_id)
            result = self.try_love_event(user_id, partner_id, affection, love)
            if result:
                try:
                    user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
                    if user:
                        embed = discord.Embed(
                            title=f"💖 特別なイベント発生！",
                            description=result["text"],
                            color=0xff69b4
                        )
                        embed.set_image(url=result["image"])
                        await user.send(embed=embed)
                        self.event_cache[str(user_id)] = today_str
                except Exception as e:
                    print(f"[ERROR] DM送信失敗: {e}")
                    continue

        self.save_event_cache()




    # --- コマンド ---

    @app_commands.command(name="love_status", description="恋愛ステータスを確認します。")
    async def love_status(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        partner_id, partner_data = await self.get_partner_character(user_id)
        if not partner_id:
            await interaction.response.send_message("まだ話すキャラが設定されていません。`/set_partner` で設定してください。", ephemeral=True)
            return

        love, affection, intimacy = await self.get_user_love_status(user_id)
        embed = discord.Embed(
            title=f"❤️ {partner_id} との恋愛ステータス",
            description=f"今のあなたとの関係を確認しよう！",
            color=0xff69b4
        )
        embed.add_field(name="恋愛度", value=f"{love}/100", inline=True)
        embed.add_field(name="好感度", value=f"{affection}/100", inline=True)
        embed.add_field(name="親密度", value=f"{intimacy}/100", inline=True)
        if partner_data.get("profile_image"):
            embed.set_thumbnail(url=partner_data["profile_image"])

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="love_gift", description="キャラにアイテムをプレゼントして好感度アップ！")
    @app_commands.describe(item_id="プレゼントするアイテムID")
    async def love_gift(self, interaction: discord.Interaction, item_id: str):
        user_id = interaction.user.id
        guild_id = interaction.guild.id if interaction.guild else 0
        gov_id = f"{guild_id}-{user_id}"
        partner_id, partner_data = await self.get_partner_character(user_id)

        if not partner_id:
            await interaction.response.send_message("話すキャラが設定されていません。`/set_partner` で設定してください。", ephemeral=True)
            return

        success = await use_item(gov_id, item_id)
        if not success:
            await interaction.response.send_message("そのアイテムは持っていないか、使用できません。", ephemeral=True)
            return

        love_inc = random.randint(1, 5)
        affection_inc = random.randint(2, 7)
        intimacy_inc = random.randint(3, 10)

        love, affection, intimacy = await self.get_user_love_status(user_id)
        await self.update_user_love_status(user_id,
                                           love=love + love_inc,
                                           affection=affection + affection_inc,
                                           intimacy=intimacy + intimacy_inc)

        embed = discord.Embed(
            title=f"🎁 {partner_id} にプレゼント！",
            description=f"{partner_id}はとても喜んでいるよ！\n"
                        f"恋愛度+{love_inc} 好感度+{affection_inc} 親密度+{intimacy_inc}",
            color=0xff69b4
        )
        if partner_data.get("event") and partner_data["event"].get("happy"):
            embed.set_image(url=partner_data["event"]["happy"].get("image"))
            embed.add_field(name="ひとこと", value=partner_data["event"]["happy"].get("text"))

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="love_date", description="デートしよう！恋愛度などで成功判定！")
    async def love_date(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        partner_id, partner_data = await self.get_partner_character(user_id)

        if not partner_id:
            await interaction.response.send_message("話すキャラが設定されていません。`/set_partner` で設定してください。", ephemeral=True)
            return

        love, affection, intimacy = await self.get_user_love_status(user_id)
        score = love + affection + intimacy + random.randint(-20, 20)

        if score >= 180:
            msg = f"デートは大成功！{partner_id}はとっても喜んでいるよ！"
            img_url = partner_data.get("event", {}).get("happy", {}).get("image")
        elif score >= 120:
            msg = f"デートはまずまず成功！{partner_id}との時間を楽しんだよ。"
            img_url = partner_data.get("event", {}).get("neutral", {}).get("image")
        else:
            msg = f"デートは残念ながらうまくいかなかったみたい…{partner_id}はちょっと悲しそう。"
            img_url = partner_data.get("event", {}).get("sad", {}).get("image")

        embed = discord.Embed(
            title="💕 デートの結果",
            description=msg,
            color=0xff69b4
        )
        if img_url:
            embed.set_image(url=img_url)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="love_confess", description="キャラに告白します。")
    async def love_confess(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        partner_id, partner_data = await self.get_partner_character(user_id)

        if not partner_id:
            await interaction.response.send_message("話すキャラが設定されていません。`/set_partner` で設定してください。", ephemeral=True)
            return

        love, affection, intimacy = await self.get_user_love_status(user_id)
        score = love + affection + intimacy

        if score >= 220:
            msg = f"告白は成功！{partner_id}もあなたのことが好きみたい！これからも仲良くしようね！"
            img_url = partner_data.get("event", {}).get("happy", {}).get("image")
        else:
            msg = f"告白は残念ながら失敗。{partner_id}はまだあなたのことを見ているようです…。"
            img_url = partner_data.get("event", {}).get("sad", {}).get("image")

        embed = discord.Embed(
            title="💌 告白の結果",
            description=msg,
            color=0xff69b4
        )
        if img_url:
            embed.set_image(url=img_url)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Love(bot))
