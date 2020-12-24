import asyncio
from datetime import datetime, timedelta


DEFAULT_ACTIVE_TIMEOUT_M = 30


class GuildRecord:
    """Represents additional per-guild information like settings & VCs.

    Specifically:
        1. The last channel a voice-related command was executed & when
        2. The Lock used by that guild to prevent spam-based issues
    """

    # How many minutes to wait before marking a guild as inactive
    active_timeout_m = DEFAULT_ACTIVE_TIMEOUT_M

    def __init__(self, orig_guild):
        self.guild = orig_guild
        self.last_channel = None
        self.last_dt = None
        self.lock = asyncio.Lock()
        self.searching_ytdl = False

    @property
    def is_active(self):
        """Return if the guild is active."""
        # If we still have a last_dt set, we haven't timed out this record
        return self.last_dt is not None

    @property
    def should_timeout(self):
        """Return if the guild should be timed out."""
        return (
            self.last_dt + timedelta(minutes=self.active_timeout_m)
                < datetime.now()
            if self.last_dt else False
        )

    def mark_inactive(self):
        """Officially mark the guild as inactive."""
        self.last_dt = None

    def update(self, last_channel=None):
        """Update the object by recording the new most recent command."""
        self.last_channel = last_channel or self.last_channel
        self.last_dt = datetime.now()

    async def send(self, msg):
        """Send a message to my last channel if I have one, else do nothing."""
        if self.last_channel:
            await self.last_channel.send(msg)


class GuildDB:
    """Holds and retrieves all additional per-guild information.

    Maps guild IDs to GuildRecords.
    """

    def __init__(self, guilds=None, active_timeout_m=None):
        if active_timeout_m:
            GuildRecord.active_timeout_m = active_timeout_m
        if guilds:
            self.records = {guild.id: GuildRecord(guild) for guild in guilds}
        else:
            self.records = {}

    def add_guild(self, guild):
        self.records[guild.id] = GuildRecord(guild)

    def update_record(self, ctx):
        self.records[ctx.guild.id].update(ctx.channel)

    @property
    def guilds_records_to_timeout(self):
        """Return guild records that should be timed out."""
        return [gr for gr in self.records.values() if gr.should_timeout]
