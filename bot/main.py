# @CHECK 2.0 features OK

"""main.py

Initialize everything, attach the general handlers, run the client.
The application should be launched from this file
"""

# discord.py
from discord.ext import commands
from discord import Status, DMChannel, Intents

# Other modules
from asyncio import sleep
from random import seed
from datetime import datetime as dt
from datetime import timezone as tz
import logging, logging.handlers, sys, os
from time import gmtime

# Custom modules
import modules.config as cfg
from display import send, SendCtx, init as display_init
from modules.spam import is_spam, unlock
from modules.enumerations import MatchStatus
from modules.exceptions import ElementNotFound, UnexpectedError
from modules.database import init as db_init, get_all_items
from modules.enumerations import PlayerStatus
from modules.loader import init as cog_init, is_all_locked, unlock_all
from modules.reactions import init as react_init, reaction_handler

# Modules for the custom classes
from modules.roles import init as roles_init, role_update, is_admin
from modules.reactions import reaction_handler

# Modules for the custom classes
from matches import on_inactive_confirmed, init as matches_init
from classes.players import Player, get_player, get_all_players_list
from classes.accounts import AccountHander
from classes.maps import Map, MapSelection
from classes.weapons import Weapon


rules_msg = None  # Will contain message object representing the rules message, global variable

log = logging.getLogger("pog_bot")

def _add_main_handlers(client):
    """_add_main_handlers, private function
        Parameters
        ----------
        client : discord.py bot
            Our bot object
    """

    # help command, works in all channels
    @client.command(aliases=['h'])
    @commands.guild_only()
    async def help(ctx):
        await send("HELP", ctx)

    # Slight anti-spam: prevent the user to input a command if the last one isn't yet processed
    # Useful for the long processes like ps2 api, database or spreadsheet calls
    @client.event
    async def on_message(message):
        if message.author == client.user:  # if bot, do nothing
            await client.process_commands(message)
            return
        # if dm, print in console and ignore the message
        if isinstance(message.channel, DMChannel):
            logging.info(message.author.name + ": " + message.content)
            return
        if message.channel.id not in cfg.channels_list:
            return
        if is_all_locked():
            if not is_admin(message.author):
                return
            # Admins can still use bot when locked
        if await is_spam(message):
            return
        message.content = message.content.lower()
        await client.process_commands(message)  # if not spam, process
        await sleep(0.5)
        unlock(message.author.id)  # call finished, we can release user

    # Global command error handler
    @client.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.CommandNotFound):  # Unknown command
            if is_all_locked():
                await send("BOT_IS_LOCKED", ctx)
                return
            await send("INVALID_COMMAND", ctx)
            return
        if isinstance(error, commands.errors.CheckFailure):  # Unauthorized command
            cog_name = ctx.command.cog.qualified_name
            if cog_name == "admin":
                await send("NO_PERMISSION", ctx, ctx.command.name)
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
                await send("WRONG_CHANNEL", ctx, ctx.command.name, channel_str)
            except KeyError:  # Should not happen
                await send("UNKNOWN_ERROR", ctx, "Channel key error")
            return
        # These are annoying error generated by discord.py when user input quotes (")
        bl = isinstance(error, commands.errors.InvalidEndOfQuotedStringError)
        bl = bl or isinstance(error, commands.errors.ExpectedClosingQuoteError)
        bl = bl or isinstance(error, commands.errors.UnexpectedQuoteError)
        if bl:
            # Tell the user not to use quotes
            await send("INVALID_STR", ctx, '"')
            return

        if isinstance(error.original, UnexpectedError):
            log.error(str(error))
            await send("UNKNOWN_ERROR", ctx, error.original.reason)
        else:
            # Print unhandled error
            log.error(str(error))
            await send("UNKNOWN_ERROR", ctx, type(error.original).__name__)
        raise error

    # Reaction update handler (for rule acceptance)
    @client.event
    # Has to be on_raw cause the message already exists when the bot starts
    async def on_raw_reaction_add(payload):
        if payload.member is None or payload.member.bot:  # If bot, do nothing
            return
        if is_all_locked():
            return
        # reaction to the rule message?
        if payload.message_id == cfg.general["rules_msg_id"]:
            print(str(payload.emoji)) # @TODO: remove (test)
            if str(payload.emoji) == "✅":
                try:
                    p = get_player(payload.member.id)
                except ElementNotFound:  # if new player
                    # create a new profile
                    p = Player(payload.member.id, payload.member.name)
                await role_update(p)
                if p.status is PlayerStatus.IS_NOT_REGISTERED:
                    # they can now register
                    await send("REG_RULES", SendCtx.channel(cfg.channels["register"]), payload.member.mention)
            # In any case remove the reaction, message is to stay clean
            await rules_msg.remove_reaction(payload.emoji, payload.member)

    # Reaction update handler (for accounts)
    @client.event
    async def on_reaction_add(reaction, user):
        # If the reaction is from the bot
        if user == client.user:
            return
        # If the reaction is not to a message of the bot
        if reaction.message.author != client.user:
            return
        try:
            player = get_player(user.id)
        except ElementNotFound:
            return
        await reaction_handler(reaction, user, player)

    @client.event
    async def on_member_join(member):
        try:
            player = get_player(member.id)
        except ElementNotFound:
            return
        await role_update(player)

    @client.event
    async def on_member_update(before, after):
        if before.status != after.status:
            await on_status_update(after)

    # Status update handler (for inactivity)
    async def on_status_update(user):
        try:
            player = get_player(user.id)
        except ElementNotFound:
            return
        if user.status == Status.offline:
            player.on_inactive(on_inactive_confirmed)
        else:
            player.on_active()
        await role_update(player)


def _add_init_handlers(client):

    @client.event
    async def on_ready():
        # Initialise matches channels
        matches_init(client, cfg.channels["matches"])

        roles_init(client)

        # fetch rule message, remove all reaction but the bot's
        global rules_msg
        rules_msg = await client.get_channel(cfg.channels["rules"]).fetch_message(cfg.general["rules_msg_id"])
        await rules_msg.clear_reactions()
        await sleep(0.2)
        await rules_msg.add_reaction('✅')

        # Update all players roles
        for p in get_all_players_list():
            await role_update(p)
        _add_main_handlers(client)
        unlock_all(client)
        log.info('Client is ready!')

    @client.event
    async def on_message(message):
        return

# TODO: testing, to be removed
def _test(client):
    from test2 import test_hand
    test_hand(client)

def _define_log(launch_str):
    # Logging config, logging outside the github repo
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

    # Seeding random generator
    seed(dt.now())

    log.info("Starting init...")

    # Get data from the config file
    cfg.get_config(f"config{launch_str}.cfg")

    # Set up command prefix
    client = commands.Bot(command_prefix=cfg.general["command_prefix"], intents=Intents.all())

    # Remove default help
    client.remove_command('help')

    # Initialise db and get all the registered users and all maps from it
    db_init(cfg.database)
    get_all_items(Player.new_from_data, "users")
    get_all_items(Map, "s_bases")
    get_all_items(Weapon, "s_weapons")

    # Get Account sheet from drive
    AccountHander.init(f"google_api_secret{launch_str}.json")

    # Establish connection with Jaeger Calendar
    MapSelection.init(f"google_api_secret{launch_str}.json")

    # Initialise display module
    display_init(client)

    # Initialise reaction handlers
    react_init(client)

    # Add init handlers
    _add_init_handlers(client)

    if launch_str == "_test":
        _test(client)

    # Add all cogs
    cog_init(client)

    # Run server
    client.run(cfg.general["token"])


if __name__ == "__main__":
    if os.path.isfile("test"):
        main("_test")
    else:
        main()
