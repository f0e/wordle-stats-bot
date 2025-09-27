import discord
from discord import app_commands
from discord.ext import commands

from .. import config


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="sync",
        description="Sync slash commands",
    )
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer()

        if str(interaction.user.id) != config.BOT_OWNER_ID:
            await interaction.followup.send(
                "You don't have permission to do that.",
                ephemeral=True,
            )
            return

        print("syncing slash commands")

        await self.bot.tree.sync()

        print("slash commands synced")

        await interaction.followup.send(
            "Slash commands synced successfully.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    if not config.BOT_HOME_GUILD_ID or not config.BOT_OWNER_ID:
        return

    guild = discord.Object(id=config.BOT_HOME_GUILD_ID)

    cog = AdminCog(bot)
    await bot.add_cog(cog, guild=guild)
