import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import traceback
import re
from typing import List, Dict, Union

from galaxy.http import create_client_session

from galaxy.api.errors import AccessDenied, InvalidCredentials, AuthenticationRequired
from galaxy.api.plugin import Plugin, create_and_run_plugin
from galaxy.api.consts import Platform, LicenseType, LocalGameState
from galaxy.api.types import NextStep, Authentication, LocalGame, Game, LicenseInfo

ITCH_DB_PATH = os.path.join(os.getenv("appdata"), "itch/db/butler.db")


class ItchIntegration(Plugin):
    async def get_owned_games(self) -> List[Game]:
        return await self.get_games()

    async def get_games(self):
        log(ITCH_DB_PATH)
        self.itch_db = sqlite3.connect(ITCH_DB_PATH)
        self.itch_db_cursor = self.itch_db.cursor()
        resp = list(self.itch_db_cursor.execute("SELECT * FROM games"))
        downloaded = [x[0] for x in list(self.itch_db_cursor.execute("SELECT game_id FROM downloads"))]
        self.itch_db.close()

        games = []

        for game in resp:
            if game[0] not in downloaded:
                continue
            can_be_bought = True if game[11] == 1 else False
            min_price = game[10]
            license_type = LicenseType.FreeToPlay
            if can_be_bought and min_price > 0:
                license_type = LicenseType.SinglePurchase
            games.append(Game(game_id=game[0], game_title=game[2], dlcs=None, license_info=LicenseInfo(license_type)))

        self.game_ids = [x.game_id for x in games]

        return games

    async def get_user_data(self, api_key):
        resp = await self._session.request("GET", f"https://itch.io/api/1/{api_key}/me")
        data = await resp.json()
        self.authenticated = True
        return data.get("user")

    async def pass_login_credentials(self, step: str, credentials: Dict[str, str], cookies: List[Dict[str, str]]) -> \
            Union[NextStep, Authentication]:
        api_key = re.search(r"^http://127\.0\.0\.1:7157/gogg2itchmatcher#access_token=(.+)", credentials["end_uri"])
        key = api_key.group(1)
        log(key)
        self.store_credentials({"access_token": key})

        user = await self.get_user_data(key)

        return Authentication(user["id"], user["username"])

    async def check_for_new_games(self):
        self.checking_for_new_games = True
        games_before = self.game_ids[:]
        games_after = await self.get_games()
        ids_after = [x.game_id for x in games_after]
        for game in games_after:
            if game.game_id not in games_before:
                self.add_game(game)

        for game in games_before:
            if game not in ids_after:
                self.remove_game(game)

        self.checking_for_new_games = False


    def tick(self) -> None:
        self.create_task(self.check_for_new_games(), "cfng")

    async def get_local_games(self) -> List[LocalGame]:
        # all available games are installed, so we convert the Game list to a LocalGame list
        games = await self.get_games()
        local_games = []
        for game in games:
            local_games.append(LocalGame(game_id=game.game_id, local_game_state=LocalGameState.Installed))

        return local_games

    async def launch_game(self, game_id: str) -> None:
        self.itch_db = sqlite3.connect(ITCH_DB_PATH)
        self.itch_db_cursor = self.itch_db.cursor()
        resp = json.loads(list(self.itch_db_cursor.execute("SELECT verdict FROM caves WHERE game_id=? LIMIT 1", [game_id]))[0][0])
        self.itch_db.close()

        subprocess.Popen(os.path.join(resp["basePath"], resp["candidates"][0]["path"]))

    async def uninstall_game(self, game_id: str) -> None:
        pass

    def __init__(self, reader, writer, token):
        super().__init__(
            Platform.ItchIo,  # Choose platform from available list
            "0.1",  # Version
            reader,
            writer,
            token
        )
        self._session = create_client_session()
        self.authenticated = False

        self.itch_db = None
        self.itch_db_cursor = None

        self.checking_for_new_games = False

        self.game_ids = []

    # implement methods
    async def authenticate(self, stored_credentials=None):
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


def main():
    create_and_run_plugin(ItchIntegration, sys.argv)


# run plugin event loop

def log(msg):
    return
    log = open(os.path.join(os.path.dirname(__file__), "log2.txt"), "a")
    log.write(str(msg) + "\n")
    log.close()


if __name__ == "__main__":
    log = open(os.path.join(os.path.dirname(__file__), "log.txt"), "w")
    try:
        main()
    except:
        traceback.print_exc(file=log)
    finally:
        log.close()
