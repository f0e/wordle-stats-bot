import discord
from discord.ext import commands
from dotenv import load_dotenv
from rich import print

from . import config
from .cogs import wordle_cog
from .database import create_tables

description = """Wordle Results Tracker Bot"""

load_dotenv()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)


class WordleBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="%",
            description=description,
            intents=intents,
            allowed_mentions=allowed_mentions,
        )

    async def setup_hook(self):
        await wordle_cog.setup(self, config.TEST_GUILD_ID)

        print("All cogs initialised")

    async def close(self):
        await super().close()

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        print(f"Guilds: {[guild.name for guild in self.guilds]}")


print("Initializing database...")
create_tables()
print("Database tables verified.")

bot = WordleBot()
bot.run(config.DISCORD_TOKEN)
