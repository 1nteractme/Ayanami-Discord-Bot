""" <summary>
Creates a private room when connected to the parent channel.
</summary> """

import os
from discord.ext import commands

class VoiceManager(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if after.channel and after.channel.id == int(os.getenv("VOICE_CHANNEL_ID", 0)):
            new_room = await member.guild.create_voice_channel(
                name=f"{member.name}'s Personal Room",
                category=after.channel.category
            )
            await new_room.set_permissions(member, connect=True, view_channel=True)
            await member.move_to(new_room)

        if before.channel and before.channel.name.endswith("'s Personal Room") and len(before.channel.members) == 0:
            await before.channel.delete()

async def setup(bot):
    await bot.add_cog(VoiceManager(bot))