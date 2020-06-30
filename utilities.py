from discord.ext import commands
import random
from aiohttp import ClientSession

from exceptions import BananaCrime


@commands.command(aliases=('ping',))
async def howyoudoin(ctx):
    """how am i doin"""
    await ctx.send('we vibin')


@commands.command()
async def roll(ctx, desire=None):
    """Handles a dice roll in the form (A)dB(+C-D...)."""
    if not desire:
        raise BananaCrime(
            "Standard form using integers, d, +, and - "
            "(i.e. `q.roll 2d4+2-1` rolls 2 d4's and adds 1)"
        )
    desire = desire.lower()
    if 'd' not in desire:
        raise BananaCrime('A d is required (i.e. `2d6`)')

    count_raw, modifiers = desire.split('d', 1)

    if count_raw and not count_raw.isdigit():
        raise BananaCrime('Invalid number of times to roll')
    count = int(count_raw) if count_raw else 1

    curr_num = ''
    curr_sum = 0
    for c in reversed(modifiers):
        if c.isdigit():
            curr_num = c + curr_num
        elif c == '+':
            curr_sum += int(curr_num)
            curr_num = ''
        elif c == '-':
            curr_sum -= int(curr_num)
            curr_num = ''
        else:
            raise BananaCrime('Invalid format to the right of the `d`')
    if not curr_num:
        raise BananaCrime('Invalid format to the right of the `d`')

    rolls = [random.randint(1, int(curr_num)) for _ in range(count)]
    str_rolls = " + ".join(str(roll) for roll in rolls)
    result = sum(rolls) + curr_sum
    await ctx.send(f'`{desire}` gave {str_rolls} *+ {curr_sum}* = **{result}**')


@commands.command()
async def choose(ctx, *choices):
    """Picks a random option from a given list of choices."""
    if not len(choices):
        raise BananaCrime('I need a list of choices')
    elif len(choices) == 1:
        ctx.send(f'`{choices[0]}`, you sneaky rapscallion.')
    else:
        entry_num = random.randint(0, len(choices) - 1)
        await ctx.send(
            f'`{choices[entry_num]}` all the way.' if entry_num % 2
            else f"I'm feelin `{choices[entry_num]}`."
        )


@commands.command()
async def fact(ctx):
    """Gives a random fact."""
    url = 'https://uselessfacts.jsph.pl/random.json?language=en'
    async with ClientSession() as session:
        resp = await session.request(method="GET", url=url)
    resp.raise_for_status()
    body = await resp.json()
    await ctx.send(body['text'])


@commands.command()
@commands.is_owner()
async def shutdown(ctx):
    """Gracefully shuts down the bot; must be my owner."""
    await ctx.send('okey dokey')
    await ctx.bot.logout()


def setup(bot):
    callbacks = [
        howyoudoin,
        roll,
        choose,
        fact,
        shutdown
    ]
    for callback in callbacks:
        bot.add_command(callback)
