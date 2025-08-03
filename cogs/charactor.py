import discord
from discord.ext import commands
import random
import json
import os

from cogs.userdb import UserDBHandler

# from utils.userdb import UserDBHandler

CHARACTER_JSON_PATH = "data/charactor.json"

class CharacterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = UserDBHandler(bot)
        self.characters = self.load_characters()

    def load_characters(self):
        if not os.path.exists(CHARACTER_JSON_PATH):
            return {}
        with open(CHARACTER_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_random_message(self, character_id):
        char_data = self.characters.get(character_id)
        if not char_data:
            return None

        # 通常メッセージキー（"msg1", "msg2", ...）のみ抽出
        msgs = [v for k, v in char_data.items() if not isinstance(v, dict)]
        return random.choice(msgs) if msgs else None

    async def send_character_embed(self, ctx, character_id):
        msg = self.get_random_message(character_id)
        if not msg:
            await ctx.send("このキャラのセリフが見つかりませんでした。")
            return

        embed = discord.Embed(
            title="📣 キャラからのメッセージ",
            description=msg["text"],
            color=discord.Color.orange()
        )
        if msg.get("image"):
            embed.set_image(url=msg["image"])

        await ctx.send(embed=embed)

    @commands.command(name="set_partner")
    async def set_partner(self, ctx, character_name: str):
        """キャラパートナーを選択するコマンド"""
        if character_name not in self.characters:
            await ctx.send("そのキャラは存在しません。")
            return

        await self.db.set_partner_character(ctx.author.id, character_name)
        await ctx.send(f"✅ パートナーを `{character_name}` に設定しました！")

    @commands.command(name="talking")
    async def talking(self, ctx):
        """選択中のキャラとおしゃべり！"""
        character = await self.db.get_partner_character(ctx.author.id)
        if not character:
            await ctx.send("まず `/set_partner [キャラ名]` でキャラを選択してください。")
            return

        await self.send_character_embed(ctx, character)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return

        character = await self.db.get_partner_character(message.author.id)
        if not character:
            return  # キャラ未設定なら返信しない

        try:
            await self.send_character_embed(message.channel, character)
        except Exception as e:
            print(f"[Charactor DM Error]: {e}")

async def setup(bot):
    await bot.add_cog(CharacterCog(bot))
