import asyncio
import queue
import signal
from asyncio import sleep
from discord import Client, Intents, FFmpegPCMAudio
from pathlib import Path
from logging import getLogger
from multiprocessing import Queue
from multiprocessing.connection import Connection


def log(team_id: int, msg: str):
    print(f"Bot({team_id}) {msg}")


def run_client(team_id: int, token: str, tasks: Queue, conn: Connection):
    """
    Runs a discord bot for sending audio to a voice channel

    Parameters
    ----------
    team_id : int
        Numeric team ID the bot represents, generally either 1 or 2.
    token : str
        Bot token to use when creating the client.
    tasks : Queue
        multiprocessing.Queue used to communicate sound files to play.
        If the integer 0 is received as a queue item, it will instead
        stop playback and disconnect from voice. Otherwise, it expects
        a two-item tuple of (channel_id_int, sound_file_path_string)
    conn : Connection
        Used as a shutdown signal for the bot. Any truthy value will cause
        the bot to disconnect and close the client.
    """
    if not token:
        log(team_id, "Missing token.")
        return

    if not tasks:
        log(team_id, "Missing tasks.")
        return

    if not conn:
        log(team_id, "Missing conn.")
        return

    log(team_id, "Initializing discord bot...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def stop(_signum, _frame):
        loop.close()
        loop.stop()

    loop.add_signal_handler(signal.SIGINT, stop)
    loop.add_signal_handler(signal.SIGTERM, stop)

    intents = Intents.all()
    client = Client(intents=intents)

    @client.event
    async def on_ready():
        log(team_id, "Bot is ready!")
        voice_channel = None
        voice_client = None

        async def disconnect():
            nonlocal voice_channel
            nonlocal voice_client
            if voice_client is not None:
                if voice_client.is_connected():
                    if voice_client.is_playing():
                        voice_client.stop()
                    await voice_client.disconnect()
                voice_client = None
                voice_channel = None

        try:
            while not client.is_closed():
                if conn.poll():
                    log(team_id, "Stopping")
                    break

                await asyncio.sleep(0.5)

                try:
                    payload = tasks.get_nowait()
                except queue.Empty:
                    continue

                if payload == 0:
                    await disconnect()
                    continue

                channel_id, sound_file = payload

                if voice_client is not None and not voice_client.is_connected():
                    await disconnect()

                if voice_channel is None:
                    log(team_id, f"Joining channel: {channel_id}")
                    voice_channel = client.get_channel(channel_id)
                    try:
                        voice_client = await voice_channel.connect(
                            reconnect=True, timeout=10
                        )
                    except e:
                        log(team_id, f"Failed to connect to voice")
                        log(team_id, e)
                        continue
                elif voice_channel.id != channel_id:
                    log(f"Moving to channel: {channel_id}")
                    voice_channel = client.get_channel(channel_id)
                    await voice_client.move_to(voice_channel)

                if voice_client.is_playing():
                    voice_client.stop()

                log(team_id, "Playing sound: {sound_file}")
                audio_source = FFmpegPCMAudio(sound_file)
                voice_client.play(audio_source)
                while voice_client.is_playing():
                    if conn.poll():
                        print(team_id, "Stopping while playing")
                        await disconnect()
                        await client.close()
                        break
                    await asyncio.sleep(0.5)
        finally:
            if not client.is_closed():
                await client.close()

    loop.run_until_complete(client.start(token))
    loop.run_forever()
