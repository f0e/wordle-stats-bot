import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, Optional

import discord
from discord.ext import commands

from ..database import GuildUserStats, SessionLocal, WordlePlay

WORDLE_USER_ID = 1211781489931452447


def parse_wordle_message(content: str) -> Optional[Dict]:
    # Check if it's a Wordle results message
    streak_pattern = r"\*\*Your group is on a (\d+) day streak!\*\* 🔥+ Here are yesterday's results:"

    streak_match = re.search(streak_pattern, content)
    if not streak_match:
        return None

    streak_days = int(streak_match.group(1))

    # Parse individual results
    results = []

    lines = content.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Look for score patterns
        score_patterns = [
            r"👑?\s*(\d|X)/6:\s*(.+)",  # Crown optional, number or X, followed by user mentions
            r"(\d|X)/6:\s*(.+)",  # Just number or X followed by user mentions
        ]

        for pattern in score_patterns:
            match = re.search(pattern, line)
            if match:
                score_str = match.group(1)
                mentions_str = match.group(2)

                # Convert score (X means failed)
                guesses = None if score_str == "X" else int(score_str)

                # Extract user IDs from mentions
                user_ids = re.findall(r"<@(\d+)>", mentions_str)

                for user_id in user_ids:
                    results.append(
                        {
                            "user_id": user_id,
                            "guesses": guesses,
                            "is_crown": "👑" in line,
                        }
                    )
                break

    if not results:
        return None

    return {"streak_days": streak_days, "results": results}


async def save_results_to_db(guild_id: int, message_id: int, parsed_results: Dict):
    db = SessionLocal()
    try:
        for result in parsed_results["results"]:
            user_id = result["user_id"]
            guesses = result["guesses"]

            # Ensure user exists in guild_user_stats
            existing_user = (
                db.query(GuildUserStats)
                .filter(
                    GuildUserStats.guild_id == guild_id,
                    GuildUserStats.discord_user_id == int(user_id),
                )
                .first()
            )

            if not existing_user:
                new_user = GuildUserStats(
                    guild_id=guild_id, discord_user_id=int(user_id)
                )
                db.add(new_user)
                db.commit()  # Commit to ensure the user exists before adding plays

            # Check if this play already exists (avoid duplicates)
            existing_play = (
                db.query(WordlePlay)
                .filter(
                    WordlePlay.guild_id == guild_id,
                    WordlePlay.discord_user_id == int(user_id),
                    WordlePlay.stats_discord_message_id == int(message_id),
                )
                .first()
            )

            if not existing_play:
                new_play = WordlePlay(
                    guild_id=guild_id,
                    discord_user_id=int(user_id),
                    stats_discord_message_id=int(message_id),
                    guesses=guesses,
                    played_at=datetime.utcnow(),
                )
                db.add(new_play)

        db.commit()
        print(f"✅ Saved {len(parsed_results['results'])} Wordle results to database")

    except Exception as e:
        db.rollback()
        print(f"❌ Error saving to database: {e}")
        raise
    finally:
        db.close()


async def scan_historical_messages(bot: commands.Bot):
    print("🔍 Starting historical scan for Wordle messages...")

    # Check if we've already done a historical scan
    db = SessionLocal()
    try:
        existing_plays = db.query(WordlePlay).limit(1).first()
        if existing_plays:
            print("📊 Database already contains plays, skipping historical scan")
            return
    finally:
        db.close()

    processed_count = 0

    for guild in bot.guilds:
        print(f"🔎 Scanning guild: {guild.name}")

        for channel in guild.text_channels:
            try:
                await scan_channel(bot, channel, guild, processed_count)
            except discord.Forbidden:
                print(f"❌ No permission to read channel {channel.name}")
            except Exception as e:
                print(f"❌ Error scanning channel {channel.name}: {e}")

    print(f"✅ Historical scan complete! Processed {processed_count} messages")


async def scan_channel(bot: commands.Bot, channel, guild, processed_count):
    print(f"🔍 Scanning channel: {channel.name}")

    # Phase 1: Initial 7-day scan to see if there are any Wordle messages
    initial_scan_date = datetime.utcnow() - timedelta(days=7)
    found_wordle_messages = False

    async for message in channel.history(limit=500, after=initial_scan_date):
        if message.author.id == WORDLE_USER_ID:
            parsed = parse_wordle_message(message.content)
            if parsed:
                found_wordle_messages = True
                break

    if not found_wordle_messages:
        print(f"📭 No Wordle messages found in {channel.name} (last 7 days), skipping")
        return

    print(f"🎯 Found Wordle messages in {channel.name}, doing deep scan...")

    # Phase 2: Deep scan with gap detection
    days_without_wordle = 0
    current_scan_date = datetime.utcnow()
    max_gap_days = 30
    max_total_days = 365  # Don't scan more than 1 year back
    scan_batch_days = 7  # Scan in 7-day batches

    total_days_scanned = 0

    while days_without_wordle < max_gap_days and total_days_scanned < max_total_days:
        # Scan in batches
        batch_start = current_scan_date - timedelta(days=scan_batch_days)
        batch_end = current_scan_date

        batch_found_wordle = False
        batch_messages = []

        try:
            async for message in channel.history(
                limit=200, before=batch_end, after=batch_start
            ):
                if message.author.id == WORDLE_USER_ID:
                    parsed = parse_wordle_message(message.content)
                    if parsed:
                        batch_messages.append((message, parsed))
                        batch_found_wordle = True
        except Exception as e:
            print(f"❌ Error in batch scan: {e}")
            break

        # Process found messages
        for message, parsed in batch_messages:
            try:
                await save_results_to_db(guild.id, message.id, parsed)
                processed_count += 1
                print(
                    f"📈 Processed message {processed_count} from {message.created_at.strftime('%Y-%m-%d')}"
                )
            except Exception as e:
                print(f"❌ Error processing message: {e}")
                continue

            # Small delay to avoid rate limits
            await asyncio.sleep(0.05)

        # Update counters
        if batch_found_wordle:
            days_without_wordle = 0  # Reset gap counter
            print(f"✅ Found {len(batch_messages)} Wordle messages in batch")
        else:
            days_without_wordle += scan_batch_days
            print(
                f"📭 No Wordle messages in batch ({days_without_wordle} days without Wordle)"
            )

        total_days_scanned += scan_batch_days
        current_scan_date = batch_start

        # Progress update
        if total_days_scanned % 28 == 0:  # Every 4 weeks
            print(
                f"📊 Scanned {total_days_scanned} days back, {days_without_wordle} days since last Wordle"
            )

    if days_without_wordle >= max_gap_days:
        print(f"⏹️ Stopping scan for {channel.name} - {max_gap_days} day gap reached")
    elif total_days_scanned >= max_total_days:
        print(
            f"⏹️ Stopping scan for {channel.name} - {max_total_days} day limit reached"
        )
