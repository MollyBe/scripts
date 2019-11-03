import os
import logging
import json
import sys
import requests
import configparser
import argparse
import shutil
import time

parser = argparse.ArgumentParser(description='RadarrSync. Sync two or more Radarr servers. https://github.com/Sperryfreak01/RadarrSync')
parser.add_argument('--config', action="store", type=str, help='Location of config file.')
parser.add_argument('--debug', help='Enable debug logging.', action="store_true")
parser.add_argument('--whatif', help="Read-Only. What would happen if I ran this. No posts are sent. Should be used with --debug", action="store_true")
args = parser.parse_args()

def ConfigSectionMap(section):
    dict1 = {}
    options = Config.options(section)
    for option in options:
        try:
            dict1[option] = Config.get(section, option)
            if dict1[option] == -1:
                logger.debug("skip: %s" % option)
        except:
            print("exception on %s!" % option)
            dict1[option] = None
    return dict1

Config = configparser.ConfigParser()
settingsFilename = os.path.join(os.getcwd(), 'configLanguage.txt')
if args.config:
    settingsFilename = args.config
elif not os.path.isfile(settingsFilename):
    print("Creating default config. Please edit and run again.")
    shutil.copyfile(os.path.join(os.getcwd(), 'configLanguage.default'), settingsFilename)
    sys.exit(0)
Config.read(settingsFilename)

########################################################################################################################
general = ConfigSectionMap('General')
logger = logging.getLogger()
if general['log_level'] == 'DEBUG':
    logger.setLevel(logging.DEBUG)
elif general['log_level'] == 'VERBOSE':
    logger.setLevel(logging.VERBOSE)
else:
    logger.setLevel(logging.INFO)
if args.debug:
    logger.setLevel(logging.DEBUG)

logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")

fileHandler = logging.FileHandler(general['log_path'],'w','utf-8')
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)
########################################################################################################################

session = requests.Session()
session.trust_env = False

servers = {}
for section in Config.sections():
    section = str(section)
    if "Radarr_" in section:
        server = (str.split(section,'Radarr_'))[1]
        servers[server] = ConfigSectionMap(section)
        movies = session.get('{0}/api/movie?apikey={1}'.format(servers[server]['url'], servers[server]['key']))
        if movies.status_code != 200:
            logger.error('{0} Radarr server error - response {1}'.format(server, movies.status_code))
            sys.exit(0)
        else:
            servers[server]['rmMovies'] = 0
            servers[server]['movies'] = []
            servers[server]['newMovies'] = 1
            servers[server]['searchid'] = []

general = ConfigSectionMap('General')
for movie in movies.json():
    for name, server in servers.items():
        if 'movieFile' in movie:
            if 'mediaInfo' in movie['movieFile']:
                if 'audioLanguages' in movie['movieFile']['mediaInfo']:
                    if movie['movieFile']['mediaInfo']['audioLanguages'] is not str(""):
                        if str(general['language_required']) not in movie['movieFile']['mediaInfo']['audioLanguages'] and general['tmdb_check'] == str('ON'):
                            logging.debug('server: radarr{0}'.format(name))
                            logging.debug('title: {0}'.format(movie['title']))
                            logging.debug('titleSlug: {0}'.format(movie['titleSlug']))
                            images = movie['images']
                            for image in images:
                                image['url'] = '{0}'.format(image['url'])
                                logging.debug(image['url'])
                            logging.debug('tmdbId: {0}'.format(movie['tmdbId']))
                            logging.debug('monitored: {0}'.format(movie['monitored']))
                            logger.info('[radarr{0}]  {1}     {2} ({3}) - {4} - is missing {5} - has - {6}'.format(name, server['newMovies'], movie['title'], movie['year'], movie['tmdbId'], general['language_required'], movie['movieFile']['mediaInfo']['audioLanguages']))
                            logger.debug('Contains:                 {0}'.format(movie['movieFile']['mediaInfo']['audioLanguages']))
                            logging.info('TMDBID check is ON')
                            originalLanguage = session.get('https://api.themoviedb.org/3/movie/{0}?api_key={1}'.format(movie['tmdbId'], general['tmdb_key']))
                            if originalLanguage.status_code != 200:
                                logger.error('TMDB server error - response {1}'.format(originalLanguage.status_code))
                                sys.exit(0)
                            tmdbData = originalLanguage.json()
                            if isinstance(tmdbData, str):
                                logger.error('TMDB server error - respone {1}'.format(originalLanguage.status_code))
                                sys.exit(0)
                            logger.info('From TMDB: Origianl Langauge is {0}'.format(tmdbData['original_language']))
                            if tmdbData['original_language'] != general['language_iso']:
                                if general['remove_foreign'] == "true" or general['remove_foreign'] == "false":
                                    if general['remove_foreign'] == 'true':
                                        removeForeign = 'true'
                                        logger.info('SET: Removing all movies not released in or missing {0}'.format(general['language_required']))
                                    if general['remove_foreign'] == 'false':
                                        removeForeign = 'false'
                                        logger.info('SET: Only removing movies released in and missing {0}'.format(general['language_required']))
                                else:
                                    logger.error('Set remove_foreign in the config [true|false]')
                                    sys.exit(0)
                            server['newMovies'] += 1
                            if server['newMovies'] > 0:
                                if removeForeign == "false" and tmdbData['original_language'] == general['language_iso']:
                                    server['rmMovies']  += 1
                                    setDelete = "ON"
                                    logger.info('SET: DELETING MOVIE FILE - Total: {0}'.format(server['rmMovies']))
                                if removeForeign == "false" and tmdbData['original_language'] != general['language_iso']:
                                    setDelete = "ON"
                                    logger.info('SET: NOT DELETING MOVIE FILE')
                                if removeForeign == "true" and tmdbData['original_language'] == general['language_iso']:
                                    server['rmMovies']  += 1
                                    setDelete = "ON"
                                    logger.info('SET: DELETING MOVIE FILE - Total: {0}'.format(server['rmMovies']))
                                if removeForeign == "true" and tmdbData['original_language'] != general['language_iso']:
                                    server['rmMovies']  += 1
                                    setDelete = "ON"
                                    logger.info('SET: DELETING MOVIE FILE - Total: {0}'.format(server['rmMovies']))
                            if args.whatif:
                                logging.info('WhatIf: Not actually removing media from radarr{0}.'.format(name))
                                logging.debug('WhatIf: Sleeping for: {0} seconds.'.format(general['wait_between_add']))
                                time.sleep(int(general['wait_between_add']))
                            else:
                                if setDelete == "ON":
                                    logger.info('DELETE TRIGGERED')
                                else:
                                    if setDelete != "ON" or setDelete != "OFF":
                                        logging.error('setDelete failed to be set')
                            logging.debug('{0} seconds sleep.'.format(general['wait_between_add']))
                            time.sleep(int(general['wait_between_add']))

                        else:
                            logging.debug('[radarr{0}]  {1} ({2}) contains {3}'.format(name, movie['title'], movie['year'], general['language_required']))
                            logging.debug('Contains:            {0}'.format(movie['movieFile']['mediaInfo']['audioLanguages']))

for name, server in servers.items():
    if len(server['searchid']):
        payload = {'name' : 'MoviesSearch', 'movieIds' : server['searchid']}
        session.post('{0}/api/command?apikey={1}'.format(server['url'], server['key']),data=json.dumps(payload))
