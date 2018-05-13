# Description
* Discord bot with personality
* General commands:
  * help: Lists all commands
  * add: Adds a bunch of numbers together
  * choice: Picks a random option from a given list of choices
  * guessinggame: Starts a guessing game; use q.guessinggame [guess] to guess
  * iscool: Determines if @User is cool (is an admin of the bot)
  * lspam: Sends a single message composed of the desired messsage copied n times (must be an admin)
  * mspam: Sends a message n times (must be an admin)
  * ping: Tests connection
  * roll: Handles Handles a roll in the form (A)dB(+C-D...)
* Can pull videos from the internet using youtube-dl
* Configuarble soundboard with category support

# Requires
### pip-able:
* discord.py[voice]
* gTTS
* pydub
* youtube-dl
### Not pip-able:
* ffmpeg, which can be installed using [this tutorial](https://github.com/adaptlearning/adapt_authoring/wiki/Installing-FFmpeg) by Adapt Learning
  * Used by youtube-dl to grab audio

# Installing
* Replace [INSERT TOKEN HERE] in main.py with the token used by your bot application
* Create a sounds folder in the same directory as main.py and music.py
* _Optional:_ Uncomment the function defined on lines 55-64 of main.py to allow join sounds, then format the dictionary defined on line 28 of main.py

# Use
* q.help lists all commands
* Sounds placed in the sounds directory must be contained in additional subfolders, used as categories
  * For example, if one wanted to insert the sound bell.mp3 in the noises category, one would place it in sounds/noises/bell.mp3
  * If the sound file is placed directly into the sounds folder, it will be ignored
