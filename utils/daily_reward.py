from discord.ext import tasks, commands
import asyncio
import random
from datetime import datetime, time, timedelta
from cogs.economy import EconomyAPI

class DailyPetReward(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reward_task.start()

    @tasks.loop(minutes=1)
    async def reward_task(self):
        now = datetime.utcnow()
        if now.time().hour == 0 and now.time().minute == 0:
            await self.distribute_rewards()

    async def distribute_rewards(self):
        userdb = self.bot.get_cog("UserDBHandler")
        economy: EconomyAPI = self.bot.get_cog("EconomyAPI")

        all_actions = await userdb.get_all_today_pet_actions()
        for record in all_actions:
            guild_id = record["guild_id"]
            user_id = record["user_id"]
            count = record["command_count"]
            multiplier = random.randint(50, 100)
            reward = count * multiplier
            await economy.add_money(guild_id, user_id, reward)

            user = self.bot.get_user(user_id)
            if user:
                try:
                    await user.send(f"🌙 今日のペット活動のご褒美：{reward} コインをゲット！おやすみ！")
                except:
                    pass  # DM失敗は無視

        await userdb.reset_pet_action_counts()

    def cog_unload(self):
        self.reward_task.cancel()

async def setup(bot):
    await bot.add_cog(DailyPetReward(bot))
