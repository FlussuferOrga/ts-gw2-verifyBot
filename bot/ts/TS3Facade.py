import logging
import os
from typing import List, Optional, Tuple

import ts3
from ts3 import TS3Error
from ts3.filetransfer import TS3FileTransfer, TS3UploadError
from ts3.query import TS3TimeoutError

from bot.ts.ThreadSafeTSConnection import ThreadSafeTSConnection, ignore_exception_handler, signal_exception_handler
from bot.ts.model import Channel
from bot.ts.types.channel_list_detail import ChannelListDetail
from bot.ts.types.whoami import WhoamiResponse

LOG = logging.getLogger(__name__)


class TS3Facade:
    def __init__(self, ts3_connection: ThreadSafeTSConnection):
        self._ts3_connection = ts3_connection

    def __str__(self):
        return f"TS3Facade[{self._ts3_connection}]"

    def close(self, timeout=5):
        self._ts3_connection.close(timeout)

    def is_healthy(self):
        return self._ts3_connection.is_healthy()

    def version(self):
        return self._ts3_connection.ts3exec_raise(lambda tc: tc.query("version").first())

    def wait_for_event(self, timeout: int):
        try:
            resp = self._ts3_connection.ts3exec_raise(lambda tc: tc.wait_for_event(timeout=timeout))
        except TS3TimeoutError:
            resp = None
        return resp

    def send_text_message_to_client(self, target_client_id: int, msg: str):
        self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode=1, target=target_client_id, msg=msg))

    def send_text_message_to_current_channel(self, msg: str):
        self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode=2, msg=msg))

    def send_text_message_to_server(self, msg: str):
        self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("sendtextmessage", targetmode=3, msg=msg))

    def channel_find_all(self, channel_name: str) -> Optional[List[Channel]]:
        resp, ts3qe = self._ts3_connection.ts3exec(lambda tsc: tsc.query("channelfind", pattern=channel_name).all(), signal_exception_handler)
        if ts3qe is not None:
            if hasattr(ts3qe, "resp") and ts3qe.resp.error["id"] == '768':  # channel not found.
                return None
            raise ts3qe

        return [Channel(chan["cid"], chan["channel_name"]) for chan in resp]

    def channel_find_first(self, channel_name: str) -> Optional[Channel]:
        resp, ts3qe = self._ts3_connection.ts3exec(lambda tsc: tsc.query("channelfind", pattern=channel_name).first(), signal_exception_handler)
        if ts3qe is not None:
            if hasattr(ts3qe, "resp") and ts3qe.resp.error["id"] == '768':  # channel not found.
                return None
            raise ts3qe

        return Channel(resp["cid"], resp["channel_name"])

    # FIXME: tests
    def channel_info(self, channel_id: int):
        return self._ts3_connection.ts3exec(lambda tsc: tsc.query("channelinfo", cid=channel_id).first(), signal_exception_handler)

    # FIXME: tests
    def channel_delete(self, channel_id: int, force: bool = False):
        self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("channeldelete", cid=channel_id, force=1 if force else 0))

    # FIXME: tests
    def servergroup_list(self):
        resp, _ = self._ts3_connection.ts3exec(lambda tsc: tsc.query("servergrouplist").all())
        return resp

    def servergroup_list_by_client(self, client_db_id: str):
        return self._ts3_connection.ts3exec(lambda ts_connection: ts_connection.query("servergroupsbyclientid", cldbid=client_db_id).all(), signal_exception_handler)[0]

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
        ts_exec = self._ts3_connection.ts3exec(lambda tsc: tsc.query("channelcreate", channel_name=channel_name, channel_description=channel_description, cpid=channel_parent_id,
                                                                     channel_flag_permanent=1 if channel_flag_permanent else 0, channel_maxclients=channel_maxclients, channel_order=channel_order,
                                                                     channel_flag_maxclients_unlimited=1 if channel_maxclients == -1 else 0).first(), signal_exception_handler)
        return ts_exec

    def channel_add_permission(self, channel_id: int, permission_id: str, permission_value: int, negated: bool = False, skip: bool = False):
        return self._ts3_connection.ts3exec_raise(lambda tsc: tsc.exec_("channeladdperm",
                                                                        cid=channel_id, permsid=permission_id,
                                                                        permvalue=permission_value,
                                                                        permnegated=1 if negated else 0,
                                                                        permskip=1 if skip else 0))

    def channel_add_permissions(self, channel_id: int, permissions: List[Tuple[str, int]]):
        for permission_id, permission_value in permissions:
            self.channel_add_permission(channel_id, permission_id=permission_id, permission_value=permission_value)

    def channel_list(self) -> List[ChannelListDetail]:
        return self._ts3_connection.ts3exec_raise(lambda tc: tc.query("channellist").all())

    def use(self, server_id: int, timeout=5):
        self._ts3_connection.ts3exec_raise(lambda tc: tc.query("use", sid=server_id).timeout(timeout=timeout).fetch())

    def whoami(self, timeout=5) -> WhoamiResponse:
        return self._ts3_connection.ts3exec_raise(lambda ts_con: ts_con.query("whoami").timeout(timeout).first())

    def upload_icon(self, icon_id, icon_data):
        def _ts_file_upload_hook(ts3_response: ts3.response.TS3QueryResponse):
            if ts3_response is not None:
                if ts3_response.parsed is not None and len(ts3_response.parsed) == 1 and ts3_response.parsed[0] is not None:
                    if "msg" in ts3_response.parsed[0].keys() and ts3_response.parsed[0]["msg"] == "invalid size":
                        raise TS3UploadError(0, "The uploaded Icon is too large")

        icon_server_path = f"/icon_{icon_id}"
        icon_local_file_name = f"{icon_id}_icon.png"  # using name instead of tag, because tags are not unique

        def _upload(ts3con):
            with open(icon_local_file_name, "w+b") as file_handle:
                try:
                    file_handle.write(icon_data)
                    file_handle.flush()
                    file_handle.seek(0)

                    # it is important to have acquired the lock for the ts3conn globally
                    # at this point, as we directly pass the wrapped connection around
                    upload = TS3FileTransfer(ts3con)
                    _ = upload.init_upload(input_file=file_handle,
                                           name=icon_server_path,
                                           cid=0,  # 0 = Serverwide
                                           query_resp_hook=_ts_file_upload_hook)
                    LOG.info("Icon %s uploaded as %s.", icon_local_file_name, icon_server_path)
                except TS3Error as ts3error:
                    LOG.error("Error Uploading icon %s.", icon_local_file_name, exc_info=ts3error)
                finally:
                    file_handle.close()
                    os.remove(icon_local_file_name)

        self._ts3_connection.ts3exec(_upload)

    def servergroup_add(self, servergroup_name: str):
        return self._ts3_connection.ts3exec(lambda tsc: tsc.query("servergroupadd", name=servergroup_name).first(), signal_exception_handler)

    def servergroup_add_permission(self, servergroup_id: str, permission_id: str, permission_value: int, negated: bool = False, skip: bool = False):
        return self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("servergroupaddperm",
                                                                  sgid=servergroup_id, permsid=permission_id,
                                                                  permvalue=permission_value,
                                                                  permnegated=1 if negated else 0,
                                                                  permskip=1 if skip else 0),
                                            signal_exception_handler)

    def servergroup_add_permissions(self, servergroup_id: str, permissions: List[Tuple[str, int]]):
        for permission_id, permission_value in permissions:
            self.servergroup_add_permission(servergroup_id, permission_id=permission_id, permission_value=permission_value)

    def channelgroup_list(self):
        return self._ts3_connection.ts3exec(lambda tsc: tsc.query("channelgrouplist").all(), signal_exception_handler)

    def channelgroup_client_list(self, channelgroup_ids: List[str]):
        result = []
        for channel_group_id in channelgroup_ids:
            channel_group_result, ts3qe = self._ts3_connection.ts3exec(lambda tsc: tsc.query("channelgroupclientlist", cgid=channel_group_id).all(), signal_exception_handler)
            if ts3qe:  # check for .resp, could be another exception type
                if hasattr(ts3qe, "resp") and ts3qe.resp is not None:
                    if ts3qe.resp.error["id"] != "1281":
                        # 1281 is "database empty result set", which is an expected error
                        # if not a single user currently wears a tag.
                        raise ts3qe
            if channel_group_result is not None:
                result.extend(channel_group_result)
        return [dict(s) for s in set(frozenset(d.items()) for d in result)]  # removes dublicates

    def set_client_channelgroup(self, channel_id: str, channelgroup_id: str, client_db_id: str):
        _, ex = self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("setclientchannelgroup", cgid=channelgroup_id, cid=channel_id, cldbid=client_db_id), signal_exception_handler)
        return ex

    def servergroup_client_add(self, servergroup_id: str, client_db_id: str):
        _, ex = self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("servergroupaddclient", sgid=servergroup_id, cldbid=client_db_id), signal_exception_handler)
        return ex

    def servergroup_client_del(self, servergroup_id: str, client_db_id: str):
        _, ex = self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("servergroupdelclient", sgid=servergroup_id, cldbid=client_db_id), signal_exception_handler)
        return ex

    def server_notify_register(self, events: List[str]):
        for event in events:
            self._ts3_connection.ts3exec(lambda tc: tc.exec_("servernotifyregister", event=event))  # alert channel chat

    def client_move(self, client_id: str, channel_id: str):
        _, chnl_err = self._ts3_connection.ts3exec(lambda tc: tc.exec_("clientmove", clid=client_id, cid=channel_id))
        return chnl_err

    def client_get_name_from_uid(self, client_uid: str):
        return self._ts3_connection.ts3exec(lambda t: t.query("clientgetnamefromuid", cluid=client_uid).first())

    def client_get_name_from_dbid(self, client_dbid):
        return self._ts3_connection.ts3exec_raise(lambda t: t.query("clientgetnamefromdbid", cldbid=client_dbid).first())

    def client_info(self, client_id: str):
        return self._ts3_connection.ts3exec_raise(lambda t: t.query("clientinfo", clid=client_id).first())

    def client_db_id_from_uid(self, client_uid) -> Optional[str]:
        response, ex = self._ts3_connection.ts3exec(lambda t: t.query("clientgetdbidfromuid", cluid=client_uid).first().get("cldbid"), exception_handler=signal_exception_handler)
        if ex is None:
            return response

        if hasattr(ex, "resp") and ex.resp is not None:
            if ex.resp.error["id"] == "512":
                # user not found
                return None

        raise ex

    def client_ids_from_uid(self, client_uid) -> List[str]:
        response, ex = self._ts3_connection.ts3exec(lambda t: t.query("clientgetids", cluid=client_uid).all(), exception_handler=signal_exception_handler)
        if ex is None:
            return response
        else:
            if hasattr(ex, "resp") and ex.resp is not None:
                if ex.resp.error["id"] == "1281":  # database empty result set
                    return []
        raise ex

    def force_rename(self, target_nickname: str):
        return self._ts3_connection.force_rename(target_nickname=target_nickname)

    def client_get_uid_from_dbid(self, client_db_id: str):
        response, ex = self._ts3_connection.ts3exec(lambda t: t.query("clientgetnamefromdbid", cldbid=client_db_id).first().get("cluid"), exception_handler=signal_exception_handler)
        if ex is None:
            return response
        else:
            if hasattr(ex, "resp") and ex.resp is not None:
                if ex.resp.error["id"] == "512":
                    # user not found
                    return None
        raise ex

    def channel_edit(self, channel_id: str, new_channel_name: str):
        return self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("channeledit", cid=channel_id, channel_name=new_channel_name), signal_exception_handler)

    def remove_icon_if_exists(self, icon_id: int):
        icon_server_path: str = f"/icon_{icon_id}"
        return self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("ftdeletefile", cid=0, cpw=None, name=icon_server_path), ignore_exception_handler)

    def server_info(self):
        return self._ts3_connection.ts3exec_raise(lambda t: t.query("serverinfo").first())

    def servergroup_rename(self, group_id: int, desired_name: str):
        return self._ts3_connection.ts3exec(lambda tsc: tsc.exec_("servergrouprename", sgid=group_id, name=desired_name), signal_exception_handler)

    pass
