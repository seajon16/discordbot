import logging.config
import json

from sassbot import SassBot


SETTINGS_FILENAME = 'settings.json'
with open(SETTINGS_FILENAME) as settings_file:
    SETTINGS_DICT = json.load(settings_file)

logging.config.dictConfig(SETTINGS_DICT['logging'])

bot = SassBot(**SETTINGS_DICT['bot_settings'])

if __name__ == '__main__':
    bot.run()
