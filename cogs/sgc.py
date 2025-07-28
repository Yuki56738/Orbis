import discord
from discord.ext import commands
from discord import app_commands
import json
import urllib.parse

JSON_CHANNEL_ID = 123456789012345678  # JSON送信用チャンネルID（DB管理なら不要かも）

class SGCClient(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db  # DBHandlerインスタンスが bot.db にセットされている前提

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # SGCに接続されているチャンネルのみ処理（DBで判定）
        if message.guild and await self.db.is_sgc_connected(message.guild.id, message.channel.id):
            dic = {
                "type": "message",
                "version": "2",
                "userId": str(message.author.id),
                "userName": message.author.name,
                "userDiscriminator": message.author.discriminator,
                "guildId": str(message.guild.id),
                "guildName": message.guild.name,
                "channelId": str(message.channel.id),
                "channelName": message.channel.name,
                "messageId": str(message.id),
                "content": message.content
            }
            if message.attachments:
                dic["attachmentsUrl"] = [att.proxy_url for att in message.attachments]
            if message.reference:
                try:
                    ref = await message.channel.fetch_message(message.reference.message_id)
                    if ref.author == self.bot.user and ref.embeds:
                        footer = ref.embeds[0].footer.text
                        for part in footer.split(" / "):
                            if part.startswith("mID:"):
                                dic["reference"] = part.replace("mID:", "", 1)
                                break
                    else:
                        dic["reference"] = str(ref.id)
                except:
                    pass

            jsondata = json.dumps(dic, ensure_ascii=False)
            json_channel = self.bot.get_channel(JSON_CHANNEL_ID)
            if json_channel:
                await json_channel.send(jsondata)
            await message.add_reaction("✅")
            return

        # JSONチャネルのメッセージ受信 → 他のSGC接続チャンネルへ転送
        if message.channel.id == JSON_CHANNEL_ID:
            if message.author == self.bot.user:
                return
            try:
                dic = json.loads(message.content)
            except json.JSONDecodeError:
                return

            if dic.get("type") != "message":
                return

            for channel in self.bot.get_all_channels():
                if (
                    isinstance(channel, discord.TextChannel)
                    and await self.db.is_sgc_connected(channel.guild.id, channel.id)
                    and channel.guild.id != int(dic["guildId"])
                ):
                    embed = discord.Embed(description=dic["content"], color=0x9B95C9)
                    embed.set_author(
                        name=f"{dic['userName']}#{dic['userDiscriminator']}",
                        icon_url=f"https://cdn.discordapp.com/avatars/{dic['userId']}/{dic.get('userAvatar', '')}.png?size=1024"
                    )
                    embed.set_footer(
                        text=f"{dic['guildName']} / mID:{dic['messageId']}",
                        icon_url=f"https://cdn.discordapp.com/icons/{dic['guildId']}/{dic.get('guildIcon', '')}.png?size=1024"
                    )
                    if dic.get("attachmentsUrl"):
                        embed.set_image(url=urllib.parse.unquote(dic["attachmentsUrl"][0]))
                    await channel.send(embed=embed)

    @app_commands.command(name="sgc_connect", description="このチャンネルをSGCに接続します")
    async def sgc_connect(self, interaction: discord.Interaction):
        await self.db.connect_sgc(interaction.guild.id, interaction.channel.id)
        await interaction.response.send_message("✅ このチャンネルをSGCに接続しました。", ephemeral=True)

    @app_commands.command(name="sgc_disconnect", description="このチャンネルのSGC接続を解除します")
    async def sgc_disconnect(self, interaction: discord.Interaction):
        await self.db.disconnect_sgc(interaction.guild.id, interaction.channel.id)
        await interaction.response.send_message("❌ このチャンネルのSGC接続を解除しました。", ephemeral=True)

    @app_commands.command(name="sgc_status", description="このチャンネルがSGCに接続されているか確認します")
    async def sgc_status(self, interaction: discord.Interaction):
        connected = await self.db.is_sgc_connected(interaction.guild.id, interaction.channel.id)
        if connected:
            await interaction.response.send_message("✅ このチャンネルはSGCに **接続されています**。", ephemeral=True)
        else:
            await interaction.response.send_message("❌ このチャンネルはSGCに **接続されていません**。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SGCClient(bot))