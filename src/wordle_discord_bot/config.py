import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
BOT_OWNER_ID = os.getenv("BOT_OWNER_ID", "")
BOT_HOME_GUILD_ID = os.getenv("BOT_HOME_GUILD_ID", "")
