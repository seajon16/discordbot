import discord
from discord.ext import commands
import random
import music
import aioconsole
import time

'''
Runs the bot.

TODO:
    Change guessing game to operate across multiple servers
'''

# Initialize music.py
bot = commands.Bot(command_prefix=commands.when_mentioned_or('q.'),
                   description='Nifty bot that does things.')
music_cog = music.Music(bot)
bot.add_cog(music_cog)

# Users with special privileges (spamming, iscool)
admins = {
    '383053603046424597': 'QuackAttack',
    '183751265975664640': 'Quesosity'
}
# Used in on_voice_state_update() to play join sounds when particular users join
# Maps user ids to the full path of the desired sound
join_sounds = {
    '183751265975664640': 'sounds/reaction/crimsonchin.mp3',  # me
}
# Who is playing the guessing game; this user's name as a string
playing_guessing_game = None
# The answer to the current guessing game
guessing_answer = 0

# Token obtained from discord that is used to launch the bot
bot_token = [INSERT TOKEN HERE]


# Define event-dependent functions
@bot.event
async def on_ready():
    ''' Sends a message to the console confirming login. '''
    print('Logged in as:\n{0} (ID: {0.id})'.format(bot.user))
    await bot.change_presence(game=discord.Game(name='q.help'))


""" # Remove comment to allow
@bot.event
async def on_voice_state_update(before, after):
    '''
    Monitors server, watching for users connecting to voice channels.
    Upon connection, plays a join sound depending on join_sounds in the joined channel.
    '''
    if before.id in join_sounds and before.voice_channel is None \
                                and after.voice_channel is not None:
        sound = join_sounds[after.id]
        await music_cog.play_join_sound(after.server, after.voice_channel, sound)
"""


# Define commands
@bot.command()
async def ping():
    ''' Tests connection. '''
    await bot.say('quack')


@bot.command()
async def roll(desire: str=None):
    ''' Handles a roll in the form (A)dB(+C-D...). '''
    # No params given, or roll is lacking a d
    if desire is None:
        await bot.say("Standard form using integers, d, +, and - (i.e. 2d4+2-1 rolls 2 d4's and adds 1).")
        return
    desre = desire.lower()
    if 'd' not in desire:
        await bot.say('A d is required (i.e. 2d6).')
        return

    # Break roll into left and right portions
    left, right = desire.split('d', 1)

    times = handle_left(left)

    # If the number of rolls was invalid
    if not times:
        await bot.say('The portion to the left of the d is invalid; must be an integer.')
        return

    # Get the left-most/first number of the right-hand side, which is our type
    #     of die, and get the sum of the +4-3+2... portion
    first_num, additional_sum = handle_right(right)

    # If user gave something like d+4+1, where a "+4" die does not exist
    if not first_num.isdigit():
        await bot.say('The portion to the right of the d is invalid; a {}-sided die does not exist.'
                      .format(first_num))
        return

    # Now that I confirmed the die type is a valid integer, cast it
    die_type = int(first_num)
    # Start off my result with whatever additional numbers the user gave me, if any
    result = additional_sum
    # Used to print what each roll ended up being, as well as the found sum
    to_display = ''

    # Roll a die_type-sided die times times
    for _ in range(times):
        curr_roll =  random.randint(1, die_type)
        to_display += '{} + '.format(curr_roll)
        result += curr_roll

    to_display += '({})'.format(additional_sum)
    await bot.say('{0} gave {1} = {2}'.format(desire, to_display, result))


@bot.group(pass_context=True)
async def iscool(ctx, person: discord.Member=None):
    ''' Determines if @User is cool. '''
    if person is None:
        output = ctx.message.author.name
        await bot.say(output + ' is not, since he/she failed to include an argument.')
    elif person.id in admins:
        await bot.say(person.display_name + ' is indeed cool.')
    else:
        await bot.say(person.display_name + ' is not cool.')


@bot.group(pass_context=True)
async def guessinggame(ctx, guess=0):
    ''' Starts a guessing game; use q.guessinggame [guess] to guess. '''
    global playing_guessing_game, guessing_answer

    if playing_guessing_game is None:
        playing_guessing_game = ctx.message.author.name
        guessing_answer = random.randint(1, 10)
        await bot.say("Ok, {}. I'm thinking of a number between 1 and 10. What is it?"
                      .format(playing_guessing_game))

    elif playing_guessing_game is ctx.message.author.name:
        if int(guess) is guessing_answer:
            await bot.say(playing_guessing_game + " correctly guessed the number.")
            playing_guessing_game = None
        else:
            await bot.say('Wrong, try again.')

    else:
        await bot.say('Someone else is playing, hold your horses.')


@bot.command()
async def add(*numbers):
    ''' Adds a bunch of numbers together. '''
    if len(numbers) < 2:
        await bot.say('I need at least two numbers, you bafoon.')
    else:
        total = 0
        for x in numbers:
            total += int(x)
        await bot.say(str(total))


@bot.group(pass_context=True)
async def mspam(ctx, times=None, *message):
    ''' Sends a message n times (must be an admin). '''
    if not times:
        await bot.say('0 times? lol')
    elif not ctx.message.author.id in admins:
        await bot.say("You aren't cool enough to use that command.")
    else:
        desire = ''
        for word in message:
            desire += word + ' '
        for _ in range(int(times)):
            await bot.say(desire)
            time.sleep(0.1)


@bot.group(pass_context=True)
async def lspam(ctx, times=None, *message):
    ''' Sends a single message composed of the desired messsage copied n times (must be an admin). '''
    if not times:
        await bot.say('0 times? lol')
    elif not ctx.message.author.id in admins:
        await bot.say("You aren't cool enough to use that command.")
    else:
        desire = ''
        for word in message:
            desire += word + ' '
        to_send = ''
        for _ in range(int(times)):
            to_send += desire + '\n'
        await bot.say(to_send)


@bot.command()
async def choice(*choices):
    ''' Picks a random option from a given list of choices. '''
    if len(choices) == 0:
        response = 'I need a list of choices.'
    elif len(choices) == 1:
        response = choices[0] + ', you sneaky rapscallion.'
    else:
        entry_num = random.randint(0, len(choices) - 1)
        response = choices[entry_num]
    await bot.say(response)


# Helpers for dice roller
def reverse_string(a_string):
    '''
    Generator which traverses a given string backwards.
    Mainly did this because I can, and Python is cool.
    Params:
        str a_string: the string to be traversed
    Yields:
        str: each character in the given string in reverse order
    '''
    curr_pos = len(a_string) - 1

    while curr_pos >= 0:
        yield a_string[curr_pos]
        curr_pos -= 1

def handle_left(left):
    '''
    Given a string to the left of a d, determine what the user desires, if valid.
    Params:
        str left: the string to the left of a d
    Returns:
        int: the number of times the die shall be rolled; 0 if input was invalid
    '''
    # If the user gave me nothing to the left of the d, then they implied 1
    if not left:
        return 1
    elif not left.isdigit():
        # So I can be lazy with truthiness
        return 0
    # Otherwise, use what I was given
    return int(left)

def handle_right(right):
    '''
    Given a string to the right of a d, convert it into the left-most number/characters
        and the sum of the digits afterwards (i.e. +4-3+2). Ignores other characters.
    Params:
        str right: the string to the right of a d to be examined
    Returns:
        str: the left-most sequence of characters; may or may not be a digit
        int: the sum of all numbers to the right of the previous 
    '''
    curr_num = ''
    curr_sum = 0

    for c in reverse_string(right):
        # If the current character is a number, then remember it
        if c.isdigit():
            curr_num = c + curr_num
        elif c == '+':
            # Increment my sum by the number and reset the number
            curr_sum += int(curr_num)
            curr_num = ''
        elif c == '-':
            # Decrement my sum by the number and reset the number
            curr_sum -= int(curr_num)
            curr_num = ''

    return curr_num, curr_sum


# Start the bot
bot.run(bot_token)
