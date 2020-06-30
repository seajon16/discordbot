import json


SETTINGS_FILENAME = 'settings.json'
with open(SETTINGS_FILENAME) as settings_file:
    SETTINGS_DICT = json.load(settings_file)


def get_settings():
    return SETTINGS_DICT
