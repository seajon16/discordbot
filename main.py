from discord import Game
from discord.ext import commands
from discord.errors import HTTPException
from random import choice
import logging
import logging.config
import asyncio
from websockets.exceptions import ConnectionClosedOK

from settings import get_settings
from exceptions import BananaCrime
from voicecontroller import VoiceController


settings_dict = get_settings()
logging.config.dictConfig(settings_dict["logging"])
LOGGER = logging.getLogger(__name__)
SHUTDOWN_MESSAGE = """Greetings, gamers.
The higher powers have issued a shutdown, therefore I shall now disappear.
Fret not, my friends, for I shall return."""

bot = commands.Bot(
    command_prefix='q.',
    description='Nifty bot that does things'
)
vccog = None

# Used to give error messages more personality
err_count = {}
banana_names = [
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
    "big stinky banana that evidently is the big banana and cannot type beep " \
        "boop bop on his/her keyboard like omg what's up with this guy lol xD"
]


async def check_err_count(ctx):
    """See if the author of the message is being a severe banana."""
    author = ctx.author
    if author in err_count:
        err_count[author] += 1
        newval = err_count[author]
        if newval == 3:
            await ctx.send("That's the third command in a row you messed up.")
        elif newval == 6:
            await ctx.send("You really aren't good at this.")
        elif newval >= 9 and not newval % 3:
            await ctx.send(
                f'Are you doing this on purpose, {author.mention}? '
                'What are you tring to gain, huh?'
            )
    else:
        err_count[author] = 1


@bot.event
async def on_command_error(ctx, ex):
    """Perform error handling, reporting (to the guilds), and logging."""
    await check_err_count(ctx)
    ex_type = type(ex)

    if ex_type == commands.errors.CommandNotFound:
        await ctx.send('Invalid command.')

    elif ex_type == commands.errors.MissingRequiredArgument:
        await ctx.send(
            'You did not specify the correct number of arguments. '
            'Try using `q.help {name of command}`.'
        )

    elif ex_type == commands.errors.CommandInvokeError \
        and type(ex.original) == BananaCrime:
        await ctx.send(f'{ex.original.crime}, you {choice(banana_names)}.')

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
        await ctx.send(ex.args[0])

    else:
        await ctx.send('what are you doing')
        LOGGER.error(
            f'Unexpected exception thrown ({type(ex).__name__}, {ex.args!r}) '
            'while handling a command:')
        raise ex


@bot.event
async def on_command_completion(ctx):
    """Update my list of error counts and praise people if need be."""
    author = ctx.author
    if author in err_count:
        if err_count[author] >= 9:
            await ctx.send(
                f'Attention Server: {author.mention} FINALLY knows how to act '
                'like a normal human being!'
            )
        del err_count[author]


@bot.event
async def on_command(ctx):
    """Log each command."""
    LOGGER.info(
        f'{ctx.message.author} in {ctx.guild}#{ctx.guild.id} '
        f'ran {ctx.message.content}'
    )


@bot.event
async def on_ready():
    """Report I'm ready to go."""
    LOGGER.info(f'Logged in as {bot.user}')
    await bot.change_presence(activity=Game('q.help'))


async def stop_and_cleanup():
    """Stop the bot and perform loop cleanup."""
    LOGGER.info('Stopping bot...')
    if vccog:
        results = await vccog.tell_active_guilds(SHUTDOWN_MESSAGE)
        for result in results:
            if result and result.exception() is not None:
                LOGGER.error(
                    'Unable to inform a guild of shutdown: '\
                    f'{type(err).__name__}, {err.args!r}'
                )
    await bot.logout()

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
            and not isinstance(task_ex, ConnectionClosedOK) \
            and not isinstance(task_ex, asyncio.CancelledError):
            LOGGER.error('Unexpected exception found during shutdown:')
            bot.loop.call_exception_handler({
                'message': 'Unexpected exception found during shutdown',
                'exception': task_ex,
                'task': task
            })

    LOGGER.debug('Shutting down async generators...')
    await bot.loop.shutdown_asyncgens()
    LOGGER.debug('Async generators shut down')

    bot.loop.stop()


try:
    LOGGER.info('Starting bot...')
    bot.loop.run_until_complete(bot.login(settings_dict['token']))

    bot.load_extension('utilities')
    vccog = VoiceController(bot)
    bot.add_cog(vccog)

    bot.loop.run_until_complete(bot.connect())

except KeyboardInterrupt:
    LOGGER.info('Caught a keyboard interrupt; triggering shutdown...')
except Exception:
    # NOTE: This exception isn't re-raised since it's logged
    #   and will trigger the bot's shutdown procedure
    LOGGER.critical(
        'Encountered the following unrecoverable top-level exception; '
        'stopping bot...',
        exc_info=True
    )

finally:
    bot.loop.run_until_complete(stop_and_cleanup())
    bot.loop.close()
    LOGGER.info("Bot stopped")
