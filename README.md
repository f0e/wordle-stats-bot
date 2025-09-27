# wordle stats

Parses scores from the official Wordle Discord bot and provides commands to view you & your friends' stats.

## commands

- /wordle_leaderboard
- /wordle_stats [user]
- (admin-only) /rescan_wordle

## dev setup

### requirements

- mise
- a postgres db somewhere

### setup

create `.env` and fill out

```
DISCORD_TOKEN=[discord bot token]
DATABASE_URL=postgresql://...
optional: BOT_OWNER_ID=[owner id, enables permissions for /sync to sync slash commands manually]
optional: BOT_HOME_GUILD_ID=[home server id, always syncs /sync command]
```

and run `mise run setup`

### running

`mise run dev`
