import asyncio
from multiprocessing import set_start_method, Pipe, Process, Queue
from multiprocessing.connection import Connection
from typing import Optional
import pathlib
import signal

import modules.config as cfg

from logging import getLogger

from .bot_client import run_client
from ..plugin import Plugin, PluginDisabled

log = getLogger("pog_bot")


def has_sound_file(name: str) -> bool:
    return f"{name}_sound" in cfg.discord


def get_sound_file(name: str) -> str:
    return cfg.discord[f"{name}_sound"]


class TeamAudioBot:
    _bot: Optional[Process] = None
    _pipe: Optional[Connection] = None
    _bot_pipe: Optional[Connection] = None
    _queue: Queue = None
    _team_id: int
    _token: str

    def __init__(self, team_id: int, token: str):
        self._team_id = team_id
        self._token = token

    def start(self):
        log.info(f"Starting TeamAudioBot({self._team_id})")
        self.stop()
        self._bot_pipe, self._pipe = Pipe(duplex=False)
        self._queue = Queue()
        self._bot = Process(
            daemon=True,
            target=run_client,
            args=(self._team_id, self._token, self._queue, self._bot_pipe),
        )
        self._bot.start()
        log.info(f"Started TeamAudioBot({self._team_id})")

    def stop(self, immediate=False):
        if self._bot != None:
            self._pipe.send(True)
            if not immediate:
                self._bot.join(2)
            if self._bot.exitcode is None:
                self._bot.kill()

        self._bot = None
        self._bot_pipe = None
        self._pipe = None
        self._queue = None

    def disconnect_voice(self):
        if self._bot != None:
            self._queue.put(0)

    def play_sound(self, channel_id: int, file_path: str):
        log.info(f"TeamAudioBot({self._team_id}) sending file: {file_path}")
        if not file_path:
            log.info(
                f"TeamAudioBot({self._team_id}) skipping missing file: {file_path}"
            )
            return

        if not pathlib.Path(file_path).is_file():
            log.info(f"TeamAudioBot({self._team_id}) invalid file: {file_path}")
            return

        if self._bot == None:
            log.info(f"TeamAudioBot({self._team_id}) starting before send: {file_path}")
            self.start()

        self._queue.put((channel_id, file_path))
        log.info(f"TeamAudioBot({self._team_id}) sent: {file_path}")


class GameObj:
    faction: str
    id: int

    def __init__(self, faction: str, id: int):
        self.faction = faction
        self.id = id


class DiscordLobbyAudio(Plugin):
    _round_no_override: Optional[int]
    _team_1_bot: Optional[TeamAudioBot]
    _team_2_bot: Optional[TeamAudioBot]

    def __init__(self, match):
        super().__init__(match)
        if not cfg.discord["team_1_token"] or not cfg.discord["team_2_token"]:
            raise PluginDisabled("Missing discord audio bot token!")

        self._round_no_override = None
        self._team_1_bot = None
        self._team_2_bot = None
        self.restart()

    def stop(self, immediate=False):
        if self._team_1_bot is not None:
            self._team_1_bot.stop(immediate)
            self._team_1_bot = None
        if self._team_2_bot is not None:
            self._team_2_bot.stop(immediate)
            self._team_1_bot = None

    def restart(self):
        self.stop(False)
        if not cfg.discord["team_1_token"] or not cfg.discord["team_2_token"]:
            raise PluginDisabled("Missing discord audio bot token!")

        log.info("Loading discord lobby audio plugin...")
        self._team_1_bot = TeamAudioBot(1, cfg.discord["team_1_token"])
        self._team_2_bot = TeamAudioBot(2, cfg.discord["team_2_token"])
        log.info("Creating TeamAudioBot instances...")
        self._team_1_bot.start()
        self._team_2_bot.start()
        log.info("Discord audio bot processes ready!")

    async def simulate_match(self):
        self._round_no_override = None
        self.on_match_launching()
        log.info("Simulating:")

        log.info("Captain selection.")
        await asyncio.sleep(5)
        self.on_captains_selected()

        log.info("Team selection.")
        await asyncio.sleep(5)
        self.on_teams_done()

        log.info("Faction selection.")
        await asyncio.sleep(5)
        self.on_faction_pick(GameObj(cfg.i_factions["NC"], 0))
        await asyncio.sleep(3)
        self.on_faction_pick(GameObj(cfg.i_factions["TR"], 1))

        log.info("Base selection.")
        await asyncio.sleep(2)
        self.on_factions_picked()
        await asyncio.sleep(5)
        self.on_base_selected(GameObj("", cfg.base_to_id["chac"]))

        log.info("Teams readying.")
        await asyncio.sleep(10)
        self.on_team_ready(GameObj("", 0))
        await asyncio.sleep(3)
        self.on_team_ready(GameObj("", 1))

        log.info("Match starting.")
        await asyncio.sleep(3)
        self.on_match_starting()
        await asyncio.sleep(30)

        log.info("Round finishing.")
        self._round_no_override = 1
        self.on_round_over()
        await asyncio.sleep(2)

        log.info("Second round starting.")
        self.on_match_starting()
        await asyncio.sleep(30)

        log.info("Second round finishing.")
        self._round_no_override = 2
        self.on_round_over()
        self._round_no_override = None

        log.info("Match finishing.")
        await asyncio.sleep(2)
        self.on_match_over()

    def on_match_launching(self):
        self._play_lobby_sound("lobby_ready")

    def on_captains_selected(self):
        self._play_lobby_sound("select_teams")

    def on_teams_done(self):
        self._play_lobby_sound("select_factions")

    def on_faction_pick(self, team):
        self._play_lobby_sound(
            f"team_{team.id + 1}_picked_{cfg.factions[team.faction]}_faction"
        )

    def on_factions_picked(self):
        if not self.match.base:
            self._play_lobby_sound("select_base")

    def on_base_selected(self, base):
        self._play_sound_all("base_selected")
        specific_base_sound = f"picked_base_{cfg.id_to_base[base.id]}"
        generic_base_sound = "unknown_base"

        if has_sound_file(specific_base_sound):
            self._play_sound_all(specific_base_sound)
        else:
            self._play_sound_all(generic_base_sound)

        self._play_sound_all("ready_prompt")

    def on_team_ready(self, team):
        self._play_sound_all(f"team_{team.id + 1}_ready")

    def on_match_starting(self):
        loop = asyncio.get_event_loop()
        loop.create_task(self._enqueue_match_starting_sounds())

    async def _enqueue_match_starting_sounds(self):
        self._play_sound_all("starts_in_30")
        await asyncio.sleep(20)
        self._play_sound_all("starts_in_10")
        await asyncio.sleep(5)
        self._play_sound_all("starts_in_5")

    def on_round_over(self):
        self._play_sound_all("round_over")
        round_no = self._round_no_override
        if round_no is None:
            round_no = self.match.round_no

        if round_no == 1:
            self._play_sound_all("switch_sides")
            self._play_sound_all("ready_prompt")

    def on_match_over(self):
        self._play_sound_all("match_over")
        self._team_1_bot.disconnect_voice()
        self._team_2_bot.disconnect_voice()

    def on_clean(self):
        self._team_1_bot.disconnect_voice()
        self._team_2_bot.disconnect_voice()

    def async_clean(self):
        self.on_clean()

    def _play_lobby_sound(self, sound_name: str):
        sound_file = get_sound_file(sound_name)
        self._team_1_bot.play_sound(cfg.discord["lobby_voice_channel"], sound_file)

    def _play_sound_all(self, sound_name: str):
        sound_file = get_sound_file(sound_name)
        self._team_1_bot.play_sound(cfg.discord["team_1_voice_channel"], sound_file)
        self._team_2_bot.play_sound(cfg.discord["team_2_voice_channel"], sound_file)

    def _play_team_sound(self, team_id: int, sound_name: str):
        sound_file = get_sound_file(sound_name)
        if team_id == 1:
            self._team_1_bot.play_sound(cfg.discord["team_1_voice_channel"], sound_file)
        else:
            self._team_2_bot.play_sound(cfg.discord["team_2_voice_channel"], sound_file)
