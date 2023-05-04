from .logger import SimpleLogger
from .ts3_interface import AudioBot
from .discord_audio.discord_lobby_audio import DiscordLobbyAudio
from .plugin import PluginDisabled
from logging import getLogger
import modules.config as cfg

_plugins = {
    "SimpleLogger": SimpleLogger,
    "TS3Audio": AudioBot,
    # "DiscordAudio": DiscordLobbyAudio,
}

log = getLogger("pog_bot")


class VirtualAttribute:
    def __init__(self, manager, name):
        self.manager = manager
        self.name = name

    def __call__(self, *args, **kwargs):
        self.manager.on_event(self.name, *args, **kwargs)


class PluginManager:
    def __init__(self, match):
        plugins_enabled = True
        self.match = match
        self._plugins = {}
        if plugins_enabled:
            for name, Plug in _plugins.items():
                try:
                    self._plugins[name] = Plug(self.match)
                except PluginDisabled as e:
                    log.warning(f"Could not start plugin '{name}'\n{e}")

    def on_event(self, event, *args, **kwargs):
        for name, p in self._plugins.items():
            try:
                getattr(p, event)(*args, **kwargs)
            except Exception as e:
                log.error(f"Error occurred in plugin {name}\n{e}")

    async def async_clean(self):
        for name, p in self._plugins.items():
            try:
                await p.async_clean()
            except Exception as e:
                log.error(f"Error occurred when clearing plugin {name}\n{e}")

    def get_plugin_by_name(self, name: str):
        return self._plugins.get(name)

    def __getattr__(self, item):
        return VirtualAttribute(self, item)
