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
optional: TEST_GUILD_ID=[guild id, allows for realtime slash command updates. use if they're not updating]
```

and run `mise run setup`

### running

`mise run dev`
