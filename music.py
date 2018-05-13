import asyncio
import discord
from discord import *
from discord.ext import commands
import random
import os
from gtts import gTTS
from pydub import AudioSegment

'''
Controls all voice-related functionality of the bot.
'''

if not discord.opus.is_loaded():
    # the 'opus' library here is opus.dll on windows
    # or libopus.so on linux in the current directory
    # you should replace this with the location the
    # opus library is located in and with the proper filename.
    # note that on windows this DLL is automatically provided for you
    discord.opus.load_opus('opus')


class VoiceEntry:
    def __init__(self, message, player):
        self.requester = message.author
        self.channel = message.channel
        self.player = player

    def __str__(self):
        fmt = '*{0.title}* uploaded by {0.uploader} and requested by {1.display_name}'
        duration = self.player.duration
        if duration:
            fmt = fmt + ' [length: {0[0]}m {0[1]}s]'.format(divmod(duration, 60))
        return fmt.format(self.player, self.requester)


class VoiceState:
    def __init__(self, bot):
        self.current = None
        self.voice = None
        self.bot = bot
        self.play_next_song = asyncio.Event()
        self.songs = asyncio.Queue()
        self.audio_player = self.bot.loop.create_task(self.audio_player_task())

    def is_playing(self):
        if self.voice is None or self.current is None:
            return False

        player = self.current.player
        return not player.is_done()

    @property
    def player(self):
        return self.current.player

    def skip(self):
        if self.is_playing():
            self.player.stop()

    def toggle_next(self):
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)

    async def audio_player_task(self):
        while True:
            self.play_next_song.clear()
            self.current = await self.songs.get()
            await self.bot.send_message(self.current.channel, 'Now playing ' + str(self.current))
            self.current.player.start()
            await self.play_next_song.wait()


class Music:
    '''
    Voice-related commands.
    Works in multiple servers at once.
    '''
    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}
        # Build the dictionary relating categories to lists of sounds
        self.sound_lists = {}
        # For each subdirectory (category) of sounds
        for category in next(os.walk('sounds'))[1]:
            # Associate the category with its list of sounds
            self.sound_lists[category] = [sound.replace('.mp3', '')
                                          for sound in next(os.walk('sounds/' + category))[2]]

    def get_voice_state(self, server):
        state = self.voice_states.get(server.id)
        if state is None:
            state = VoiceState(self.bot)
            self.voice_states[server.id] = state

        return state

    async def create_voice_client(self, channel):
        voice = await self.bot.join_voice_channel(channel)
        state = self.get_voice_state(channel.server)
        state.voice = voice

    def __unload(self):
        for state in self.voice_states.values():
            try:
                state.audio_player.cancel()
                if state.voice:
                    self.bot.loop.create_task(state.voice.disconnect())
            except:
                pass

    @commands.command(pass_context=True, no_pm=True)
    async def join(self, ctx, *, channel : discord.Channel):
        ''' Joins a voice channel. '''
        try:
            await self.create_voice_client(channel)
        except discord.InvalidArgument:
            await self.bot.say('This is not a voice channel...')
        except discord.ClientException:
            await self.bot.say('Already in a voice channel...')
        else:
            await self.bot.say('Ready to play audio in ' + channel.name)

    @commands.command(pass_context=True, no_pm=True)
    async def summon(self, ctx):
        ''' Summons the bot to join your voice channel. '''
        summoned_channel = ctx.message.author.voice_channel
        if summoned_channel is None:
            await self.bot.say('You are not in a voice channel.')
            return False

        state = self.get_voice_state(ctx.message.server)
        if state.voice is None:
            state.voice = await self.bot.join_voice_channel(summoned_channel)
        else:
            await state.voice.move_to(summoned_channel)

        return True

    @commands.command(pass_context=True, no_pm=True)
    async def play(self, ctx, *, song : str):
        '''
        Plays a song.

        If there is a song currently in the queue, then it is
        queued until the next song is done playing.

        This command automatically searches as well from YouTube.
        The list of supported sites can be found here:
        https://rg3.github.io/youtube-dl/supportedsites.html
        '''
        state = self.get_voice_state(ctx.message.server)
        opts = {
            'default_search': 'auto',
            'quiet': True,
        }

        if not await self.summon_if_needed(ctx, state):
            return

        try:
            player = await state.voice.create_ytdl_player(song, ytdl_options=opts, after=state.toggle_next)
        except Exception as e:
            fmt = 'An error occurred while processing this request: ```py\n{}: {}\n```'
            await self.bot.send_message(ctx.message.channel, fmt.format(type(e).__name__, e))
        else:
            player.volume = 0.6
            entry = VoiceEntry(ctx.message, player)
            await self.bot.say('Enqueued ' + str(entry))
            await state.songs.put(entry)

    @commands.command(pass_context=True, no_pm=True)
    async def volume(self, ctx, value : int):
        ''' Sets the volume of the currently playing song. '''

        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.volume = value / 100
            await self.bot.say('Set the volume to {:.0%}'.format(player.volume))

    @commands.command(pass_context=True, no_pm=True)
    async def pause(self, ctx):
        ''' Pauses the currently playing song. '''
        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.pause()

    @commands.command(pass_context=True, no_pm=True)
    async def resume(self, ctx):
        ''' Resumes the currently playing song. '''
        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.resume()

    @commands.command(pass_context=True, no_pm=True)
    async def stop(self, ctx):
        '''
        Stops playing audio and leaves the voice channel.

        This also clears the queue.
        '''
        server = ctx.message.server
        state = self.get_voice_state(server)

        if state.is_playing():
            player = state.player
            player.stop()

        try:
            state.audio_player.cancel()
            del self.voice_states[server.id]
            await state.voice.disconnect()
        except:
            pass

    @commands.command(pass_context=True, no_pm=True)
    async def skip(self, ctx):
        ''' Skips current song. '''
        state = self.get_voice_state(ctx.message.server)
        if not state.is_playing():
            await self.bot.say('Not playing any music right now...')
            return

        await self.bot.say('Skipping song...')
        state.skip()

    @commands.command(pass_context=True, no_pm=True)
    async def playing(self, ctx):
        ''' Shows info about the currently playing song. '''
        state = self.get_voice_state(ctx.message.server)
        if state.current is None:
            await self.bot.say('Not playing anything.')
        else:
            await self.bot.say('Now playing ' + state.current)

    @commands.command(pass_context=True, no_pm=True)
    async def sb(self, ctx, desire: str=None):
        '''
        Plays a given sound from the soundboard.

        Call this command with no argument to see available sounds.
        '''
        if desire is None:
            available = 'Available categories: '
            for option in self.sound_lists:
                available += option + ', '
            available += 'all'
            await self.bot.say(available)
            return

        server = ctx.message.server
        state = self.get_voice_state(server)
        if state.is_playing():
            await self.bot.say('Something is currently playing. Use q.stop first.')
            return

        if desire == 'all':
            result = 'All available sounds:'
            for sounds in self.sound_lists.values():
                for sound in sounds:
                    result += '\n' + sound
            await self.bot.say(result)
            return

        if desire == 'random':
            category, choice_list = random.choice(list(self.sound_lists.items()))
            result = random.choice(choice_list)
            if not await self.summon_if_needed(ctx, state):
                return
            path = 'sounds/{0}/{1}.mp3'.format(category, result)
            await self.play_sound(state, path)
            return

        # If the user gave a category
        if desire in self.sound_lists:
            output = 'Category ' + desire + ': '
            for sound in self.sound_lists[desire]:
                output += sound + ', '
            output += 'random'
            await self.bot.say(output)
            return

        for category, sounds in self.sound_lists.items():
            for sound in sounds:
                if sound == desire:
                    if not await self.summon_if_needed(ctx, state):
                        return
                    path = 'sounds/{0}/{1}.mp3'.format(category, sound)
                    await self.play_sound(state, path)
                    return

        await self.bot.say('Invalid category/sound name. Try q.sb with no arguments.')

    @commands.command(pass_context=True, no_pm=True)
    async def say(self, ctx, *args):
        ''' Text to speech. '''
        if args is None:
            await self.bot.say('Give me text to speak.')
            return
        server = ctx.message.server
        state = self.get_voice_state(server)
        if state.is_playing():
            await self.bot.say('Something is currently playing. Use q.stop first.')
            return

        # Convert desired speech from a list into a single string
        desire = ''
        for word in args:
            desire += word + ' '

        if not await self.summon_if_needed(ctx, state):
            return

        # Create the corresponding spoken text using GTTS
        # Full list of voices within tts.py of gtts module
        tts = gTTS(desire, 'en-uk')
        tts.save('sounds/temp_voice.mp3')
        # Load and increase the volume of the sound using pydub's AudioSegment
        sound = AudioSegment.from_mp3('sounds/temp_voice.mp3')
        louder_sound = sound + 15
        louder_sound.export('sounds/temp_voice_boosted.mp3', format='mp3')
        # Play the boosted sound
        await self.play_sound(state, 'sounds/temp_voice_boosted.mp3')

    # Extras/Helpers (params/returns listed here since these do not appear as actual commands)
    async def play_join_sound(self, server, channel, sound):
        '''
        Plays a particular join sound on the desired server.
        Params:
            Server server: the desired server
            Channel channel: the target channel (presumably the one the user just joined)
            str sound: the full path to the sound, plus its extension
        '''
        state = self.get_voice_state(server)
        if state.is_playing():
            return
        if state.voice is None:
            await self.create_voice_client(channel)
        await self.play_sound(state, sound)

    async def summon_if_needed(self, ctx, state):
        '''
        Summons the bot to the user's voice channel if needed.
        Params:
            CTX ctx: the relevant context object
            State state: the particular server's state
        Returns:
            bool: True if successful, False otherwise.
        '''
        if state.voice is None:
            return await ctx.invoke(self.summon)
        return True

    async def play_sound(self, state, path):
        '''
        Plays a given sound in a particular category using a state object.
        Params:
            State state: the particular server's state
            str path: the full path to the sound, plus its extension
        '''
        player = state.voice.create_ffmpeg_player(path)
        player.start()
