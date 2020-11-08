import asyncio
import os
import discord
from discord import VoiceChannel
from discord.ext import commands
import random
from gtts import gTTS
# _extra_langs is needed for now since there's a bug in gTTS
from gtts.lang import tts_langs, _extra_langs
from datetime import datetime
from functools import partial
import logging
import editdistance

from exceptions import BananaCrime


# Defaults
DEFAULT_SB_NUM_NEW = 20
DEFAULT_SB_REQUEST_FILE_MAX_SIZE_B = 10000
DEFAULT_SB_REQUEST_FILENAME = 'sb_requests.txt'

# Directory housing all sounds
SOUND_DIR = 'sounds'
# Default language to use with GTTS
GTTS_DEFAULT_LANG = 'en-uk'
# Where to store the temporary voice file when using GTTS
GTTS_TEMP_FILE = f'{SOUND_DIR}/temp_voice.mp3'
# Minimum edit distance for a requested `sb` sound request
MIN_EDIT_DIST = 4

LOGGER = logging.getLogger(__name__)


async def split_send(ctx, msg):
    """Send a message in segments of <2k characters.

    It's possible for the bot to produce a message longer than 2k characters,
    which discord does not support. This fixes this issue.
    NOTE: Splits by newlines; there must be at least one per 2k characters.
    """
    start_p = 0
    end_p = 1999
    while end_p < len(msg):
        if msg[end_p] != '\n':
            end_p -= 1
        else:
            await ctx.send(msg[start_p:end_p])
            start_p = end_p
            end_p += 1999
    await ctx.send(msg[start_p:])


class VoiceController(commands.Cog, name='Voice'):
    """Handles all voice-related functionality.

    Will read soundboard files from SOUND_DIR.
    NOTE: There cannot be sounds with duplicate filenames.

    Args:
        sb_num_new (str): When listing newest sounds on soundboard, list the
            most recent sb_num_new sounds.
        sb_request_filename (str): Name of the file to write soundboard requests to.
        sb_request_file_max_size_b (int): Loose maximum allowed size of the
            soundboard request file in bytes. Specifically, a soundboard request
            can only be a certain number of bytes long; once the file grows over
            sb_request_file_max_size_b bytes, requests will be denied.
    """

    def __init__(self, bot, **kwargs):
        self.bot = bot
        self.parse_kwargs(kwargs)

        # Grab valid TTS languages from `gtts.lang` to give language options
        try:
            self.valid_tts_langs = tts_langs()
        except RuntimeError:
            self.valid_tts_langs = _extra_langs()
        self.load_sounds()

    def parse_kwargs(self, kwargs):
        """Helper to parse kwargs and set defaults."""
        self.sb_num_new = kwargs.get('sb_num_new', DEFAULT_SB_NUM_NEW)
        self.sb_request_file_max_size_b = kwargs.get(
            'sb_request_file_max_size_b', DEFAULT_SB_REQUEST_FILE_MAX_SIZE_B
        )
        self.sb_request_filename = kwargs.get(
            'sb_request_filename', DEFAULT_SB_REQUEST_FILENAME
        )

    def load_sounds(self):
        """Build the dictionaries relating categories and lists of sounds."""
        self.category_to_sounds = {}  # used for easy listing
        self.sound_to_category = {}   # used to quickly check for membership
        # For each subdirectory (category) of sounds
        for category in next(os.walk(SOUND_DIR))[1]:
            # Associate the category with its list of sounds
            sounds = [
                sound[:-4] for sound in os.listdir(
                    os.path.join(SOUND_DIR, category)
                )
            ]
            # Check for duplicates
            for sound in sounds:
                if sound in self.sound_to_category:
                    raise ValueError(
                        'Detected duplicate sound name: '
                        f'{self.sound_to_category[sound]}/{sound} '
                        f'vs {category}/{sound}'
                    )
                self.sound_to_category[sound] = category
            self.category_to_sounds[category] = sorted(sounds)
        # Build list of newest sounds
        self.newest_sounds = [
            os.path.basename(sound)[:-4] for sound in sorted(
                [
                    os.path.join(SOUND_DIR, category, f'{sound}.mp3')
                    for sound, category in self.sound_to_category.items()
                ],
                key=os.path.getmtime,
                reverse=True
            )[:self.sb_num_new]
        ]

    async def close(self):
        """Disconnect all voice clients."""
        active_vclients = [
            record.guild.voice_client
            for record in self.bot.guild_records.values()
            if record.guild.voice_client
                and record.guild.voice_client.is_connected()
        ]
        dc_coros = [vclient.disconnect() for vclient in active_vclients]
        results = await asyncio.gather(*dc_coros, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                LOGGER.error(
                    'Unable to close a voice client: '\
                    f'{type(result).__name__}, {result.args!r}'
                )

    async def check_record_for_inactivity(self, record):
        """Check record for timeout, and do so if required."""
        guild = record.guild
        vclient = guild.voice_client
        if record.should_timeout:
            record.mark_inactive()
            # Double check there's still an active voice connection that isn't
            #   playing something currently
            if vclient and vclient.is_connected() and not vclient.is_playing():
                # NOTE: If YTDL ever comes back, may tweak this
                await vclient.disconnect()
                await record.send('Disconnected from voice due to inactivity.')
                LOGGER.info(f'VC timed out in {guild}#{guild.id}')

        # Disconnects might silently fail when someone runs a leave
        #   right after the bot creates a new voice client, so
        #   bot.guild_records might be missing a GVR
        # If we just put a retry wrapper around disconnect calls,
        #   it still can't detect it without introducing unnecessary
        #   delays for all disconnects, since voice clients don't
        #   reflect the issue until after the bot re-syncs w discord
        elif not record.is_active and vclient and vclient.is_connected():
            record.update()
            LOGGER.info(f'Handled missing GVR in {guild}#{guild.id}')

    async def _summon(self, ctx):
        """Helper that attempts to join the VC of the caller.

        NOTE: Does not perform any locking.
        """
        if not ctx.author.voice:
            raise BananaCrime('You are not in a voice channel')
        target_channel = ctx.author.voice.channel
        if not target_channel.permissions_for(ctx.guild.me).connect:
            raise BananaCrime(
                "I don't have permission to join your voice channel"
            )

        vclient = ctx.voice_client
        if vclient and vclient.is_connected():
            if vclient.channel == target_channel:
                raise BananaCrime("I'm already in this channel")
            await vclient.move_to(target_channel)
        else:
            await target_channel.connect()

    async def prepare_to_play(self, ctx, require_silence=True):
        """Prepare to play an AudioSource.

        Specifically, stop playback or complain if something's already playing
        depending on the require_silence parameter, and if I'm not in a VC,
        attempt to join that of the caller.
        NOTE: Does not perform any locking.
        """
        vclient = ctx.voice_client
        if not vclient or not vclient.is_connected():
            await self._summon(ctx)
            return ctx.voice_client

        if vclient.is_playing():
            if require_silence:
                raise BananaCrime("I'm already playing something")
            else:
                vclient.stop()
        elif vclient.is_paused():
            vclient.stop()

        return vclient

    @commands.is_owner()
    @commands.command(pass_context=True, aliases=('reload',))
    async def sbreload(self, ctx):
        """Reload soundboard listing; must be my owner."""
        self.load_sounds()
        await ctx.message.add_reaction('\N{OK HAND SIGN}')

    @commands.command(pass_context=True)
    async def join(self, ctx, channel: VoiceChannel=None):
        """Join the given voice channel."""
        if not channel:
            raise BananaCrime('I need a channel to join')
        if not channel.permissions_for(ctx.guild.me).connect:
            raise BananaCrime(
                "I don't have permission to join that voice channel"
            )

        vclient = ctx.voice_client
        async with self.bot.guild_records[ctx.guild.id].lock:
            if vclient and vclient.is_connected():
                if vclient.channel == channel:
                    raise BananaCrime("I'm already in this channel")
                await vclient.move_to(channel)
            else:
                await channel.connect()

    @commands.command(pass_context=True)
    async def summon(self, ctx):
        """Join the voice channel of the caller."""
        async with self.bot.guild_records[ctx.guild.id].lock:
            await self._summon(ctx)

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

        guild_lock = self.bot.guild_records[ctx.guild.id].lock
        # If I was called at the same time as I'm processing a command,
        #   when I eventually get my turn to execute, I need to wait a moment
        #   before leaving, otherwise the library will be confused
        # In addition, passing this condition is a sneaky/mean thing to do, so
        #   I'll also be sassy
        should_wait = guild_lock.locked()
        async with guild_lock:
            if should_wait:
                await asyncio.sleep(0.1)
                await ctx.send(
                    "You people need to make up your minds; do you want me to "
                    "play something or not? :rolling_eyes:"
                )
            ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
        self.bot.guild_records[ctx.guild.id].mark_inactive()

    async def play_sound(self, ctx, category, sound):
        """Helper that plays a given sound belonging to a given category."""
        guild_lock = self.bot.guild_records[ctx.guild.id].lock
        if guild_lock.locked():
            raise BananaCrime("I'm already trying to process a VC command")
        async with guild_lock:
            vclient = await self.prepare_to_play(ctx, False)
        path = f'{SOUND_DIR}/{category}/{sound}.mp3'
        vclient.play(
            discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(path), 0.5)
        )

    @commands.command(pass_context=True)
    async def sb(self, ctx, desire: str=None):
        """Play a given sound from the soundboard.

        Call this command with no argument to see available sounds.
        """
        if not desire:
            await ctx.send(
                'Available categories: '
                f'{", ".join(self.category_to_sounds)}, new, all'
            )

        elif desire == 'all':
            # Use split send since this guy can easily grow above 2k chars
            await split_send(
                ctx,
                'All available sounds:\n'
                + '\n'.join([
                    '\n'.join(sounds)
                    for sounds in self.category_to_sounds.values()
                ])
            )

        elif desire == 'new':
            await ctx.send(
                'Most recently added sounds:\n' + '\n'.join(self.newest_sounds)
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
            sound = random.choice(sounds)
            await self.play_sound(ctx, category, sound)
            await ctx.send(f"You just heard `{sound}`.")

        # If the sound exists
        elif desire in self.sound_to_category:
            category = self.sound_to_category[desire]
            await self.play_sound(ctx, category, desire)

        # See if we can guess what they meant
        else:
            substring_matches = [
                sound for sound in self.sound_to_category
                if desire in sound or sound in desire
            ]
            # Always go with substring membership before edit distance
            if substring_matches:
                sound = min(
                    substring_matches,
                    key=lambda p, l=len(desire): abs(len(p) - l)
                )
            # Didn't have any substring matches, go with edit distance
            else:
                sound = min(
                    self.sound_to_category,
                    key=partial(editdistance.eval, desire)
                )
                # Ensure it is within the minimum edit distance
                sound = sound \
                    if editdistance.eval(desire, sound) > MIN_EDIT_DIST \
                    else None

            # If I still didn't find anything, give up
            if not sound:
                raise BananaCrime(
                    'Invalid category/sound name; try `q.sb` with no arguments'
                )
            # Otherwise, go for it
            category = self.sound_to_category.get(sound)
            await self.play_sound(ctx, category, sound)
            await ctx.send(
                f"`{desire}` isn't a valid sound, "
                f"so I'll play `{sound}` instead."
            )

    @commands.command(pass_context=True)
    async def say(self, ctx, *, desire=None):
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

        async with self.bot.guild_records[ctx.guild.id].lock:
            vclient = await self.prepare_to_play(ctx)
        try:
            tts = gTTS(desire, lang=lang)
        except ValueError:
            raise BananaCrime('Invalid language')
        tts.save(GTTS_TEMP_FILE)

        vclient.play(
            discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(
                    # Suppress bitrate estimation warning
                    GTTS_TEMP_FILE, options='-loglevel error'
                ),
                1
            )
        )

    @commands.command(pass_context=True)
    async def play(self, ctx, *, desire: str=None):
        """This command no longer works due to the DMCA strike against YTDL.

        Read more about it here: https://github.com/github/dmca/pull/8153
        """
        await ctx.send(
            "Due to recent developments, YTDL no longer is available, "
            "therefore this command no longer works. See this link for more "
            "context: https://github.com/github/dmca/pull/8153"
        )

    @commands.command(pass_context=True)
    async def sbrequest(self, ctx, url, start_time=None, end_time=None):
        """Put in a request to add a sound to the soundboard.

        URL should link to the corresponding video.
        Can optionally provide start/end timestamps in the format hh:mm:ss,
        which would greatly be appreciated so I know what you're looking for,
        especially if the video is longer than a few seconds.
        If you give me anything invalid, I will know who you are and will
        publicly shame you accordingly.
        """
        if 'dQw4w9WgXcQ' in url:
            raise BananaCrime(
                'Did you really just try to rick roll me? In 2020? Come on'
            )
        if os.stat(self.sb_request_filename).st_size \
                > self.sb_request_file_max_size_b:
            await ctx.send("My request queue is too full; try again later.")
            return
        if len(url) > 100:
            raise BananaCrime('URLs cannot be longer than 100 characters')
        if (start_time and len(start_time) > 10) \
            or (end_time and len(end_time) > 10):
            raise BananaCrime('Timestamps cannot be longer than 10 characters')

        with open(self.sb_request_filename, 'a') as f:
            f.write(f"[{datetime.now()}] {ctx.message.author} requests {url}")
            if start_time:
                f.write(f' from {start_time}')
                if end_time:
                    f.write(f' to {end_time}')
            f.write('\n')

        LOGGER.info('Recorded a soundboard request.')
        await ctx.send('Request made.')

    @commands.command(pass_context=True)
    async def sbcount(self, ctx):
        """Display how many sounds are currently in the soundboard."""
        await ctx.send(f'Number of sounds: {len(self.sound_to_category)}')

    @commands.command(pass_context=True)
    async def refresh(self, ctx):
        """Refresh my connection to prevent me from timing out."""
        vclient = ctx.voice_client
        # Don't even bother checking if there's a GVR, since this is the only
        #   user-facing piece of information
        if not vclient or not vclient.is_connected():
            raise BananaCrime(
                "I'm not in a voice channel, so there's no reason to refresh me"
            )
        self.record_guild_update(ctx)
        await ctx.message.add_reaction('\N{OK HAND SIGN}')
