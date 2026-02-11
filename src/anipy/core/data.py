import os
import json
import re
import sqlite3
import sys
import time

from typing import Generator, Literal, get_origin, get_args, AsyncGenerator

from .types import Servers, DataObject, DataList, LockFileKeys, Serializable
from ..extractors import Extractors
from .exceptions import BadResponse, EnvVarNotFound

from .util import compress_data, decompress_data, get_user_id

from ..integrations.discord import DiscordAPI
from ..integrations.webhook import Webhook, Body


def get_user_config_dir() -> str:
    if os.name == "posix":
        path = os.path.join(os.environ["HOME"], ".config", "anipy")
    else:
        path = os.path.joni(os.environ["APPDATA"], "anipy")

    if not os.path.exists(path):
        os.makedirs(path)

    return path


def get_user_data_dir() -> str:
    if os.name == "posix":
        path = os.path.join(os.environ["HOME"], ".local", "share", "anipy")
    else:
        path = os.path.joni(os.environ["APPDATA"], "anipy")

    if not os.path.exists(path):
        os.makedirs(path)

    return path


def get_lock_file() -> str:
    p = os.path.join(get_user_data_dir(), f"anipy-lock.json")
    if not os.path.exists(p):
        with open(p, "w") as f:
            json.dump({}, f)

    return p


def lock_file_update(key: LockFileKeys, value: Serializable) -> None:
    p = get_lock_file()

    with open(p, "r") as f:
        data = json.load(f)

    data[key] = value
    with open(p, "w") as f:
        json.dump(data, f, indent=4)


def lock_file_get_content() -> dict:
    with open(get_lock_file(), "r") as f:
        return json.load(f)


class Config:
    # fmt: off
    banner:     list[str]               = ["continue watching", "highlighted"]
    download:   bool                    = False
    cut:        bool                    = True
    player:     Literal["mpv", "vlc"]   = "mpv"
    server:     Servers                 = Servers.VIDSTREAMING
    extractor:  Extractors              = Extractors.MEGACLOUD
    prompt:     str                     = "{} > "
    # fmt: on

    def __init__(self) -> None:
        self.__path = os.path.join(get_user_config_dir(), "settings.json")
        self.__obj = {}

        if os.path.exists(self.__path):
            with open(self.__path, "r") as f:
                self.__obj = json.load(f)
                for k, v in self.__obj.items():
                    match k:
                        case "extractor":
                            setattr(self, k, Extractors[v])

                        case "server":
                            setattr(self, k, Servers[v])

                        case _:
                            setattr(self, k, v)

    def _get_annotations(self) -> dict:
        res = {}

        for k, annot in Config.__annotations__.items():
            if not k.startswith("_"):
                origin = get_origin(annot)

                if origin is Literal:
                    res[k] = list(get_args(annot))

                elif isinstance(annot, type):
                    res[k] = annot.__name__

                else:
                    res[k] = str(annot)

        return res

    def update(self, key: str, value) -> str | None:
        cfg = self.get_running_config()

        if key not in cfg:
            return f"unknown key '{key}'"

        annotion = Config.__annotations__[key]
        origin = get_origin(annotion)

        if annotion != str:
            try:
                value = eval(value)

            except NameError:
                return f"invalid value {value}"

            except TypeError:
                pass

            if origin is Literal and value not in get_args(annotion):
                return f"invalid value {value} (expected one of {get_args(annotion)})"

            elif isinstance(annotion, type) and not isinstance(value, annotion):
                return f"invalid arg type"

        if key in ("extractor", "server"):
            self.__obj[key] = value.name

        else:
            self.__obj[key] = value

        setattr(self, key, value)

        with open(self.__path, "w") as f:
            json.dump(self.__obj, f, indent=4)

    def get_running_config(self) -> dict:
        d = {}
        for k in dir(self):
            v = getattr(self, k)
            if not callable(v) and not k.startswith("_"):
                if k in ("server", "extractor"):
                    d[k] = v.name
                else:
                    d[k] = v

        return d

    def create(self) -> dict:
        data = {
            "download": False,
            "cut": False,
            "player": "mpv",
            "server": Servers.VIDSTREAMING.name,
            "extractor": Extractors.MEGACLOUD.name,
            "banner": [],
        }

        dir_name = os.path.dirname(self.__path)
        if not os.path.exists(dir_name):
            os.mkdir(dir_name)

        with open(self.__path, "w") as f:
            json.dump(data, f, indent=4)

        return data


class Condition:
    def __init__(self, column: str, expression: str, values: list) -> None:
        self.column = column
        self.expession = expression.upper()
        self.values = values

    @property
    def query(self) -> str:
        placeholders = ", ".join(["?"] * len(self.values))

        if self.expession == "in":
            placeholders = f"({placeholders})"

        return f"{self.column} {self.expession} {placeholders}"


class DB:
    def __init__(self, path: str) -> None:
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row

    def create(self, table: str, fields: dict) -> None:
        columns = ",\n\t".join([f"{k} {v}" for k, v in fields.items()])
        query = f"CREATE TABLE IF NOT EXISTS {table} (\n    {columns}\n);"

        self.con.execute(query)

    def select(self, table: str, condition: Condition | None = None) -> list[dict]:
        if condition:
            params = condition.values
            query = f"SELECT * FROM {table} WHERE {condition.query}"

        else:
            params = []
            query = f"SELECT * FROM {table}"

        cur = self.con.execute(query, params)
        return list(map(dict, cur.fetchall()))

    def insert(self, table: str, rows: list[dict]) -> None:
        placeholders = ", ".join(["?"] * len(rows[0]))
        keys = ""
        values = []

        for row in rows:
            row = dict(sorted(row.items()))
            if not keys:
                keys = ", ".join(row.keys())

            values.append(tuple(row.values()))

        query = f"INSERT INTO {table} ({keys}) VALUES ({placeholders})"

        self.con.executemany(query, values)
        self.con.commit()

    def update(self, table: str, data: dict, condition: Condition) -> None:
        placeholders = ", ".join([f"{k} = ?" for k in data.keys()])
        query = f"UPDATE {table} SET {placeholders} WHERE {condition.query}"

        params = list(data.values()) + condition.values

        self.con.execute(query, params)
        self.con.commit()

    def delete(self, table: str, condition: Condition) -> None:
        params = condition.values
        query = f"DELETE FROM {table} WHERE {condition.query}"

        self.con.execute(query, params)
        self.con.commit()

    def close(self) -> None:
        self.con.close()


class LocalDB:
    def __init__(self) -> None:
        db_filename = f"data.db"
        self.__path = os.path.join(get_user_data_dir(), db_filename)

        self.__db = DB(self.__path)
        self.__table = "data"

        try:
            self.__db.select(self.__table)

        except sqlite3.OperationalError:
            self.create()

    def pull(self) -> Generator[DataObject, None, None]:
        for o in self.__db.select(self.__table):
            yield DataObject(o)

    def erase(self) -> None:
        os.remove(self.__path)
        self.__init__()

    def add(self, objects: list[DataObject]) -> None:
        if any(self.__db.select(self.__table, Condition("id", "=", [o.id])) for o in objects):
            return

        self.__db.insert(self.__table, [o.json() for o in objects])

    def update(self, object: DataObject) -> None:
        d = object.json()
        d.pop("id")

        self.__db.update(self.__table, d, Condition("id", "=", [object.id]))

    def remove(self, object: DataObject) -> None:
        self.__db.delete(self.__table, Condition("id", "=", [object.id]))

    def create(self) -> None:
        self.__db.create(
            self.__table,
            {
                "id": "TEXT PRIMARY KEY",
                "title": "TEXT NOT NULL",
                "other_title": "TEXT",
                "episode_count": "INTEGER",
                "year": "INTEGER",
                "added_at": "INTEGER",
                "finished_at": "INTEGER DEFAULT 0",
                "highlighted": "INTEGER DEFAULT 0",
                "continue_from": "INTEGER DEFAULT 1",
                "status": "TEXT CHECK(status IN ('watchlist', 'completed'))",
                "description": "TEXT",
                "genres": "TEXT",
                "episode_duration": "TEXT",
                "poster": "TEXT NOT NULL UNIQUE",
                "type": "TEXT NOT NULL",
                "url": "TEXT NOT NULL UNIQUE",
                "airing_status": "TEXT",
                "message_id": "TEXT NOT NULL UNIQUE",
            },
        )


class DiscordDB:
    def __init__(self) -> None:
        env_vars = ["ANIPY_DATA_WEBHOOK", "ANIPY_DISCORD_TOKEN"]

        for e in env_vars:
            if not os.getenv(e):
                raise EnvVarNotFound(f"'{e}' environment variable isn't set")

        self.__wh = Webhook(os.environ["ANIPY_DATA_WEBHOOK"])
        self.__d = DiscordAPI(os.environ["ANIPY_DISCORD_TOKEN"])

    async def _load_webhooks(self) -> None:
        if not hasattr(self.__wh, "channel_id"):
            await self.__wh.info()

    async def last_updated(self) -> int:
        await self._load_webhooks()

        resp = await self.__d.get_channel(self.__wh.channel_id)
        pattern = r"anipy-\w+-(\d{10})"
        match = re.search(pattern, resp["name"])

        if not match:
            return await self.update_last_updated()

        return int(match.group(1))

    async def update_last_updated(self) -> int:
        await self._load_webhooks()

        ts = int(time.time())
        await self.__d.modify_channel(self.__wh.channel_id, {"name": f"anipy-data-{ts}"})

        return ts

    async def pull(self) -> AsyncGenerator[DataObject, None]:
        await self._load_webhooks()

        pages = lock_file_get_content().get(LockFileKeys.DB_PAGES, [])
        for msg in await self.__d.get_channel_messages_full(self.__wh.channel_id, pages):
            content_b64 = msg["content"]
            content_json = decompress_data(content_b64)
            content_json["message_id"] = msg["id"]

            yield DataObject(content_json)

    async def add(self, object: DataObject) -> str:
        msg_content = compress_data(object.json())
        code, resp = await self.__wh.send(Body(content=msg_content))
        if code != 200:
            raise BadResponse(f"{code}: {resp}")

        return resp["id"]

    async def update(self, object: DataObject, message_id: str) -> None:
        msg_content = compress_data(object.json())
        code, resp = await self.__wh.edit(message_id, Body(content=msg_content))
        if code != 200:
            raise BadResponse(f"{code}: {resp}")

    async def remove(self, message_id: str) -> None:
        code, resp = await self.__wh.delete(message_id)
        if code != 204:
            raise BadResponse(f"{code}: {resp}")


class Data:
    def __init__(self) -> None:
        self.remote = DiscordDB()
        self.local = LocalDB()

        self.datadict: dict[str, DataObject] = {}

    @property
    def watchlist(self) -> DataList:
        return DataList(sorted((o for o in self.datadict.values() if o.status == "watchlist"), key=lambda o: o.added_at))

    @property
    def completed(self) -> DataList:
        return DataList(sorted((o for o in self.datadict.values() if o.status == "completed"), key=lambda o: o.finished_at))

    async def load(self) -> None:
        print("   local data", end="")
        sys.stdout.flush()

        self.__lock_file_content = lock_file_get_content()
        remote_db_last_updated = await self.remote.last_updated()
        local_db_last_updated = self.__lock_file_content.get(LockFileKeys.DB_LAST_UPDATE, 0)

        objects = []

        if local_db_last_updated == 0:
            print("\r\033[1m:(\033[0m local data: not found", end="")
            sys.stdout.flush()

            async for object in self.remote.pull():
                self.datadict[object.id] = object
                objects.append(object)
            print("\r\033[1m=D\033[0m local data: pulled from remote")

            self.local.add(objects)
            lock_file_update(LockFileKeys.DB_LAST_UPDATE, remote_db_last_updated)

        elif remote_db_last_updated > local_db_last_updated:
            print("\r\033[1m:(\033[0m local data: outdated", end="")
            sys.stdout.flush()
            self.local.erase()

            async for object in self.remote.pull():
                self.datadict[object.id] = object
                objects.append(object)

            print("\r[ \033[1m=D\033[0m ] local data: pulled from remote")

            self.local.add(objects)
            lock_file_update(LockFileKeys.DB_LAST_UPDATE, remote_db_last_updated)

        elif remote_db_last_updated == local_db_last_updated:
            print("\r\033[1m=D\033[0m local data: sync")
            for object in self.local.pull():
                self.datadict[object.id] = object

        else:
            raise ValueError("cho")

    async def add(self, object: DataObject) -> None:
        message_id = await self.remote.add(object)
        object.message_id = message_id

        self.local.add([object])
        self.datadict[object.id] = object

        ts = await self.remote.update_last_updated()
        lock_file_update(LockFileKeys.DB_LAST_UPDATE, ts)

    async def update(self, object: DataObject) -> None:
        assert object.message_id

        message_id = object.message_id

        # unset object.message_id, so when object is sent to remote
        # it's not included in the json blob
        object.message_id = None
        await self.remote.update(object, message_id)

        object.message_id = message_id
        self.local.update(object)

        self.datadict[object.id] = object

        ts = await self.remote.update_last_updated()
        lock_file_update(LockFileKeys.DB_LAST_UPDATE, ts)

    async def remove(self, object: DataObject) -> None:
        assert object.message_id
        await self.remote.remove(object.message_id)
        self.local.remove(object)

        self.datadict.pop(object.id)

        ts = await self.remote.update_last_updated()
        lock_file_update(LockFileKeys.DB_LAST_UPDATE, ts)
