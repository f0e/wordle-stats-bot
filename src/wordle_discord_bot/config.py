import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
test_guild_id_str = os.getenv("TEST_GUILD_ID")
TEST_GUILD_ID = int(test_guild_id_str) if test_guild_id_str is not None else None
