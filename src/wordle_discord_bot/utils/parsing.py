import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

import discord
from discord.ext import commands

from ..database import GuildUserStats, SessionLocal, WordlePlay

WORDLE_USER_ID = 1211781489931452447


@dataclass
class WordleResult:
    user_id: int | None
    username_at_time: str | None
    guesses: Optional[int]
    is_crown: bool


@dataclass
class ParsedWordleMessage:
    streak_days: int
    results: List[WordleResult]


async def parse_wordle_message(
    guild: discord.Guild, content: str
) -> Optional[ParsedWordleMessage]:
    streak_pattern = r"\*\*Your group is on a (\d+) day streak!\*\* 🔥+ Here are yesterday's results:"
    streak_match = re.search(streak_pattern, content)
    if not streak_match:
        return None

    streak_days = int(streak_match.group(1))

    results: List[WordleResult] = []

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue

        match = re.search(r"(\d|X)/6:\s*(.+)", line)
        if match:
            score_str, mentions_str = match.groups()
            guesses = None if score_str == "X" else int(score_str)

            user_ids = re.findall(r"<@(\d+)>", mentions_str)

            for user_id in user_ids:
                user = guild.get_member(int(user_id))  # fast cache lookup
                if not user:
                    try:
                        user = await guild.fetch_member(int(user_id))  # API fallback
                    except discord.NotFound:
                        # user doesn't exist anymore. Oh well.
                        pass

                if user:
                    user_name = user.nick or user.global_name or user.name
                else:
                    user_name = None

                results.append(
                    WordleResult(
                        user_id=int(user_id),
                        username_at_time=user_name,
                        guesses=guesses,
                        is_crown="👑" in line,
                    )
                )

            # sometimes the bot doesnt ping properly.
            fail_ping_user_names = re.findall(
                r"(?<!<)@([^\s@]+(?: [^\s@@<]+)*)", mentions_str
            )

            for user_name in fail_ping_user_names:
                results.append(
                    WordleResult(
                        user_id=None,
                        username_at_time=user_name,
                        guesses=guesses,
                        is_crown="👑" in line,
                    )
                )

    if not results:
        return None

    return ParsedWordleMessage(streak_days=streak_days, results=results)


async def save_results_to_db(
    guild_id: int,
    message_id: int,
    message_date: datetime,
    parsed_results: ParsedWordleMessage,
):
    db = SessionLocal()
    try:
        for result in parsed_results.results:
            user_id = result.user_id

            # if no user_id, attempt to find it by username in nearby entries
            # fixes when the wordle bot doesnt ping users properly. hacky.
            if not user_id and result.username_at_time:
                print(
                    f"!! no userid & username ({result.username_at_time})... searching surroundings"
                )
                # Look for previous or future plays within, e.g., ±7 days
                time_window_start = datetime.utcnow() - timedelta(days=7)
                time_window_end = datetime.utcnow() + timedelta(days=7)

                matching_play = (
                    db.query(WordlePlay)
                    .filter(
                        WordlePlay.guild_id == guild_id,
                        WordlePlay.discord_user_name_at_time == result.username_at_time,
                        WordlePlay.played_at.between(
                            time_window_start, time_window_end
                        ),
                        WordlePlay.discord_user_id.isnot(None),
                    )
                    .first()
                )

                if matching_play:
                    user_id = matching_play.discord_user_id
                    print(
                        f"!! matched {result.username_at_time} to {matching_play.discord_user_name_at_time} (userid: {matching_play.discord_user_id})"
                    )

                else:
                    print(
                        f"⚠️ Could not match user for username '{result.username_at_time}' in guild {guild_id}"
                    )

            if user_id:
                # Ensure there is a user record
                existing_user = (
                    db.query(GuildUserStats)
                    .filter(
                        GuildUserStats.guild_id == guild_id,
                        GuildUserStats.discord_user_id == user_id,
                    )
                    .first()
                )

                if not existing_user and user_id:
                    new_user = GuildUserStats(
                        guild_id=guild_id,
                        discord_user_id=user_id,
                    )
                    db.add(new_user)
                    db.commit()

                # Save the play
                existing_play = (
                    db.query(WordlePlay)
                    .filter(
                        WordlePlay.guild_id == guild_id,
                        WordlePlay.discord_user_id == user_id,
                        WordlePlay.stats_discord_message_id == message_id,
                    )
                    .first()
                )

                if not existing_play:
                    new_play = WordlePlay(
                        guild_id=guild_id,
                        discord_user_id=user_id,
                        stats_discord_message_id=message_id,
                        discord_user_name_at_time=result.username_at_time,
                        guesses=result.guesses,
                        played_at=message_date,  # TODO: idk if this handles timezones properly
                    )
                    db.add(new_play)

                db.commit()
        print(f"✅ Saved {len(parsed_results.results)} Wordle results to database")

    except Exception as e:
        db.rollback()
        print(f"❌ Error saving to database: {e}")
        raise
    finally:
        db.close()


async def scan_historical_messages(bot: commands.Bot, force: bool = False):
    print("🔍 Starting historical scan for Wordle messages...")

    if not force:
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
                processed_count = await scan_channel(
                    bot, channel, guild, processed_count
                )
            except discord.Forbidden:
                print(f"❌ No permission to read channel {channel.name}")
            except Exception as e:
                print(f"❌ Error scanning channel {channel.name}: {e}")

    print(f"✅ Historical scan complete! Processed {processed_count} messages")


async def scan_channel(
    bot: commands.Bot,
    channel: discord.TextChannel,
    guild: discord.Guild,
    processed_count: int,
) -> int:
    print(f"🔍 Scanning channel: {channel.name}")

    # Phase 1: Initial 7-day scan to see if there are any Wordle messages
    initial_scan_date = datetime.utcnow() - timedelta(days=7)
    found_wordle_messages = False

    async for message in channel.history(limit=500, after=initial_scan_date):
        if message.author.id == WORDLE_USER_ID:
            parsed = await parse_wordle_message(guild, message.content)
            if parsed:
                found_wordle_messages = True
                break

    if not found_wordle_messages:
        print(f"📭 No Wordle messages found in {channel.name} (last 7 days), skipping")
        return processed_count

    print(f"🎯 Found Wordle messages in {channel.name}, doing deep scan...")

    # Phase 2: Deep scan with gap detection
    days_without_wordle = 0
    current_scan_date = datetime.utcnow()
    max_gap_days = 30
    scan_batch_days = 7  # Scan in 7-day batches
    total_days_scanned = 0

    while days_without_wordle < max_gap_days:
        batch_start = current_scan_date - timedelta(days=scan_batch_days)
        batch_end = current_scan_date

        batch_found_wordle = False
        batch_messages = []

        try:
            async for message in channel.history(
                limit=200, before=batch_end, after=batch_start
            ):
                if message.author.id == WORDLE_USER_ID:
                    parsed = await parse_wordle_message(guild, message.content)
                    if parsed:
                        batch_messages.append((message, parsed))
                        batch_found_wordle = True
        except Exception as e:
            print(f"❌ Error in batch scan: {e}")
            break

        for message, parsed in batch_messages:
            try:
                await save_results_to_db(
                    guild.id, message.id, message.created_at, parsed
                )
                processed_count += 1
                print(
                    f"📈 Processed message {processed_count} from {message.created_at.strftime('%Y-%m-%d')}"
                )
            except Exception as e:
                print(f"❌ Error processing message: {e}")
                continue
            await asyncio.sleep(0.05)

        if batch_found_wordle:
            days_without_wordle = 0
            print(f"✅ Found {len(batch_messages)} Wordle messages in batch")
        else:
            days_without_wordle += scan_batch_days
            print(
                f"📭 No Wordle messages in batch ({days_without_wordle} days without Wordle)"
            )

        total_days_scanned += scan_batch_days
        current_scan_date = batch_start

        if total_days_scanned % 28 == 0:  # Every 4 weeks
            print(
                f"📊 Scanned {total_days_scanned} days back, {days_without_wordle} days since last Wordle"
            )

    if days_without_wordle >= max_gap_days:
        print(f"⏹️ Stopping scan for {channel.name} - {max_gap_days} day gap reached")

    return processed_count
