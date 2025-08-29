from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.orm import Session

from wordle_discord_bot.utils.parsing import (
    WORDLE_USER_ID,
    parse_wordle_message,
    save_results_to_db,
    scan_historical_messages,
)

from ..database import GuildUserStats, WordlePlay, get_db


class WordleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._historical_scan_done = False

    async def cog_load(self):
        print("📊 Wordle Cog loaded")

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._historical_scan_done:
            await scan_historical_messages(self.bot)
            self._historical_scan_done = True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return

        # Check if message is from the specific user
        if message.author.id == WORDLE_USER_ID:
            print(f"📨 Message from Wordle user: {message.content[:100]}...")

            # Parse the message
            parsed_results = await parse_wordle_message(message.guild, message.content)

            if parsed_results:
                # Save to database
                try:
                    await save_results_to_db(
                        message.guild.id, message.id, message.created_at, parsed_results
                    )
                except Exception as e:
                    print(f"❌ Failed to save Wordle results: {e}")
            else:
                print("❌ Message doesn't match Wordle results pattern")

    @app_commands.command(
        name="wordle_stats", description="Show Wordle statistics for a user"
    )
    @app_commands.describe(
        days="Number of days back to include in leaderboard (optional)"
    )
    async def wordle_stats(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
        days: int | None = None,
    ):
        await interaction.response.defer()

        if not interaction.guild:
            await interaction.followup.send(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        target_user = user or interaction.user

        db: Session = next(get_db())
        try:
            # Determine cutoff date if days filter is provided
            cutoff_date = None
            if days is not None:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

            # Get user's plays
            query = db.query(WordlePlay).filter(
                WordlePlay.guild_id == interaction.guild.id,
                WordlePlay.discord_user_id == target_user.id,
            )

            if cutoff_date is not None:
                query = query.filter(WordlePlay.played_at >= cutoff_date)

            plays = query.all()

            if not plays:
                await interaction.followup.send(
                    f"No Wordle data found for {target_user.display_name}",
                    ephemeral=True,
                )
                return

            # Calculate stats
            total_plays = len(plays)
            successful_plays = [p for p in plays if p.guesses is not None]
            failed_plays = [p for p in plays if p.guesses is None]

            success_rate = (
                (len(successful_plays) / total_plays) * 100 if total_plays > 0 else 0
            )

            if successful_plays:
                avg_guesses = sum(
                    p.guesses for p in successful_plays if p.guesses
                ) / len(successful_plays)
                guess_distribution = {}
                for i in range(1, 7):
                    count = len([p for p in successful_plays if p.guesses == i])
                    guess_distribution[i] = count
            else:
                avg_guesses = 0
                guess_distribution = {}

            # Create embed
            embed = discord.Embed(
                title=f"📊 Wordle Stats for {target_user.display_name}",
                color=discord.Color.green(),
            )

            embed.add_field(name="Total Games", value=str(total_plays), inline=True)
            embed.add_field(name="Win Rate", value=f"{success_rate:.1f}%", inline=True)
            embed.add_field(
                name="Avg Guesses",
                value=f"{avg_guesses:.1f}" if avg_guesses > 0 else "N/A",
                inline=True,
            )

            MAX_BAR_LENGTH = 20

            if guess_distribution:
                dist_text = "\n".join(
                    [
                        f"{i}/6: {'█' * (count / MAX_BAR_LENGTH)} ({count})"
                        for i, count in guess_distribution.items()
                        if count > 0
                    ]
                )
                embed.add_field(
                    name="Guess Distribution",
                    value=dist_text or "No data",
                    inline=False,
                )

            embed.add_field(
                name="Failed Games", value=str(len(failed_plays)), inline=True
            )

            # Add user avatar
            embed.set_thumbnail(url=target_user.display_avatar.url)

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(
                f"Error retrieving stats: {e}", ephemeral=True
            )
        finally:
            db.close()

    @app_commands.command(
        name="wordle_leaderboard",
        description="Show the Wordle leaderboard for this server",
    )
    @app_commands.describe(
        days="Number of days back to include in leaderboard (optional)"
    )
    async def wordle_leaderboard(
        self, interaction: discord.Interaction, days: int | None = None
    ):
        await interaction.response.defer()

        if not interaction.guild:
            await interaction.followup.send(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        db: Session = next(get_db())
        try:
            # Determine cutoff date if days filter is provided
            cutoff_date = None
            if days is not None:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

            # Get all users with plays in this guild
            users_with_stats = (
                db.query(GuildUserStats.discord_user_id, GuildUserStats)
                .filter(GuildUserStats.guild_id == interaction.guild.id)
                .all()
            )

            leaderboard_data = []

            for user_id, user_stats in users_with_stats:
                # Filter plays by cutoff date if applicable
                plays = [
                    p
                    for p in user_stats.plays
                    if not cutoff_date or p.played_at >= cutoff_date
                ]
                if not plays:
                    continue

                total_plays = len(plays)
                successful_plays = [p for p in plays if p.guesses is not None]
                success_rate = (
                    (len(successful_plays) / total_plays) * 100
                    if total_plays > 0
                    else 0
                )
                avg_guesses = (
                    sum(p.guesses for p in successful_plays) / len(successful_plays)
                    if successful_plays
                    else 6.0
                )

                # Try to get Discord user
                try:
                    discord_user = interaction.guild.get_member(user_id)
                    display_name = (
                        discord_user.display_name if discord_user else f"User {user_id}"
                    )
                except:
                    display_name = f"User {user_id}"

                leaderboard_data.append(
                    {
                        "name": display_name,
                        "total_plays": total_plays,
                        "success_rate": success_rate,
                        "avg_guesses": avg_guesses,
                        "successful_plays": len(successful_plays),
                    }
                )

            if not leaderboard_data:
                await interaction.followup.send(
                    "No Wordle data found for this server!", ephemeral=True
                )
                return

            def leaderboard_score(user):
                avg = user["avg_guesses"]
                win_rate = user["success_rate"]
                wins = user["successful_plays"]

                smoothing = 5
                effective_avg = (avg * wins + 6 * smoothing) / (wins + smoothing)
                score = effective_avg - (win_rate / 100)

                return score

            leaderboard_data.sort(key=leaderboard_score)

            embed = discord.Embed(
                title="🏆 Wordle Leaderboard"
                + (f" (last {days} days)" if days else ""),
                color=discord.Color.gold(),
            )

            leaderboard_text = ""
            for i, data in enumerate(leaderboard_data[:10], 1):
                emoji = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
                leaderboard_text += f"{emoji} **{data['name']}**\n"
                leaderboard_text += f"   Win Rate: {data['success_rate']:.1f}% | Avg: {data['avg_guesses']:.1f} | Games: {data['total_plays']}\n\n"

            embed.description = leaderboard_text
            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(
                f"Error generating leaderboard: {e}", ephemeral=True
            )
        finally:
            db.close()

    @app_commands.command(
        name="rescan_wordle",
        description="Manually trigger a rescan of historical Wordle messages (Admin only)",
    )
    @app_commands.default_permissions(administrator=True)
    async def rescan_wordle(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        await interaction.followup.send("🔄 Starting manual rescan...")
        await scan_historical_messages(self.bot, True)
        await interaction.followup.send("✅ Rescan completed!")


async def setup(bot: commands.Bot, TEST_GUILD_ID=None):
    cog = WordleCog(bot)
    await bot.add_cog(cog)

    if TEST_GUILD_ID:
        guild = discord.Object(id=TEST_GUILD_ID)
        bot.tree.add_command(cog.wordle_stats, guild=guild)
        bot.tree.add_command(cog.wordle_leaderboard, guild=guild)
        bot.tree.add_command(cog.rescan_wordle, guild=guild)
        await bot.tree.sync(guild=guild)

    print("✅ Wordle cog setup complete")
