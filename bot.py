import os
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True

class MyBot(commands.Bot):

    async def setup_hook(self):
        # Загружаем одиночные файлы
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                await self.load_extension(f"cogs.{filename[:-3]}")

        # Загружаем модули
        # await self.load_extension("cogs.ttv_monitor")

        await self.tree.sync()

bot = MyBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot ready! {bot.user} (id {bot.user.id})")

bot.run(TOKEN)