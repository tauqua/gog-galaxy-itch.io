import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
import queue
from typing import List, Optional

from galaxy.api.consts import LicenseType, LocalGameState
from galaxy.api.types import LocalGame, Game, LicenseInfo, GameTime

if sys.platform.startswith("darwin"):
    ITCH_DB_PATH = os.path.expanduser("~/Library/Application Support/itch/db/butler.db")
else:
    ITCH_DB_PATH = os.path.join(os.getenv("appdata"), "itch/db/butler.db")


class localClientDbReader():
    async def get_owned_games(self) -> List[Game]:
        return await self.get_games()

    async def get_games(self):
        logging.debug("Opening connection to itch butler.db")
        self.itch_db = sqlite3.connect(ITCH_DB_PATH)
        self.itch_db_cursor = self.itch_db.cursor()
        resp = list(self.itch_db_cursor.execute("SELECT * FROM games WHERE classification = 'game'"))
        downloaded = [x[0] for x in list(self.itch_db_cursor.execute("SELECT game_id FROM caves"))]
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

        self.mylocal_game_ids = [x.game_id for x in games]

        logging.debug("Finished building games")

        return games


    async def check_for_new_games(self):
        logging.debug("Checking for changes in the itch butler.db")
        self.checking_for_new_games = True
        games_before = self.mylocal_game_ids[:]
        games_after = await self.get_games()
        ids_after = [x.game_id for x in games_after]
        for game in games_after:
            if game.game_id not in games_before:
                self.updateQueue_add_game.put(game)
                self.my_queue_update_local_game_status.put(LocalGame(game_id=game.game_id, local_game_state=LocalGameState.Installed))
                logging.debug(f"Game {game.game_id} ({game.game_title}) is new, adding to galaxy...")

        for game in games_before:
            if game not in ids_after:
                self.updateQueue_remove_game.put(game)
                logging.debug(f"Game {game} seems to be uninstalled, removing from galaxy...")

        self.checking_for_new_games = False

        logging.debug("Finished checking for changes in the itch butler.db")

    async def get_local_games(self) -> List[LocalGame]:
        # all available games are installed, so we convert the Game list to a LocalGame list
        games = await self.get_games()
        local_games = []
        for game in games:
            local_games.append(LocalGame(game_id=game.game_id, local_game_state=LocalGameState.Installed))

        return local_games

    async def launch_game(self, game_id: str) -> None:
        logging.debug("query db")
        self.itch_db = sqlite3.connect(ITCH_DB_PATH)
        self.itch_db_cursor = self.itch_db.cursor()
        resp = json.loads(list(self.itch_db_cursor.execute("SELECT verdict FROM caves WHERE game_id=? LIMIT 1", [game_id]))[0][0])
        self.itch_db.close()
        
        logging.info("building")
        start = int(time.time())
        logging.info(resp["basePath"])
        logging.info(resp["candidates"][0]["path"])
        my_full_path=os.path.join(resp["basePath"], resp["candidates"][0]["path"])
        my_base_path=os.path.split(my_full_path)[0]
        #proc = await os.system("%windir%\\Sysnative\\cmd.exe /c \""+os.path.join(resp["basePath"], resp["candidates"][0]["path"])+"\"")
        #proc = await asyncio.create_subprocess_shell("%windir%\\Sysnative\\cmd.exe /c \""+os.1path.join(resp["basePath"], resp["candidates"][0]["path"])+"\"")
        my_command = "%windir%\\Sysnative\\cmd.exe /c \"cd /d \""+my_base_path+"\" && \""+my_full_path+"\"\""
        logging.info(my_command)
        proc = await asyncio.create_subprocess_shell(
            my_command
        )

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
        return GameTime(
            game_id=game_id,
            time_played=None,
            last_played_time=None,
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

    def __init__(self):
        self.authenticated = False

        self.itch_db = None
        self.itch_db_cursor = None

        self.checking_for_new_games = False

        self.mylocal_game_ids = []
        
        self.updateQueue_add_game = queue.Queue()
        self.updateQueue_remove_game = queue.Queue()
        self.my_queue_update_local_game_status = queue.Queue()

# run plugin event loop

