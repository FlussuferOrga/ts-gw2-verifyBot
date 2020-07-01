from bot.ts.ThreadSafeTSConnection import ThreadSafeTSConnection, signal_exception_handler


class TS3Facade:
    def __init__(self, ts3_connection: ThreadSafeTSConnection):
        self._ts3_connection = ts3_connection

    def send_text_message_to_client(self, target_client_id: int, msg: str):
        self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode=1, target=target_client_id, msg=msg))

    def send_text_message_to_current_channel(self, msg: str):
        self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode=2, msg=msg))

    def send_text_message_to_server(self, msg: str):
        self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode=3, msg=msg))

    def channel_find(self, channel_name: str):
        resp, ts3qe = self._ts3_connection.ts3exec(lambda tsc: tsc.query("channelfind", pattern=channel_name).first(), signal_exception_handler)
        if ts3qe is not None:
            if hasattr(ts3qe, "resp") and ts3qe.resp.error["id"] == '768':  # channel not found.
                return None
            raise ts3qe

        return Channel(resp["cid"], resp["channel_name"])

    # FIXME: tests
    def channel_info(self, channel_id: int):
        resp, ts3qe = self._ts3_connection.ts3exec(lambda tsc: tsc.query("channelinfo", cid=channel_id).all())
        return resp

    # FIXME: tests
    def channel_delete(self, channel_id: int, force: bool = False):
        self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("channeldelete", cid=channel_id, force=1 if force else 0))

    # FIXME: tests
    def servergroup_list(self):
        resp, ts3qe = self._ts3_connection.ts3exec(lambda tsc: tsc.query("servergrouplist").all())
        return resp

    # FIXME: tests
    def servergroup_delete(self, servergroup_id: int, force: bool = False):
        self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("servergroupdel", sgid=servergroup_id, force=1 if force else 0))

    # FIXME: tests
    def channel_create(self,
                       channel_name: str,
                       channel_description: str = "",
                       channel_parent_id: int = 0,
                       channel_flag_permanent: bool = True,
                       channel_maxclients: int = -1,  # passing -1 makes the number of clients unlimited
                       channel_order: int = 0
                       ):
        self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("channelcreate",
                                                           channel_name=channel_name,
                                                           channel_description=channel_description,
                                                           cpid=channel_parent_id,
                                                           channel_flag_permanent=1 if channel_flag_permanent else 0,
                                                           channel_maxclients=channel_maxclients,
                                                           channel_order=channel_order,
                                                           channel_flag_maxclients_unlimited=1 if channel_maxclients == -1 else 0).first(),
                                     signal_exception_handler)


class Channel:
    def __init__(self, channel_id, channel_name):
        self.channel_id: str = channel_id
        self.channel_name: str = channel_name
