from discord import Game
from discord.ext import commands
from random import choice

from settings import get_settings
from exceptions import BananaCrime
from voicecontroller import VoiceController


bot = commands.Bot(
    command_prefix='q.',
    description='Nifty bot that does things'
)

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
    author = ctx.author
    if author in err_count:
        err_count[author] += 1
        newval = err_count[author]
        if newval == 3:
            await ctx.send(
                "That's the third command in a row you messed up."
            )
        elif newval == 6:
            await ctx.send(
                "You really aren't good at this."
            )
        elif newval >= 9 and not newval % 3:
            await ctx.send(
                f'Are you doing this on purpose, {author.mention}? '
                'What are you tring to gain, huh?'
            )
    else:
        err_count[author] = 1


@bot.event
async def on_command_error(ctx, ex):
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
        await ctx.send(
            f'{ex.original.crime}, you {choice(banana_names)}.'
        )

    elif ex_type == commands.errors.NotOwner:
        await ctx.send("you aren't jon, you banana")

    elif ex_type == commands.errors.BadArgument:
        await ctx.send(ex.args[0])

    else:
        await ctx.send('what are you doing')
        raise ex


@bot.event
async def on_command_completion(ctx):
    author = ctx.author
    if author in err_count:
        if err_count[author] >= 9:
            await ctx.send(
                f'Attention Server: {author.mention} FINALLY knows how to act '
                'like a normal human being!'
            )
        del err_count[author]


@bot.event
async def on_ready():
    print('Logged in as', bot.user)
    await bot.change_presence(activity=Game('q.help'))


token = get_settings()['token']
bot.load_extension('utilities')
bot.add_cog(VoiceController(bot))
bot.run(token)
