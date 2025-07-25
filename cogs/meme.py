import discord
from discord.ext import commands
from discord import app_commands
import random

class MemeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # GIFのURL一覧（TenorなどのGIFリンクを入れてください）
        self.gif_urls = [
            "https://tenor.com/view/disco-time-gif-18195529",
            "https://tenor.com/view/cat-annoyed-stare-side-eye-gif-16732086699915766519",
            "https://tenor.com/view/chient-mat-chienmat-gif-12285493229007254431",
            "https://tenor.com/view/hahahahah-gahahahaha-haha-ha-fun-gif-14720055923291368119",
            "https://tenor.com/view/shrek-rizz-shrek-meme-gif-13109705573733693514",
            "https://tenor.com/view/bailes-gif-12538695882059836355",
            "https://tenor.com/view/huh-cat-huh-m4rtin-huh-huh-meme-what-cat-gif-8048702078111616715",
            "https://tenor.com/view/hmm-sulley-monsters-inc-james-sullivan-shocked-gif-15802869",
            "https://tenor.com/view/daisuke-beatmania-beatmania-iidx-iidx-music-gif-16032323",
            "https://tenor.com/view/explosion-mushroom-cloud-atomic-bomb-bomb-boom-gif-4464831",
            "https://tenor.com/view/shia-la-beouf-clap-clapping-applause-impressed-gif-4427576",
            "https://tenor.com/view/house-explosion-explode-boom-kaboom-gif-19506150"
        ]

    @app_commands.command(name="meme", description="ランダムなGIFでちょっとしたテロを仕掛けます。何が出るかはお楽しみ！")
    async def meme(self, interaction: discord.Interaction):
        gif_url = random.choice(self.gif_urls)
        await interaction.response.send_message(content=gif_url)

async def setup(bot: commands.Bot):
    await bot.add_cog(MemeCog(bot))
