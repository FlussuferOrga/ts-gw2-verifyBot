from bot.ts.ThreadSafeTSConnection import default_exception_handler


class User():
    """
    Class that interfaces the Teamspeak-API with user-specific calls more convenient.
    Since calls to the API are penalised, the class also tries to minimise those calls
    by only resolving properties when they are actually needed and then caching them (if sensible).
    """

    def __init__(self, ts_facade, unique_id=None, ts_db_id=None, client_id=None):
        self._ts_facade = ts_facade
        self._unique_id = unique_id
        self._ts_db_id = ts_db_id
        self._client_id = client_id
        self._exception_handler = default_exception_handler

        if all(x is None for x in [unique_id, ts_db_id, client_id]):
            raise ValueError("At least one ID must be non-null")

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "User[unique_id: %s, ts_db_id: %s, client_id: %s]" % (self.unique_id, self.ts_db_id, self._client_id)

    @property
    def current_channel(self):
        client_info = self._ts_facade.client_info(client_id=self.client_id)
        if client_info:
            self._ts_db_id = client_info.get("client_database_id")  # since we are already retrieving this information...
        return Channel(client_info.get("cid")) if client_info else None

    @property
    def name(self):
        return self._ts_facade.client_get_name_from_uid(client_uid=self._unique_id)[0].get("name")

    @property
    def unique_id(self):
        if self._unique_id is None:
            if self._ts_db_id is not None:
                self._unique_id = self._ts_facade.client_get_name_from_dbid(self._ts_db_id).get("cluid")
            elif self._client_id is not None:
                client_info = self._ts_facade.client_info(client_id=self._client_id)
                self._unique_id = client_info.get("client_unique_identifier")
                self._ts_db_id = client_info.get("client_databased_id")  # not required, but since we already queried it...
            else:
                raise ValueError("Unique ID can not be retrieved")
        return self._unique_id

    @property
    def ts_db_id(self):
        if self._ts_db_id is None:
            if self._unique_id is not None:
                self._ts_db_id = self._ts_facade.client_db_id_from_uid(self._unique_id)
            elif self._client_id is not None:
                ids = self._ts_facade.client_info(client_id=self._client_id)
                self._unique_id = ids.get("client_unique_identifier")  # not required, but since we already queried it...
                self._ts_db_id = ids.get("client_database_id")
            else:
                raise ValueError("TS DB ID can not be retrieved")
        return self._ts_db_id

    @property
    def client_id(self):
        if self._client_id is None:
            if self._unique_id is not None:
                # easiest case: unique ID is set
                self._client_id = self._ts_facade.client_ids_from_uid(client_uid=self._unique_id)[0].get("clid")  # use first and hope for the best.
            elif self._ts_db_id is not None:
                self._unique_id = self._ts_facade.client_get_name_from_dbid(client_dbid=self._ts_db_id).get("cluid")
                self._client_id = self._ts_facade.client_ids_from_uid(client_uid=self._unique_id)[0].get("clid")  # use first and hope for the best.
            else:
                raise ValueError("Client ID can not be retrieved")
        return self._client_id


class Channel:
    def __init__(self, channel_id):
        self.channel_id = channel_id
