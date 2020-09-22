from typing import TypedDict


class WhoamiResponse(TypedDict):
    virtualserver_status: str
    virtualserver_id: int
    virtualserver_unique_identifier: str
    virtualserver_port: int
    client_id: int
    client_channel_id: int
    client_nickname: str
    client_database_id: int
    client_login_name: str
    client_unique_identifier: str
    client_origin_server_id: int
