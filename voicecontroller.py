import asyncio
from asyncio import Lock
import os
import discord
from discord import VoiceClient, VoiceChannel
from discord.ext import commands
import random
from gtts import gTTS
from gtts.lang import tts_langs
from youtube_dl import YoutubeDL
from datetime import datetime, timedelta
from functools import wraps

from exceptions import BananaCrime


SOUND_DIR = 'sounds'
GTTS_DEFAULT_LANG = 'en-uk'
GTTS_TEMP_FILE = f'{SOUND_DIR}/temp_voice.mp3'
# Options to pass to FFMPEG
# * Reconnect args are to catch and fix stream interruptions
# * -vn disables video (since we just want audio)
FFMPEG_OPTS = {
    'before_options': \
        '-reconnect 1 ' \
        '-reconnect_streamed 1 ' \
        '-reconnect_delay_max 5',
    'options': '-vn'
}
# Options to pass to YTDL
# * Most are self-explanatory
# * source_address ensures it binds to IPv4, since IPv6 can cause issues
YTDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'auto',
    'quiet': True,
    'source_address': '0.0.0.0'
}
YTDL = YoutubeDL(YTDL_OPTS)


class YTDLSource(discord.PCMVolumeTransformer):
    """Wrapper for YoutubeDL streaing functionality.

    Shouldn't directly call the constructor; use `create_from_search` instead.
    Inspired by:
    https://github.com/Rapptz/discord.py/blame/master/examples/basic_voice.py
    """
    def __init__(self, source, info, volume=0.5):
        super().__init__(source, volume)
        self.title = info['title']
        self.uploader = info['uploader']
        self.duration_m, self.duration_s = divmod(info['duration'], 60)

    def __str__(self):
        return (
            f"{self.title}\n"
            f"uploaded by {self.uploader}\n"
            f"[{self.duration_m}m {self.duration_s}s]"
        )

    @classmethod
    async def create_from_search(cls, search, loop=asyncio.get_event_loop()):
        info = await loop.run_in_executor(
            None, lambda: YTDL.extract_info(search, download=False)
        )
        # If it found multiple possibilities, just grab the 1st one
        if 'entries' in info:
            info = info['entries'][0]

        return cls(discord.FFmpegPCMAudio(info['url'], **FFMPEG_OPTS), info)


class VoiceController(commands.Cog, name='Voice'):
    """Handles all voice-related functionality."""

    def __init__(self, bot):
        self.bot = bot
        # Grab valid TTS languages from `gtts.lang` to give language options
        self.valid_tts_langs = tts_langs()
        self.load_sounds()

    def load_sounds(self):
        """Build the dictionaries relating categories and lists of sounds.

        Note: There cannot be sounds with duplicate filenames.
        """
        self.category_to_sounds = {}  # used for easy listing
        self.sound_to_category = {}   # used to quickly check for membership
        # For each subdirectory (category) of sounds
        for category in next(os.walk('sounds'))[1]:
            # Associate the category with its list of sounds
            sounds = [
                sound[:-4] for sound in os.listdir(f'{SOUND_DIR}/{category}')
            ]
            for sound in sounds:
                if sound in self.sound_to_category:
                    raise ValueError(
                        'Detected duplicate sound name: '
                        f'{self.sound_to_category[sound]}/{sound} '
                        f'vs {category}/{sound}'
                    )
                self.sound_to_category[sound] = category
            self.category_to_sounds[category] = sorted(sounds)

    async def prepare_to_play(self, ctx):
        """Prepare to play an AudioSource.

        Specifically, ensure I am not already playing something, and
            if I'm not in a VC, attempt to join that of the caller.
        """
        vclient = ctx.voice_client
        if not vclient or not vclient.is_connected():
            await ctx.invoke(self.summon)
            return ctx.voice_client

        if vclient.is_playing():
            raise BananaCrime("I'm already playing something")

        if vclient.is_paused():
            vclient.stop()

        return vclient

    @commands.is_owner()
    @commands.command(pass_context=True, aliases=('reload',))
    async def reloadsb(self, ctx):
        """Reload soundboard listing; must be my owner."""
        self.load_sounds()
        await ctx.send('Done.')

    @commands.command(pass_context=True)
    async def join(self, ctx, channel: VoiceChannel=None):
        """Join the given voice channel."""
        if not channel:
            raise BananaCrime('I need a channel to join')
        vclient = ctx.voice_client
        if vclient and vclient.is_connected():
            await vclient.move_to(channel)
        else:
            await channel.connect()

    @commands.command(pass_context=True)
    async def summon(self, ctx):
        """Join the voice channel of the caller."""
        if not ctx.author.voice:
            raise BananaCrime('You are not in a voice channel')
        target_channel = ctx.author.voice.channel
        vclient = ctx.voice_client
        if vclient and vclient.is_connected():
            if vclient.channel == target_channel:
                raise BananaCrime("I'm already in this channel")
            await vclient.move_to(target_channel)
        else:
            await target_channel.connect()

    @commands.command(pass_context=True)
    async def stop(self, ctx):
        """Stop all playback but stays in channel."""
        vclient = ctx.voice_client
        if not vclient:
            raise BananaCrime("I'm not in a voice channel")

        if vclient.is_playing() or vclient.is_paused():
            vclient.stop()
        else:
            raise BananaCrime("I'm not playing anything")

    @commands.command(pass_context=True)
    async def leave(self, ctx):
        """Leave the current voice channel."""
        vclient = ctx.voice_client
        if not vclient:
            raise BananaCrime("I'm not in a voice channel")

        await ctx.voice_client.disconnect()

    @commands.command(pass_context=True)
    async def sb(self, ctx, desire: str=None):
        """Play a given sound from the soundboard.

        Call this command with no argument to see available sounds.
        """
        if not desire:
            await ctx.send(
                'Available categories: '
                f'{", ".join(self.category_to_sounds)}, all'
            )

        elif desire == 'all':
            await ctx.send(
                'All available sounds:\n'
                + '\n'.join([
                    '\n'.join(sounds)
                    for sounds in self.category_to_sounds.values()
                ])
            )

        # If they searched a category
        elif desire in self.category_to_sounds:
            await ctx.send(
                f'Category {desire}: '
                f'{", ".join(self.category_to_sounds[desire])}'
            )

        elif desire == 'random':
            category, sounds = random.choice(
                list(self.category_to_sounds.items())
            )
            vclient = await self.prepare_to_play(ctx)
            path = f'{SOUND_DIR}/{category}/{random.choice(sounds)}.mp3'
            vclient.play(
                discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(path), 0.5)
            )

        # Ensure the sound exists
        elif desire in self.sound_to_category:
            category = self.sound_to_category[desire]
            vclient = await self.prepare_to_play(ctx)
            path = f'{SOUND_DIR}/{category}/{desire}.mp3'
            vclient.play(
                discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(path), 0.5)
            )

        else:
            raise BananaCrime(
                'Invalid category/sound name; try `q.sb` with no arguments'
            )

    @commands.command(pass_context=True)
    async def say(self, ctx, *, desire: str=None):
        """Use gTTS to play a text-to-speech message."""
        await ctx.invoke(self.saylang, GTTS_DEFAULT_LANG, desire=desire)

    @commands.command(pass_context=True)
    async def saylang(self, ctx, lang=None, *, desire=None):
        """Use gTTS to play a text-to-speech message using a given language."""
        if not lang:
            await ctx.send(
                'Available languages:\n'
                + '\n'.join([
                    f'{v}: `{k}`' for k, v in self.valid_tts_langs.items()
                ])
            )
            return
        if not desire:
            raise BananaCrime('Give me text to speak')

        vclient = await self.prepare_to_play(ctx)
        try:
            tts = gTTS(desire, lang=lang)
        except ValueError:
            raise BananaCrime('Invalid language')
        tts.save(GTTS_TEMP_FILE)

        vclient.play(
            discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(GTTS_TEMP_FILE), 1
            )
        )

    @commands.command(pass_context=True)
    async def play(self, ctx, *, desire: str=None):
        """Play a song. Give me a URL or a search term."""
        if not desire:
            raise BananaCrime('Give me a search term')

        async with ctx.typing():
            vclient = await self.prepare_to_play(ctx)
            ytdl_src = await YTDLSource.create_from_search(
                desire, self.bot.loop
            )
            vclient.play(
                ytdl_src,
                after=lambda e: print('YT got mad:', e) if e else None
            )
        await ctx.send(f"*Now playing:*\n{ytdl_src}")

    @commands.command(pass_context=True)
    async def pause(self, ctx):
        """Pause song playback."""
        vclient = ctx.voice_client
        if not vclient or not vclient.is_playing():
            raise BananaCrime("I'm not playing anything")
        if type(vclient.source) != YTDLSource:
            raise BananaCrime("You can't pause the soundboard")

        vclient.pause()

    @commands.command(pass_context=True)
    async def resume(self, ctx):
        """Resume playing a song."""
        vclient = ctx.voice_client
        if not vclient or not vclient.is_connected():
            raise BananaCrime("I'm not in a voice channel")
        if type(vclient.source) != YTDLSource:
            raise BananaCrime("You can't pause/unpause the soundboard")
        if not vclient.is_paused():
            raise BananaCrime("I'm not paused")

        vclient.resume()

    @commands.command(pass_context=True)
    async def playing(self, ctx):
        """Get the information of the currently playing song, if any."""
        vclient = ctx.voice_client
        if not vclient or not vclient.is_connected():
            raise BananaCrime("I'm not even in a voice channel")

        if (vclient.is_playing() or vclient.is_paused()) \
            and type(vclient.source) == YTDLSource:
            await ctx.send(f"*Currently playing:*\n{vclient.source}")
        else:
            await ctx.send("I'm not playing any songs at the moment.")

    @commands.command(pass_context=True)
    async def volume(self, ctx, vol: int=None):
        """Set the volume of whatever is currently playing.

        Takes a percentage as an integer.
        """
        if vol is None or not vol >= 0 or not vol <= 100:
            raise BananaCrime("That's not a valid integer percentage (0-100)")
        vclient = ctx.voice_client
        if not vclient or not vclient.is_connected():
            raise BananaCrime("I'm not even in a voice channel")

        vclient.source.volume = vol / 100
        await ctx.send(f"Volume set to {vol}%.")
