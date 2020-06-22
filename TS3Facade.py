from ThreadsafeTSConnection import ThreadsafeTSConnection, signal_exception_handler


class TS3Facade:
    def __init__(self, ts3_connection: ThreadsafeTSConnection):
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


class Channel:
    def __init__(self, channel_id, channel_name):
        self.channel_id: str = channel_id
        self.channel_name: str = channel_name
