import discord
from discord.ext import commands

class General(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="ping", description="Проверка работы бота")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pong!")

    @discord.app_commands.command(name="hello", description="Приветствие")
    async def hello(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Привет, {interaction.user.mention}!")

    # @discord.app_commands.command(name="userinfo", description="Информация о пользователе")
    # async def userinfo(self, interaction: discord.Interaction, member: discord.Member | None = None):
    #     member = member or interaction.user
    #     embed = discord.Embed(title=f"Info — {member}", color=discord.Color.blue())
    #     embed.add_field(name="ID", value=str(member.id))
    #     if member.avatar:
    #         embed.set_thumbnail(url=member.avatar.url)
    #     await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(General(bot))