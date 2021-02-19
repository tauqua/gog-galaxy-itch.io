import asyncio
import datetime
import json
import logging
from pathlib import Path
import sys
import re
import os
import time
from typing import List, Dict, Union, Optional

from aiohttp.client_exceptions import ClientResponseError

from galaxy.api.plugin import Plugin, create_and_run_plugin
from galaxy.api.consts import Platform, LicenseType, OSCompatibility
from galaxy.api.types import NextStep, Authentication, Game, LicenseInfo
from galaxy.api.errors import AuthenticationRequired, AccessDenied, InvalidCredentials

from http_client import HTTPClient

with open(Path(__file__).parent / 'manifest.json', 'r') as f:
    __version__ = json.load(f)['version']

# Set this to "true" to check games against IGDB and find out which ones don't have data (may show up as "Unknown game."
# The results get logged to unknown-games.txt, in the same directory as this file.
CHECK_GAMES_AGAINST_IGDB = False
GOG_GAME_URL = "https://gamesdb.gog.com/platforms/itch/external_releases/{}"

# IGDB states the rate limit is 4 requests per second. To be safe, buffer to 0.5s between requests.
GOG_API_RATE_LIMIT_SECONDS = 0.5

class ItchIntegration(Plugin):
    def __init__(self, reader, writer, token):
        super().__init__(
            Platform.ItchIo,
            __version__,
            reader,
            writer,
            token
        )
        self.http_client = HTTPClient(self.store_credentials)
        self.session_cookie = None

    async def shutdown(self):
        await self.http_client.close()

    # implement methods
    async def authenticate(self, stored_credentials=None):
        logging.debug("authenticate")
        confirmation_uri = 'https://itch.io/user/oauth?client_id=3821cecdd58ae1a920be15f6aa479f7e&scope=profile&response_type=token&redirect_uri=http%3A%2F%2F127.0.0.1%3A7157%2Fgogg2itchintegration'
        if not stored_credentials:
            return NextStep("web_session", {
                "window_title": "Log in to Itch.io",
                "window_width": 536,
                "window_height": 675,
                "start_uri": confirmation_uri,
                "end_uri_regex": r"^(http://127\.0\.0\.1:7157/gogg2itchintegration#access_token=.+)",
            }, js={r'^https://itch\.io/my-feed.*': [f'window.location = "{confirmation_uri}"']})
        else:
            self.http_client.update_cookies(stored_credentials)
            try:
                user = await self.get_user_data()
                return Authentication(str(user.get("id")), str(user.get("username")))
            except AccessDenied:
                raise InvalidCredentials()


    async def pass_login_credentials(self, step, credentials, cookies):
        session_cookies = {cookie['name']: cookie['value'] for cookie in cookies if cookie['name']}
        self.http_client.update_cookies(session_cookies)

        user = await self.get_user_data()
        logging.debug(type(id))
        logging.debug(user.get("id"))
        logging.debug(user.get("username"))
        return Authentication(str(user.get("id")), str(user.get("username")))

    async def get_owned_games(self):
        page = 1
        games = []
        while True:
            try:
                resp = await self.http_client.get(f"https://api.itch.io/profile/owned-keys?classification=game&page={page}")
            except AuthenticationRequired:
                self.lost_authentication()
                raise
            if len(resp.get("owned_keys")) == 0:
                return games
            await self.parse_json_into_games(resp.get("owned_keys"), games)
            page += 1
        return games

    async def get_user_data(self):
        resp = await self.http_client.get(f"https://api.itch.io/profile?")
        self.authenticated = True
        return resp.get("user")

    async def parse_json_into_games(self, resp, games):
        for key in resp:
            game = key.get("game")
            if not game.get("classification") == "game":
                continue
            game_name = game.get("title")
            game_num = str(game.get("id"))
            logging.debug('Parsed %s, %s', game_name, game_num)
            self.persistent_cache[game_num] = game
            this_game = Game(
                game_id=game_num,
                game_title=game_name,
                license_info=LicenseInfo(LicenseType.SinglePurchase),
                dlcs=[])
            games.append(this_game)
            
            if CHECK_GAMES_AGAINST_IGDB:
                itch_id = game.get("id")
                game_gog_url = GOG_GAME_URL.format(itch_id)
                start_time = time.time()
                
                try:
                    json_response = await self.http_client.get(game_gog_url)
                    if "error" in json_response:
                        log_unknown_game("No IGDB data found for {} (itch.io game ID is {})".format(game_name, itch_id))
                        
                except ClientResponseError as e:
                    log_unknown_game("No IGDB data found for {}: {}".format(game_name, e))
                
                stop_time = time.time()
                elapsed_seconds = stop_time - start_time
                if elapsed_seconds <= GOG_API_RATE_LIMIT_SECONDS:
                    diff_seconds = GOG_API_RATE_LIMIT_SECONDS - elapsed_seconds
                    await asyncio.sleep(diff_seconds)
                

    async def get_os_compatibility(self, game_id, context):
        try:
            compat = self.persistent_cache[str(game_id)].get("traits")
            os = (OSCompatibility.Windows if "p_windows" in compat else OSCompatibility(0)) | (OSCompatibility.MacOS if "p_osx" in compat else OSCompatibility(0)) | (OSCompatibility.Linux if "p_linux" in compat else OSCompatibility(0))
            logging.debug("Compat value: %s", os)
            if not os == 0:
                return os
        except KeyError:
            logging.error("Key not found in cache: %s", game_id)

def main():
    create_and_run_plugin(ItchIntegration, sys.argv)


# run plugin event loop

def log(msg):
    # return
    log = open(os.path.join(os.path.dirname(__file__), "log2.txt"), "a", encoding="utf-8")
    log.write(str(msg) + "\n")
    log.close()

def log_unknown_game(message):
    log = open(os.path.join(os.path.dirname(__file__), "unknown-games.txt"), "a", encoding="utf-8")
    log.write("{} | {}\n".format(datetime.datetime.now().isoformat(), message))
    log.close()

    
if __name__ == "__main__":
    main()
