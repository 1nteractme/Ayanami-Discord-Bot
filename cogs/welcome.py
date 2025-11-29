""" <summary>
Greets a new member of the server with a welcome message.
</summary> """

import os
import discord, discord.ext.commands as commands

class Welcome(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = member.guild.get_channel(int(os.getenv("WELCOME_CHANNEL_ID", 0)))
        if channel:
            await channel.send(f"Добро пожаловать, {member.mention}! 🎉")

async def setup(bot):
    await bot.add_cog(Welcome(bot))