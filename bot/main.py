# @CHECK 2.0 features OK

"""main.py

Initialize everything, attach the general handlers, run the client.
The application should be launched from this file
"""

# discord.py
from discord.ext import commands
from discord import Intents

# Other modules
from asyncio import sleep
from random import seed
from datetime import datetime as dt
import logging, logging.handlers, sys, os
from time import gmtime

# General Enum and Exceptions
from modules.tools import UnexpectedError

# Display
from display.strings import AllStrings as disp, views
from display.classes import ContextWrapper

# Custom modules
import modules.config as cfg
import modules.roles
import modules.jaeger_calendar
import modules.loader
import modules.lobby
import modules.database
import modules.message_filter
import modules.accounts_handler
import modules.signal
import modules.stat_processor
import modules.interactions

# Classes
from match.classes.match import Match
from classes import Player, Base, Weapon

log = logging.getLogger("pog_bot")

_interactions_handler = modules.interactions.InteractionHandler(None, views.accept_button, disable_after_use=False)


def _add_main_handlers(client):
    """_add_main_handlers, private function
        Parameters
        ----------
        client : discord.py bot
            Our bot object
    """

    try:
        # help command, works in all channels
        @client.command(aliases=['h'])
        @commands.guild_only()
        async def help(ctx):
            await disp.HELP.send(ctx)
    except commands.errors.CommandRegistrationError:
        log.warning("Skipping =help registration")

    # Slight anti-spam: prevent the user to input a command if the last one isn't yet processed
    # Useful for the long processes like ps2 api, database or spreadsheet calls
    @client.event
    async def on_message(message):
        await modules.message_filter.on_message(client, message)

    # Global command error handler
    @client.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.CommandNotFound):  # Unknown command
            if modules.loader.is_all_locked():
                await disp.BOT_IS_LOCKED.send(ctx)
                return
            await disp.INVALID_COMMAND.send(ctx)
            return
        if isinstance(error, commands.errors.CheckFailure):  # Unauthorized command
            cog_name = ctx.command.cog.qualified_name
            if cog_name == "admin":
                await disp.NO_PERMISSION.send(ctx, ctx.command.name)
                return
            try:
                channel_id = cfg.channels[cog_name]
                channel_str = ""
                if isinstance(channel_id, list):
                    channel_str = "channels " + \
                        ", ".join(f'<#{id}>' for id in channel_id)
                else:
                    channel_str = f'channel <#{channel_id}>'
                # Send the use back to the right channel
                await disp.WRONG_CHANNEL.send(ctx, ctx.command.name, channel_str)
            except KeyError:  # Should not happen
                await disp.UNKNOWN_ERROR.send(ctx, "Channel key error")
            return
        # These are annoying error generated by discord.py when user input quotes (")
        bl = isinstance(error, commands.errors.InvalidEndOfQuotedStringError)
        bl = bl or isinstance(error, commands.errors.ExpectedClosingQuoteError)
        bl = bl or isinstance(error, commands.errors.UnexpectedQuoteError)
        if bl:
            # Tell the user not to use quotes
            await disp.INVALID_STR.send(ctx, '"')
            return

        try:
            original = error.original
        except AttributeError:
            original = error

        if isinstance(original, UnexpectedError):
            log.error(str(error))
            await disp.UNKNOWN_ERROR.send(ctx, original.reason)
        else:
            # Print unhandled error
            log.error(str(error))
            await disp.UNKNOWN_ERROR.send(ctx, type(original).__name__)
        raise error

    @client.event
    async def on_member_join(member):
        player = Player.get(member.id)
        if not player:
            return
        await modules.roles.role_update(player)

    @client.event
    async def on_presence_update(before, after):
        if before.status != after.status:
            await on_status_update(after)

    # Status update handler (for inactivity)
    async def on_status_update(user):
        player = Player.get(user.id)
        if not player:
            return
        await modules.roles.role_update(player)


def _add_init_handlers(client):

    @_interactions_handler.callback('accept')
    async def on_rule_accept(player, interaction_id, interaction, interaction_values):
        user = interaction.user
        if modules.loader.is_all_locked():
            raise modules.interactions.InteractionNotAllowed
        # reaction to the rule message?
        p = Player.get(user.id)
        if not p:  # if new player
            # create a new profile
            p = Player(user.id, user.name)
            await modules.roles.role_update(p)
            await modules.database.async_db_call(modules.database.set_element, "users", p.id, p.get_data())
            await disp.REG_RULES.send(ContextWrapper.channel(cfg.channels["register"]),
                                      user.mention)
        else:
            await modules.roles.role_update(p)
            await modules.roles.role_update(p)

    @client.event
    async def on_ready():
        # Initialise matches channels
        Match.init_channels(client, cfg.channels["matches"])

        modules.roles.init(client)
        # Init signal handler
        modules.signal.init()

        # fetch rule message, remove all reaction but the bot's
        channel = client.get_channel(cfg.channels["rules"])
        msg = await channel.fetch_message(channel.last_message_id)
        if msg.author.id == client.user.id:
            ctx = _interactions_handler.get_new_context(msg)
            await disp.RULES.edit(ctx)
        else:
            ctx = _interactions_handler.get_new_context(channel)
            await disp.RULES.send(ctx)

        # Update all players roles
        for p in Player.get_all_players_list():
            await modules.roles.role_update(p)
        _add_main_handlers(client)

        if not modules.lobby.get_all_names_in_lobby():
            try:
                last_lobby = modules.database.get_field("restart_data", 0, "last_lobby")
            except KeyError:
                pass
            else:
                for p_id in last_lobby:
                    try:
                        player = Player.get(int(p_id))
                        if player and not modules.lobby.is_lobby_stuck() and player.is_registered:
                            modules.lobby.add_to_lobby(player)
                    except ValueError:
                        pass
                modules.database.set_field("restart_data", 0, {"last_lobby": list()})
            names = modules.lobby.get_all_names_in_lobby()
            if names:
                await disp.LB_QUEUE.send(ContextWrapper.channel(cfg.channels["lobby"]),
                                         names_in_lobby=modules.lobby.get_all_names_in_lobby())
        modules.loader.unlock_all(client)
        log.info('Client is ready!')
        await disp.RDY.send(ContextWrapper.channel(cfg.channels["spam"]), cfg.VERSION)

    @client.event
    async def on_message(message):
        return


# TODO: testing, to be removed
def _test(client):
    from template_test_file import test_hand
    test_hand(client)


def _define_log(launch_str):
    # Logging config, logging outside the github repo
    try:
        os.makedirs('../../POG-data/logging')
    except FileExistsError:
        pass
    log_filename = '../../POG-data/logging/bot_log'
    logging.Formatter.converter = gmtime
    formatter = logging.Formatter('%(asctime)s | %(levelname)s %(message)s', "%Y-%m-%d %H:%M:%S UTC")
    # If test mode
    if launch_str == "_test":
        # Print debug
        level = logging.DEBUG
        # Print logging to console
        file_handler = logging.StreamHandler(sys.stdout)
    else:
        # Print info
        level = logging.INFO
        # Print to file, change file everyday at 12:00 UTC
        date = dt(2020, 1, 1, 12)
        file_handler = logging.handlers.TimedRotatingFileHandler(log_filename, when='midnight', atTime=date, utc=True)
    log.setLevel(level)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    class StreamToLogger(object):
        """
        Fake file-like stream object that redirects writes to a logger instance.
        """
        def __init__(self, logger, log_level=logging.INFO):
            self.logger = logger
            self.log_level = log_level
            self.linebuf = ''

        def write(self, buf):
            for line in buf.rstrip().splitlines():
                  self.logger.log(self.log_level, line.rstrip())

        def flush(self):
            pass

    # Redirect stdout and stderr to log:
    sys.stdout = StreamToLogger(log, logging.INFO)
    sys.stderr = StreamToLogger(log, logging.ERROR)

    log.addHandler(file_handler)


def main(launch_str=""):

    _define_log(launch_str)

    # Init order MATTERS

    log.info("Starting init...")

    # Get data from the config file
    cfg.get_config(launch_str)

    # Set up intents
    intents = Intents.none()
    intents.guilds = True
    intents.members = True
    intents.bans = False
    intents.emojis = False
    intents.integrations = False
    intents.webhooks = False
    intents.invites = False
    intents.voice_states = False
    intents.presences = True
    intents.messages = True
    # intents.guild_messages Activated by the previous one
    # intents.dm_messages Activated by the previous one
    intents.reactions = False
    # intents.guild_reactions
    # intents.dm_reactions
    intents.typing = False
    intents.guild_typing = False
    intents.dm_typing = False
    client = commands.Bot(command_prefix=cfg.general["command_prefix"], intents=intents)

    # Remove default help
    client.remove_command('help')

    # Initialise db and get all the registered users and all bases from it
    modules.database.init(cfg.database)
    modules.database.get_all_elements(Player.new_from_data, "users")
    modules.database.get_all_elements(Base, "static_bases")
    modules.database.get_all_elements(Weapon, "static_weapons")

    # Get Account sheet from drive
    modules.accounts_handler.init(cfg.GAPI_JSON)

    # Establish connection with Jaeger Calendar
    modules.jaeger_calendar.init(cfg.GAPI_JSON)

    # Initialise display module
    ContextWrapper.init(client)

    # Init lobby
    modules.lobby.init(Match, client)

    # Init stat processor
    modules.stat_processor.init()

    # Add init handlers
    _add_init_handlers(client)

    if launch_str == "_test":
        _test(client)

    # Add all cogs
    modules.loader.init(client)

    # Run server
    client.run(cfg.general["token"])


if __name__ == "__main__":
    # To run in 'DEV' mode, create a file called 'test' next to 'main.py'
    if os.path.isfile("test"):
        print("Running mode: 'DEV'")
        main("_test")
    else:
        print("Running mode: 'PROD', all output will be redirected to log files!\n"
              "Make sure to run in 'DEV' mode if you want debug output!"
              "Add a file called 'test' next to main.py to switch to 'DEV' mode")
        main()
