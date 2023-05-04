from logging import getLogger
from multiprocessing import Pipe, Process, Queue
from multiprocessing.connection import Connection
from typing import Optional
import pathlib

from .bot_client import run_client

log = getLogger("pog_bot")


class TeamAudioBot:
    """
    This class acts as an interface for communicating with a separate bot voice client
    process. The voice client is implemented in bot_client.py. This class provides
    convenience methods for starting, stopping, and otherwise controlling the client.
    """

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
