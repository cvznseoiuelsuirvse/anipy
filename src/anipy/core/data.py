import os
import json
import sqlite3

from typing import Literal, get_origin, get_args

from .types import DataObject, DataList, LockFileKeys, Serializable
from ..providers import ProviderTypes

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
    banner:     list[str]               = ["continue watching", "highlighted"]
    provider:   ProviderTypes           = ProviderTypes.HIANIME
    prompt:     str                     = "{} > "

    def __init__(self) -> None:
        self.__path = os.path.join(get_user_config_dir(), "settings.json")
        self.__obj = {}

        if os.path.exists(self.__path):
            with open(self.__path, "r") as f:
                self.__obj = json.load(f)
                for k, v in self.__obj.items():
                    if k == "provider":
                        setattr(self, k, ProviderTypes(v))

                    else:
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


class Condition:
    def __init__(self, column: str, expression: str, values: list) -> None:
        self.column = column
        self.expession = expression.upper()
        self.values = values

    def __str__(self) -> str:
        placeholders = ", ".join(["?"] * len(self.values))

        if self.expession == "in":
            placeholders = f"({placeholders})"

        return f"{self.column} {self.expession} {placeholders}"


class DBManager:
    def __init__(self, path: str) -> None:
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row


    def create(self, table: str, fields: dict) -> None:
        columns = ",\n\t".join([f"{k} {v}" if v is not None else k for k, v in fields.items()])
        query = f"CREATE TABLE IF NOT EXISTS {table} (\n    {columns}\n);"

        self.con.execute(query)
        self.con.commit()

    def select(self, table: str, conditions: list[Condition] | None = None) -> list[dict]:
        if conditions:
            params = [v for c in conditions for v in c.values]
            query = f"SELECT * FROM {table} WHERE {' AND '.join(map(str, conditions))}"

        else:
            params = []
            query = f"SELECT * FROM {table}"

        cur = self.con.execute(query, params)
        return list(map(dict, cur.fetchall()))

    def insert(self, table: str, row: dict) -> None:
        placeholders = ", ".join(["?"] * len(row))
        keys, values = zip(*sorted(row.items()))

        query = f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({placeholders})"

        self.con.execute(query, values)
        self.con.commit()

    def insert_many(self, table: str, rows: list[dict]) -> None:
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

    def update(self, table: str, data: dict, conditions: list[Condition]) -> None:
        placeholders = ", ".join([f"{k} = ?" for k in data.keys()])
        query = f"UPDATE {table} SET {placeholders} WHERE {' AND '.join(map(str, conditions))}"

        params = list(data.values()) + [v for c in conditions for v in c.values]

        self.con.execute(query, params)
        self.con.commit()

    def delete(self, table: str, conditions: list[Condition]) -> None:
        params = [v for c in conditions for v in c.values]
        query = f"DELETE FROM {table} WHERE {' AND '.join(map(str, conditions))}"

        self.con.execute(query, params)
        self.con.commit()

    def close(self) -> None:
        self.con.close()


class LocalDB:
    def __init__(self, provider: ProviderTypes) -> None:
        db_filename = f"data.db"
        self.__path = os.path.join(get_user_data_dir(), db_filename)

        self.__db = DBManager(self.__path)
        self.__provider = provider

        self.__main_table = "data"
        self.__ids_table =  "ids"

        self._create_main_table()
        self._create_ids_table()

    def get_all(self) -> list[DataObject]:
        l = []

        for o in self.__db.select(self.__main_table):
            do = DataObject(o)
            do.external_id = self.get_external_id(do.id) or ""
            l.append(do)

        return l

    def erase(self) -> None:
        os.remove(self.__path)
        self.__init__(self.__provider)

    def add(self, object: DataObject) -> None:
        data = object.json()
        self.__db.insert(self.__main_table, data)
        self.add_id(object)

    def add_id(self, object: DataObject) -> None:
        self.__db.insert(
            self.__ids_table, 
            {
                "id": object.id, 
                "provider": self.__provider, 
                "external_id": object.external_id
            }
        )

    def get_external_id(self, internal_id: int) -> str | None:
        conds = [
            Condition("id", "=", [internal_id]),
            Condition("provider", "=", [self.__provider]),
        ]
        res = self.__db.select(self.__ids_table, conds)
        if not res: 
            return None

        return res[0]['external_id']

    def update(self, object: DataObject) -> None:
        d = object.json()
        d.pop("id")

        self.__db.update(self.__main_table, d, [Condition("id", "=", [object.id])])

    def remove(self, object: DataObject) -> None:
        self.__db.delete(self.__main_table, [Condition("id", "=", [object.id])])

    def _create_main_table(self) -> None:
        self.__db.create(
            self.__main_table,
            {
                "id": "INTEGER",
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
                "type": "TEXT NOT NULL",
                "airing_status": "TEXT CHECK(airing_status IN ('finished', 'airing'))",
                "PRIMARY KEY (id AUTOINCREMENT)": None,
            },
        )

    def _create_ids_table(self) -> None:
        self.__db.create(
            self.__ids_table,
            {
                "id": "INTEGER",
                "provider": "TEXT NOT NULL",
                "external_id": "TEXT NOT NULL",
                "PRIMARY KEY (provider, external_id)": None,
                "FOREIGN KEY (id) REFERENCES data(id)": None,
            },
        )


class MalDB: ...

class Data:
    def __init__(self, provider: ProviderTypes) -> None:
        self.local = LocalDB(provider)
        self.provider = provider
        self.data: list[DataObject]

    @property
    def watchlist(self) -> DataList:
        return DataList(sorted((o for o in self.data if o.status == "watchlist"), key=lambda o: o.added_at))

    @property
    def completed(self) -> DataList:
        return DataList(sorted((o for o in self.data if o.status == "completed"), key=lambda o: o.finished_at))

    def load(self) -> None:
        self.data = self.local.get_all()

    def add(self, object: DataObject) -> None:
        self.local.add(object)
        self.data.append(object)

    def add_id(self, object: DataObject, external_id: str) -> None:
        object.external_id = external_id
        self.local.add_id(object)

    def update(self, object: DataObject) -> None:
        self.local.update(object)

    def remove(self, object: DataObject) -> None:
        self.local.remove(object)
        self.data.pop(object.id)


if __name__ == "__main__": ...
