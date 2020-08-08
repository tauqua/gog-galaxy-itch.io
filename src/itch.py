import json
import logging
from pathlib import Path
import sys
import re
import os
from typing import List, Dict, Union, Optional

from galaxy.api.plugin import Plugin, create_and_run_plugin
from galaxy.api.consts import Platform, LicenseType, OSCompatibility
from galaxy.api.types import NextStep, Authentication, Game, LicenseInfo
from galaxy.api.errors import AuthenticationRequired, AccessDenied, InvalidCredentials

from http_client import HTTPClient

with open(Path(__file__).parent / 'manifest.json', 'r') as f:
    __version__ = json.load(f)['version']

KEYS_URL = 'https://api.itch.io/profile/owned-keys?page=%s'

HOMEPAGE = 'https://www.itch.io'


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
        if not stored_credentials:
            return NextStep("web_session", {
                "window_title": "Log in to Itch.io",
                "window_width": 536,
                "window_height": 675,
                "start_uri": r"https://itch.io/user/oauth?client_id=3821cecdd58ae1a920be15f6aa479f7e&scope=profile&response_type=token&redirect_uri=http%3A%2F%2F127.0.0.1%3A7157%2Fgogg2itchintegration",
                "end_uri_regex": r"^http://127\.0\.0\.1:7157/gogg2itchintegration#access_token=.+",
            })
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
            self.parse_json_into_games(resp.get("owned_keys"), games)
            page += 1
        return games

    async def get_user_data(self):
        resp = await self.http_client.get(f"https://api.itch.io/profile?")
        self.authenticated = True
        return resp.get("user")

    def parse_json_into_games(self, resp, games):
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
    log = open(os.path.join(os.path.dirname(__file__), "log2.txt"), "a")
    log.write(str(msg) + "\n")
    log.close()

if __name__ == "__main__":
    main()
