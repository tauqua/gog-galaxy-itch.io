import json
import logging
from pathlib import Path
import sys
import re
import os
from typing import List, Dict, Union, Optional

from galaxy.api.plugin import Plugin, create_and_run_plugin
from galaxy.api.consts import Platform, LicenseType
from galaxy.api.types import NextStep, Authentication, Game, LicenseInfo
from galaxy.api.errors import AuthenticationRequired, AccessDenied, InvalidCredentials

from http_client import HTTPClient

with open(Path(__file__).parent / 'manifest.json', 'r') as f:
    __version__ = json.load(f)['version']

AUTH_PARAMS = {
    "window_title": "Log in to Itch.io",
    "window_width": 536,
    "window_height": 675,
    "start_uri": r"https://itch.io/user/oauth?client_id=9a47359f7cba449ace3ba257cfeebc17&scope=profile&response_type=token&redirect_uri=http%3A%2F%2F127.0.0.1%3A7157%2Fgogg2itchmatcher",
    "end_uri_regex": r"^http://127\.0\.0\.1:7157/gogg2itchmatcher#access_token=.+",
}

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
        if not (stored_credentials.get("access_token") if stored_credentials else None):
            return NextStep("web_session", {
                "window_title": "Log in to Itch.io",
                "window_width": 536,
                "window_height": 675,
                "start_uri": r"https://itch.io/user/oauth?client_id=9a47359f7cba449ace3ba257cfeebc17&scope=profile&response_type=token&redirect_uri=http%3A%2F%2F127.0.0.1%3A7157%2Fgogg2itchmatcher",
                "end_uri_regex": r"^http://127\.0\.0\.1:7157/gogg2itchmatcher#access_token=.+",
            })
        else:
            try:
                user = await self.get_user_data(stored_credentials["access_token"])

                return Authentication(user["id"], user["username"])
            except AccessDenied:
                raise InvalidCredentials()


    async def pass_login_credentials(self, step: str, credentials: Dict[str, str], cookies: List[Dict[str, str]]) -> \
            Union[NextStep, Authentication]:
        session_cookies = {cookie['name']: cookie['value'] for cookie in cookies if cookie['name']}
        self.http_client.update_cookies(session_cookies)
        api_key = re.search(r"^http://127\.0\.0\.1:7157/gogg2itchmatcher#access_token=(.+)", credentials["end_uri"])
        key = api_key.group(1)
        self.store_credentials({"access_token": key})

        user = await self.get_user_data(key)
        return Authentication(user["id"], user["username"])

    async def get_owned_games(self):
        page = 1
        games = []
        while True:
            try:
                resp = await self.http_client.get(f"https://api.itch.io/profile/owned-keys?page={page}")
            except AuthenticationRequired:
                self.lost_authentication()
                raise
            if len(resp.get("owned_keys")) == 0:
                return games
            self.parse_json_into_games(resp.get("owned_keys"), games)
            page += 1
        return games

    async def get_user_data(self, api_key):
        resp = await self.http_client.get(f"https://itch.io/api/1/{api_key}/me")
        self.authenticated = True
        return resp.get("user")

    @staticmethod
    def parse_json_into_games(resp, games):
        for key in resp:
            game = key.get("game")
            if not game.get("classification") == "game":
                continue
            game_name = game.get("title")
            game_href = game.get("url")
            url_slug = str(game_href.split('itch.io/')[-1])
            logging.debug('Parsed %s, %s', game_name, url_slug)
            games.append(Game(
                game_id=url_slug,
                game_title=game_name,
                license_info=LicenseInfo(LicenseType.SinglePurchase),
                dlcs=[])
            )


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
