# Description
* Discord bot with personality
* General commands:
  * `help`: Lists all commands
  * `ping`/`howyoudoin`: Healthcheck
  * `roll`: Handles a dice roll in the form (A)dB(+C-D...)
  * `choose`: Picks a random option from a given list of choices
  * `fact`: Gives a random fact using [uselessfacts.jsph.pl](https://uselessfacts.jsph.pl)
  * `shutdown`: Gracefully shuts down the bot; must be my owner

* Can stream audio from the internet using `youtube-dl`
* Configuarble soundboard with category support

# Requirements
* Python 3.7+
* The following packages:
  * `pip`-able:
    * `discord.py[voice]`
    * `gTTS`
    * `youtube-dl`
  * Not `pip`-able:
    * `ffmpeg`
      * For **Linux**, this is available through most package managers (i.e. `apt`)
      * For **Windows**, follow [this tutorial](https://github.com/adaptlearning/adapt_authoring/wiki/Installing-FFmpeg) by Adapt Learning

# Installation
* Clone the repo
* Replace `[INSERT TOKEN HERE]` in [`settings.json`](./settings.json) with your bot's token
  * If you need a bot token, follow [these instructions](https://www.writebots.com/discord-bot-token/)

# Use
* Run `python main.py` to start the bot
* `q.help` lists all commands
* Sounds placed in the [`sounds`](./sounds) directory must be contained in additional subfolders, used as categories
  * For example, if one wanted to insert the sound `bell.mp3` in the `noises` category, one would place it in `sounds/noises/bell.mp3`
  * If the sound file is placed directly into the `sounds` folder, it will be ignored

# Additional Resources
* [discord.py documentation](https://discordpy.readthedocs.io/en/latest/api.html)
* [`basic_voice.py` example from discord.py's repo](https://github.com/Rapptz/discord.py/blob/master/examples/basic_voice.py), which partially inspired this bot's [`voicecontroller.py`](./voicecontroller.py)
