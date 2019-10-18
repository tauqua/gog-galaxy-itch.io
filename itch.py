import asyncio
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
import traceback
import re
from typing import List, Dict, Union, Optional

from galaxy.http import create_client_session

from galaxy.api.errors import AccessDenied, InvalidCredentials, AuthenticationRequired
from galaxy.api.plugin import Plugin, create_and_run_plugin
from galaxy.api.consts import Platform, LicenseType, LocalGameState
from galaxy.api.types import NextStep, Authentication, LocalGame, Game, LicenseInfo, GameTime

ITCH_DB_PATH = os.path.join(os.getenv("appdata"), "itch/db/butler.db")


class ItchIntegration(Plugin):
    async def get_owned_games(self) -> List[Game]:
        return await self.get_games()

    async def get_games(self):
        logging.debug("Opening connection to itch butler.db")
        self.itch_db = sqlite3.connect(ITCH_DB_PATH)
        self.itch_db_cursor = self.itch_db.cursor()
        resp = list(self.itch_db_cursor.execute("SELECT * FROM games"))
        downloaded = [x[0] for x in list(self.itch_db_cursor.execute("SELECT game_id FROM downloads"))]
        self.itch_db.close()
        logging.debug("Closing connection to itch butler.db")

        games = []

        logging.debug("Starting building games...")

        for game in resp:
            logging.debug(f"Building game {game[0]} ({game[2]})")
            if game[0] not in downloaded:
                logging.debug(f"Game {game[0]} ({game[2]}) seems to be only cached, skipping...")
                continue
            can_be_bought = True if game[11] == 1 else False
            min_price = game[10]
            license_type = LicenseType.FreeToPlay
            if can_be_bought and min_price > 0:
                license_type = LicenseType.SinglePurchase
            games.append(Game(game_id=game[0], game_title=game[2], dlcs=None, license_info=LicenseInfo(license_type)))
            logging.debug(f"Built {game[0]} ({game[2]})")

        self.game_ids = [x.game_id for x in games]

        logging.debug("Finished building games")

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
        logging.debug("Checking for changes in the itch butler.db")
        self.checking_for_new_games = True
        games_before = self.game_ids[:]
        games_after = await self.get_games()
        ids_after = [x.game_id for x in games_after]
        for game in games_after:
            if game.game_id not in games_before:
                self.add_game(game)
                logging.debug(f"Game {game.game_id} ({game.game_title}) is new, adding to galaxy...")

        for game in games_before:
            if game not in ids_after:
                self.remove_game(game)
                logging.debug(f"Game {game} seems to be uninstalled, removing from galaxy...")

        self.checking_for_new_games = False

        logging.debug("Finished checking for changes in the itch butler.db")


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

        start = int(time.time())
        proc = await asyncio.create_subprocess_shell(os.path.join(resp["basePath"], resp["candidates"][0]["path"]))

        await proc.communicate() # wait till terminates
        end = int(time.time())

        session_mins_played = int((end - start) / 60) # secs to mins
        time_played = (self._get_time_played(game_id) or 0) + session_mins_played
        game_time = GameTime(game_id=game_id, time_played=time_played, last_played_time=end)
        self.update_game_time(game_time)

        # store updated times
        self.persistent_cache[self._time_played_key(game_id)] = str(time_played)
        self.persistent_cache[self._last_played_time_key(game_id)] = str(end)
        self.push_cache()

    async def get_game_time(self, game_id: str, context: None) -> GameTime:
        """Blep

        :param game_id: the id of the game for which the game time is returned
        :param context: the value returned from :meth:`prepare_game_times_context`
        :return: GameTime object
        """
        return GameTime(
            game_id=game_id,
            time_played=None,#self._get_time_played(game_id),
            last_played_time=None,#self._get_last_played_time(game_id),
        )

    def _get_time_played(self, game_id: str) -> Optional[int]:
        key = self._time_played_key(game_id)
        return int(self.persistent_cache[key]) if key in self.persistent_cache else None

    def _get_last_played_time(self, game_id: str) -> Optional[int]:
        key = self._last_played_time_key(game_id)
        return int(self.persistent_cache[key]) if key in self.persistent_cache else None

    @staticmethod
    def _time_played_key(game_id: str) -> str:
        return f'time{game_id}'

    @staticmethod
    def _last_played_time_key(game_id: str) -> str:
        return f'last{game_id}'

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
