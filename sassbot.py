import asyncio
from discord import Game
from discord.ext import commands
from discord.errors import HTTPException
from random import choice
import signal
import logging
from websockets.exceptions import ConnectionClosedOK

from exceptions import BananaCrime
from voicecontroller import VoiceController
from guilddb import GuildDB


# Defaults
DEFAULT_ACTIVE_TIMEOUT_CHECK_INTERVAL_S = 60
DEFAULT_ACTIVE_TIMEOUT_M = 30

LOGGER = logging.getLogger(__name__)


class SassBot(commands.Bot):
    """Base bot class that sets up cogs/extensions and tracks guild info.

    Specifically regarding guild info, tracks guild-specific settings and
        session-related information using a SQLite DB.

    Args:
        token (str): Token to use to log in to Discord.
        active_timeout_check_interval_s (int, Optional): The number of seconds
            between each time the bot checks for inactive sessions.
        active_timeout_m (int, Optional): The number of minutes of inactivity
            before the bot's session becomes inactive and will therefore not
            send shutdown messages and will disconnect from any voice channels.
        voice_settings (dict, Optional): Settings to initialize VoiceController
    """

    # Used to give error messages more personality
    BANANA_NAMES = [
        'banana',
        'bafoon',
        'dingus',
        'horse',
        'fool',
        'crook',
        'fiend',
        'doofus',
        'goose',
        'oaf',
        "big stinky banana that evidently is the big banana and cannot type "
            "beep boop bop on his/her keyboard like omg what's up with this "
            "guy lol xD"
    ]
    # Message sent to all guilds with an active voice connection upon shutdown
    SHUTDOWN_MESSAGE = "Greetings, gamers. The higher powers have issued a " \
        "shutdown, therefore I shall now disappear. Fret not, my friends, " \
        "for I shall return."

    def __init__(self, **kwargs):
        # Grab & remove settings base class doesn't need
        self.parse_kwargs(kwargs)

        # Used for error customization
        self.err_count = {}
        # Manages additional per-guild info
        self.guild_db = GuildDB()

        super().__init__(**kwargs)

        self.load_extension('utilities')
        self.voice_controller = VoiceController(self, **self.voice_settings)
        self.add_cog(self.voice_controller)

    def parse_kwargs(self, kwargs):
        """Helper to parse kwargs and set defaults."""
        if 'token' not in kwargs:
            raise KeyError('You must specify a Discord auth token')

        self.active_timeout_check_interval_s = kwargs.pop(
            'active_timeout_check_interval_s',
            DEFAULT_ACTIVE_TIMEOUT_CHECK_INTERVAL_S
        )
        self.active_timeout_m = kwargs.pop(
            'active_timeout_m', DEFAULT_ACTIVE_TIMEOUT_M
        )
        self._token = kwargs.pop('token')
        self.voice_settings = kwargs.pop('voice_settings', dict())

    # Running/Stopping #
    def _sigint_handler(self):
        """SIGINT handler that, when triggered, stops the bot.

        This is simply close() but with an additional log message.
        """
        LOGGER.info('Caught SIGINT')
        self.loop.create_task(self.close())

    def run(self):
        """Start bot, keeping control within this object.

        Control will cease on SIGINT or an unrecoverable exception.
        """
        self.loop.add_signal_handler(
            signal.SIGINT, lambda: self._sigint_handler()
        )
        try:
            LOGGER.info('Starting bot...')
            self.loop.run_until_complete(self._prepare_to_serve())

            self.loop.run_until_complete(self.connect())
        except Exception:
            # NOTE: This exception isn't re-raised since it's logged
            #   and will trigger the bot's shutdown procedure
            LOGGER.critical(
                'Encountered the following unrecoverable top-level exception; '
                'stopping bot...',
                exc_info=True
            )
            self.loop.run_until_complete(self.close())
        finally:
            LOGGER.info('Bot stopped')
            self.loop.close()

    async def _prepare_to_serve(self):
        """Connect to Discord and initialize objects that need the data.

        NOTE: By default, database will be populated with at most 100 guilds.
        """
        await self.login(self._token)
        async for guild in self.fetch_guilds():
            self.guild_db.add_guild(guild)

        # Start checking for inactive voice clients
        self.inactivity_task = self.loop.create_task(self.inactivity_checker())

    async def close(self):
        """Stop the bot."""
        LOGGER.info('Stopping bot...')
        await self.tell_active_guilds(self.SHUTDOWN_MESSAGE)
        self.inactivity_task.cancel()
        await self.voice_controller.close()

        await super().close()

        tasks = [
            task for task in asyncio.all_tasks()
            if task is not asyncio.current_task()
        ]
        LOGGER.debug('Cancelling all tasks...')
        for task in tasks:
            LOGGER.debug(f'Cancelling {task}')
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        LOGGER.debug('All tasks cancelled')

        for task in tasks:
            if task.cancelled():
                continue
            task_ex = task.exception()
            # Ignore normal socket closures and uncaught cancels
            if task_ex is not None \
                    and not isinstance(task_ex, ConnectionClosedOK):
                LOGGER.error('Unexpected exception found during shutdown:')
                self.loop.call_exception_handler({
                    'message': 'Unexpected exception found during shutdown',
                    'exception': task_ex,
                    'task': task
                })

        LOGGER.debug('Shutting down async generators...')
        await self.loop.shutdown_asyncgens()
        LOGGER.debug('Async generators shut down')

        self.loop.stop()

    # Guild-record-related #
    async def tell_active_guilds(self, msg):
        """Send a message to all guilds with an active voice client."""
        tgt_channels = [
            record.last_channel for record in self.guild_records.values()
            if record.is_active and record.last_channel
        ]
        msg_coros = [
            channel.send(msg) for channel in tgt_channels
        ]
        results = await asyncio.gather(*msg_coros, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                LOGGER.error(
                    'Unable to message a guild: '\
                    f'{type(result).__name__}, {result.args!r}'
                )

    async def handle_crit(self, msg):
        """DMs my owner saying I just fired a crit."""
        if self.owner_id:
            owner = self.get_user(self.owner_id) \
                or await self.fetch_user(self.owner_id)
        else:
            owner = (await self.application_info()).owner
        if not owner:
            LOGGER.error(f'Could not find owner with ID {self.owner_id}')
            return

        tgt_channel = owner.dm_channel or await owner.create_dm()
        if not tgt_channel:
            LOGGER.error(
                f'Could not create DM channel with owner ID {self.owner_id}'
            )
            return
        await tgt_channel.send(
            'Hello, you garbage programmer. '
            f'I just fired a crit with this message:\n{msg}'
        )

    @property
    def guild_records(self):
        """All guild records."""
        # This is just a convenience wrapper
        return self.guild_db.records

    async def inactivity_checker(self):
        """Periodic task that removes inactive voice connections."""
        try:
            while True:
                for record in self.guild_db.records.values():
                    # Tell the voice controller to check it
                    await self.voice_controller.check_record_for_inactivity(
                        record
                    )

                await asyncio.sleep(self.active_timeout_check_interval_s)

        except asyncio.CancelledError:
            LOGGER.debug('Inactivity checking task was cancelled')
        except Exception:
            # NOTE: This exception isn't re-raised since it gets logged
            #   and already stopped/"finished" the task; if we raised it again,
            #   discord.py's main handler would report it again unless we made a
            #   custom canceller/reaper
            LOGGER.critical('Inactivity checking task failed:', exc_info=True)
            await self.handle_crit('Inactivity checking task failed')

    # Event overriders #
    async def check_err_count(self, ctx):
        """See if the author of the message is being a severe banana."""
        author = ctx.author
        if author in self.err_count:
            self.err_count[author] += 1
            newval = self.err_count[author]
            if newval == 3:
                await ctx.send(
                    "That's the third command in a row you messed up."
                )
            elif newval == 6:
                await ctx.send("You really aren't good at this.")
            elif newval >= 9 and not newval % 3:
                await ctx.send(
                    f'Are you doing this on purpose, {author.mention}? '
                    'What are you trying to gain, huh?'
                )
        else:
            self.err_count[author] = 1

    async def on_command_error(self, ctx, ex):
        """Perform error handling, reporting (to the guilds), and logging."""
        await self.check_err_count(ctx)
        ex_type = type(ex)

        if ex_type == commands.errors.CommandNotFound:
            await ctx.send('Invalid command.')

        elif ex_type == commands.errors.MissingRequiredArgument:
            await ctx.send(
                'You did not specify the correct number of arguments. '
                f'Try running `{self.command_prefix}help {ctx.command.name}`, '
                f'you {choice(self.BANANA_NAMES)}.'
            )

        elif ex_type == commands.errors.CommandInvokeError \
            and type(ex.original) == BananaCrime:
            await ctx.send(
                f'{ex.original.crime}, you {choice(self.BANANA_NAMES)}.'
            )

        elif ex_type == commands.errors.CommandInvokeError \
            and type(ex.original) == HTTPException:
            await ctx.send(
                'You just managed to give me a command that made Discord angry.'
            )
            LOGGER.error(
                f'Running {ctx.message.content} caused an HTTPException '
                f'({type(ex).__name__}, {ex.args!r}):'
            )
            raise ex

        elif ex_type == commands.errors.NotOwner:
            await ctx.send("You aren't my owner, you banana.")

        elif ex_type == commands.errors.BadArgument:
            await ctx.send(
                f'{ex.args[0]} '
                f'Try running `{self.command_prefix}help {ctx.command.name}`, '
                f'you {choice(self.BANANA_NAMES)}.'
            )

        elif ex_type == commands.errors.UnexpectedQuoteError:
            await ctx.send(
                "If you include a quote in an argument, you'll either need to "
                "fully encase what you're trying to send me in quotes, or you "
                f"need to escape it, you {choice(self.BANANA_NAMES)}."
            )

        elif ex_type == commands.errors.InvalidEndOfQuotedStringError:
            await ctx.send(
                "You cannot place a character directly after the end of a "
                f"quoted string, you {choice(self.BANANA_NAMES)}."
            )

        elif ex_type == commands.errors.ExpectedClosingQuoteError:
            await ctx.send(
                "You did not complete your quoted string, "
                f"you {choice(self.BANANA_NAMES)}."
            )

        elif ex_type == commands.errors.ChannelNotFound:
            await ctx.send(
                "That channel doesn't exist; make sure to match casing "
                "and encase the channel name in quotes if it has spaces in it, "
                f"you {choice(self.BANANA_NAMES)}."
            )

        else:
            await ctx.send('what are you doing')
            LOGGER.error(
                'Unexpected exception thrown while handling a command:',
                exc_info=ex
            )

    async def on_command_completion(self, ctx):
        """Update my list of error counts and praise people if need be."""
        author = ctx.author
        if author in self.err_count:
            if self.err_count[author] >= 9:
                await ctx.send(
                    f'Attention Server: {author.mention} FINALLY knows how to '
                    'act like a normal human being!'
                )
            del self.err_count[author]

    async def on_command(self, ctx):
        """Log each command and refresh our last channel record."""
        LOGGER.info(
            f'{ctx.message.author} in {ctx.guild}#{ctx.guild.id} '
            f'ran {ctx.message.content}'
        )
        self.guild_db.update_record(ctx)

    async def on_ready(self):
        """Report I'm ready to go."""
        LOGGER.info(f'Logged in as {self.user}')
        await self.change_presence(activity=Game(f'{self.command_prefix}help'))

    async def on_guild_join(self, guild):
        """Update records when I'm added to a guild."""
        self.guild_db.add_guild(guild)
