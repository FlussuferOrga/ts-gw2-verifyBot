import datetime
import logging
import re
import sqlite3
import threading
from typing import Optional

import time
from ts3.response import TS3Event

from bot.db import ThreadSafeDBConnection
from bot.ts import Channel, TS3Facade, User
from .TS3Auth import AuthRequest, AuthorizationNotPossibleError
from .audit_service import AuditService
from .config import Config
from .connection_pool import ConnectionPool
from .user_service import UserService

REGISTER_EVENTS = ["textchannel", "textprivate", "server"]

LOG = logging.getLogger(__name__)


class EventLooper:
    _verify_channel: Optional[Channel]

    def __init__(self, database_connection: ThreadSafeDBConnection,
                 ts_connection_pool: ConnectionPool[TS3Facade],
                 config: Config,
                 user_service: UserService,
                 audit_service: AuditService):
        self._database_connection = database_connection
        self._ts_connection_pool = ts_connection_pool
        self._config = config
        self._user_service = user_service
        self._audit_service = audit_service

        self._lock = threading.RLock()

        self._ts_facade: Optional[TS3Facade] = None
        self._own_client_id = None
        self._verify_channel = None
        self.closed = False

    def start(self):
        while not self.closed:
            with self._lock:  # prevent concurrency
                with self._ts_connection_pool.item() as ts_facade:
                    self._ts_facade = ts_facade

                    # Forces script to loop forever while we wait for events to come in, unless connection timed out or exception occurs.
                    # Then it should loop a new bot into creation.
                    LOG.info("BOT now idle, waiting for requests.")

                    self._loop_for_events()

    def _loop_for_events(self):
        self._set_up_connection()
        last_check = datetime.datetime.now()

        while not self.closed and self._ts_facade is not None and self._ts_facade.is_healthy():

            # periodically reconfigure the connection (if changes are necessary)
            if last_check is None or (datetime.datetime.now() - last_check).seconds > 30:
                change_detected = self._set_up_connection()
                if change_detected:
                    LOG.warning("Query Client has been reconfigured. This should not be necessary.")
                last_check = datetime.datetime.now()

            response: TS3Event = self._ts_facade.wait_for_event(timeout=self._config.bot_sleep_idle)
            if response is not None:
                event_type: str = response.event
                event_data = response.parsed[0]
                try:
                    self._handle_event(event_data, event_type)
                except Exception as ex:
                    LOG.error("Error while handling the event", exc_info=ex)
        LOG.info("Listening Connection is not available anymore. Ending loop.")

    def _set_up_connection(self):
        change = False

        current_state = self._ts_facade.whoami()

        if current_state['virtualserver_id'] != self._config.server_id:
            LOG.info("Using server %s", self._config.server_id)
            self._ts_facade.use(self._config.server_id)  # abort loop, resets loop
            change = True

        self._own_client_id = current_state.get('client_id')
        if current_state['client_nickname'] != self._config.bot_nickname:
            LOG.info("Renaming myself to  %s", self._config.bot_nickname)
            self._ts_facade.force_rename(self._config.bot_nickname)
            change = True

        # Find the verify channel
        if self._verify_channel is None:
            self._verify_channel = self._find_verify_channel()
            LOG.info("Detected channel %s", self._verify_channel)
            change = True

        # Move ourselves to the Verify channel
        if current_state['client_channel_id'] != self._verify_channel.id:
            LOG.info("Moving myself to %s", self._verify_channel)
            self._move_to_channel(self._verify_channel, self._own_client_id)
            change = True

        if change:  # any of the above parameters changes, re-registering for events
            LOG.info("Registering for events: %s", REGISTER_EVENTS)
            # register for text events
            self._ts_facade.server_notify_register(REGISTER_EVENTS)

        return change

    def _handle_event(self, event_data, event_type):
        if event_type == 'notifytextmessage':  # text message
            if "msg" in event_data:
                self._handle_message_event(event_data)  # handle event
        elif event_type == 'notifycliententerview':
            if event_data["client_type"] == '0':  # no server query client
                self._handle_client_login(event_data)  # handle event
        elif event_type == 'notifyclientleftview':  # client left
            pass  # this event is not of interest
        else:
            LOG.warning("Unhandled Event: %s", event_type)

    def _move_to_channel(self, channel: Channel, client_id):
        chnl_err = self._ts_facade.client_move(client_id=client_id, channel_id=str(channel.channel_id))
        if chnl_err:
            LOG.warning("BOT Attempted to join channel '%s' (%s): %s", channel.channel_name, channel.channel_id,
                        chnl_err.resp.error["msg"])
        else:
            LOG.info("BOT has joined channel '%s' (%s).", channel.channel_name, channel.channel_id)

    def _find_verify_channel(self):
        channel_name = self._config.channel_name

        found_channel = None
        while found_channel is None:
            found_channel = self._ts_facade.channel_find_first(channel_name)
            if found_channel is None:
                LOG.warning("Unable to locate channel with name '%s'. Sleeping for 10 seconds...", channel_name)
                time.sleep(10)
            else:
                return found_channel

    # Handler that is used every time an event (message) is received from teamspeak server
    def _handle_message_event(self, event_data):
        """
        *event* is a ts3.response.TS3Event instance, that contains the name
        of the event and the data.
        """
        message = event_data.get('msg')
        rec_from_name = event_data.get('invokername').encode('utf-8')  # fix any encoding issues introduced by Teamspeak
        rec_from_uid = event_data.get('invokeruid')
        rec_from_id = event_data.get('invokerid')
        rec_type = event_data.get('targetmode')

        if rec_from_id == self._own_client_id:
            return  # ignore our own messages.
        try:
            # Type 2 means it was channel text
            if rec_type == "2":
                self.handle_channel_msg(message, rec_from_id, rec_from_name, rec_from_uid)
            # Type 1 means it was a private message
            elif rec_type == '1':
                self.handle_private_message(message, rec_from_id, rec_from_name, rec_from_uid)
        except Exception as ex:
            LOG.error("BOT Event: Something went wrong during message received from teamspeak server." +
                      " Likely bad user command/message.",
                      exc_info=ex)
        return None

    def handle_channel_msg(self, message, rec_from_id, rec_from_name, rec_from_uid):
        LOG.info("Received Text Channel Message from %s (%s) : %s", rec_from_name, rec_from_uid, message)
        cmd, args = self._extract_command(
            message)  # sanitize the commands but also restricts commands to a list of known allowed commands
        if cmd is not None:
            if cmd == "ping":
                LOG.info("Ping received from '%s'!", rec_from_name)
                self._ts_facade.send_text_message_to_client(rec_from_id,
                                                            self._config.locale.get("bot_pong_response"))
            if cmd == "hideguild":
                if len(args) == 1:
                    LOG.info("User '%s' wants to hide guild '%s'.", rec_from_name, args[0])
                    with self._database_connection.lock:
                        try:
                            tag_to_hide = args[0]
                            result = self._database_connection.cursor.execute(
                                "SELECT guild_id FROM guilds WHERE ts_group = ?", (tag_to_hide,)).fetchone()
                            if result is None:
                                LOG.debug("Failed. " +
                                          "The group probably doesn't exist or the user is already hiding that group.")
                                self._ts_facade.send_text_message_to_client(rec_from_id,
                                                                            self._config.locale.get(
                                                                                "bot_hide_guild_unknown"))
                            else:
                                guild_db_id = result[0]
                                self._database_connection.cursor.execute(
                                    "INSERT INTO guild_ignores(guild_id, ts_db_id, ts_name) VALUES(?, ?, ?)",
                                    (guild_db_id, rec_from_uid, rec_from_name))
                                self._database_connection.conn.commit()
                                self._audit_service.audit_user_on_hide_unhide_guild(rec_from_uid)
                                LOG.debug("Success!")
                                self._ts_facade.send_text_message_to_client(rec_from_id,
                                                                            self._config.locale.get(
                                                                                "bot_hide_guild_success"))
                        except sqlite3.IntegrityError as ex:
                            self._database_connection.conn.rollback()
                            LOG.error("Database error during hideguild", exc_info=ex)
                            self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get(
                                "bot_hide_guild_unknown"))
                else:
                    self._ts_facade.send_text_message_to_client(rec_from_id,
                                                                self._config.locale.get("bot_hide_guild_help"))
            elif cmd == "unhideguild":
                if len(args) == 1:
                    LOG.info("User '%s' wants to unhide guild '%s'.", rec_from_name, args[0])
                    with self._database_connection.lock:
                        self._database_connection.cursor.execute(
                            "DELETE FROM guild_ignores WHERE guild_id = (SELECT guild_id FROM guilds WHERE ts_group = ? AND ts_db_id = ?)",
                            (args[0], rec_from_uid))
                        changes = self._database_connection.cursor.execute("SELECT changes()").fetchone()[0]
                        self._database_connection.conn.commit()
                        if changes > 0:
                            LOG.debug("Success!")
                            self._audit_service.audit_user_on_hide_unhide_guild(rec_from_uid)
                            self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get(
                                "bot_unhide_guild_success"))
                        else:
                            LOG.debug(
                                "Failed. Either the guild is unknown or the user had not hidden the guild anyway.")
                            self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get(
                                "bot_unhide_guild_unknown"))
                else:
                    self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get(
                        "bot_unhide_guild_help"))

    def handle_private_message(self, message, rec_from_id, rec_from_name, rec_from_uid):
        LOG.info("Received Private Chat Message from %s (%s) : %s", rec_from_name, rec_from_uid, message)

        reg_api_auth = r'\s*(.*?-.*?-.*?-.*?-.*)\s*$'
        # Command for verifying authentication
        if re.match(reg_api_auth, message):
            pair = re.search(reg_api_auth, message)
            uapi = pair.group(1)

            if self._config.enable_verification:
                if self._user_service.check_client_needs_verify(rec_from_uid):
                    LOG.info("Received verify request from %s", rec_from_name)
                    try:
                        auth = AuthRequest(uapi, self._config.required_servers, int(self._config.required_level))

                        LOG.debug('Name: |%s| API: |%s|', auth.name, uapi)

                        if auth.success:
                            limit_hit = self._user_service.is_ts_registration_limit_reached(auth.name)
                            if self._config.debug:
                                LOG.debug("Limit hit check: %s", limit_hit)
                            if not limit_hit:
                                LOG.info("Setting permissions for %s as verified.", rec_from_name)

                                # set permissions
                                self._user_service.set_permissions(rec_from_uid)

                                # get todays date
                                today_date = datetime.date.today()

                                # Add user to database so we can query their API key over time to ensure they are still on our server
                                self._user_service.add_user_to_database(rec_from_uid, auth.name, uapi, today_date,
                                                                        today_date)
                                self._user_service.update_guild_tags(self._ts_facade,
                                                                     User(self._ts_facade, unique_id=rec_from_uid),
                                                                     auth)
                                # self.updateGuildTags(rec_from_uid, auth)
                                LOG.debug("Added user to DB with ID %s", rec_from_uid)

                                # notify user they are verified
                                self._ts_facade.send_text_message_to_client(rec_from_id,
                                                                            self._config.locale.get("bot_msg_success"))
                            else:
                                # client limit is set and hit
                                self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get(
                                    "bot_msg_limit_Hit"))
                                LOG.info("Received API Auth from %s, but %s has reached the client limit.",
                                         rec_from_name,
                                         rec_from_name)
                        else:
                            # Auth Failed
                            self._ts_facade.send_text_message_to_client(rec_from_id,
                                                                        self._config.locale.get("bot_msg_fail"))
                    except AuthorizationNotPossibleError as ex:
                        LOG.warning("Audit of Teamspeak user %s is currently not possible. Skipping.", rec_from_name,
                                    exc_info=ex)
                        self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get(
                            "bot_msg_verification_currently_not_possible"))
                else:
                    LOG.debug("Received API Auth from %s, but %s is already verified. Notified user as such.",
                              rec_from_name, rec_from_name)
                    self._ts_facade.send_text_message_to_client(rec_from_id,
                                                                self._config.locale.get("bot_msg_alrdy_verified"))
            else:
                self._ts_facade.send_text_message_to_client(rec_from_id,
                                                            self._config.locale.get("bot_msg_verification_disabled"))
        else:
            self._ts_facade.send_text_message_to_client(rec_from_id, self._config.locale.get("bot_msg_rcv_default"))
            LOG.info("Received bad response from %s [msg= %s]", rec_from_name, message.encode('utf-8'))
            # sys.exit(0)

    def _handle_client_login(self, event_data):
        # raw_sgroups = event_data.get('client_servergroups')
        client_type: int = int(event_data.get('client_type'))
        raw_clid = event_data.get('clid')
        raw_cluid = event_data.get('client_unique_identifier')

        if client_type == 1:  # serverquery client, no need to send message or verify
            return

        if raw_clid == self._own_client_id:
            return

        if self._config.enable_verification:
            if self._user_service.check_client_needs_verify(raw_cluid):
                self._ts_facade.send_text_message_to_client(raw_clid, self._config.locale.get("bot_msg_verify"))
            else:
                self._audit_service.audit_user_on_join(raw_cluid)

    def _extract_command(self, command_string):
        for allowed_cmd in self._config.cmd_list:
            if re.match(r'(^%s)\s*' % (allowed_cmd,), command_string):
                toks = command_string.split()  # no argument for split() splits on arbitrary whitespace
                return toks[0], toks[1:]
        return None, None

    def close(self):
        self.closed = True
