import os
import json
import sqlite3

from typing import Literal, get_origin, get_args
from enum import Enum

from attr import dataclass

from .types import DataObject, DataList, LockFileKeys, Serializable, Any
from ..providers import Providers

def get_user_config_dir() -> str:
    if os.name == "posix":
        path = os.path.join(os.environ["HOME"], ".config", "anipy")
    else:
        path = os.path.join(os.environ["APPDATA"], "anipy")

    if not os.path.exists(path):
        os.makedirs(path)

    return path


def get_user_data_dir() -> str:
    if os.name == "posix":
        path = os.path.join(os.environ["HOME"], ".local", "share", "anipy")
    else:
        path = os.path.join(os.environ["APPDATA"], "anipy")

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
    banner:     list[str]  = ["continue watching", "highlighted"]
    provider:   Providers  = Providers.ALLMANGA
    prompt:     str        = "{} > "

    def __init__(self) -> None:
        self.__path = os.path.join(get_user_config_dir(), "settings.json")
        self.__obj = {}

        if os.path.exists(self.__path):
            with open(self.__path, "r") as f:
                self.__obj = json.load(f)
                for k, v in self.__obj.items():
                    if k == "provider":
                        setattr(self, k, Providers(v))

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

def row_factory(cur: sqlite3.Cursor, row: tuple):
    keys = [t[0] for t in cur.description]
    return dict(zip(keys, row))

class DBManager:
    def __init__(self, path: str) -> None:
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.row_factory = row_factory

        self.cur = self.con.cursor()

    def create_table(self, table: str, scheme: dict) -> None:
        columns = ",\n\t".join([f"{k} {v}" if v is not None else k for k, v in scheme.items()])
        query = f"CREATE TABLE IF NOT EXISTS {table} (\n    {columns}\n);"

        self.cur.execute(query)
        self.con.commit()

    def select_one(self, table: str, filters: dict[str, Any]) -> dict | None:
        query = f"SELECT * FROM {table} WHERE {' AND '.join(k+' = ?' for k in filters.keys())}"

        cur = self.con.execute(query, (*filters.values(),))
        return cur.fetchone()


    def select_all(self, table: str, filters: dict[str, Any] | None = None) -> list[dict]:
        if filters:
            query = f"SELECT * FROM {table} WHERE {' AND '.join(k+' = ?' for k in filters.keys())}"
            cur = self.con.execute(query, (*filters.values(),))

        else:
            query = f"SELECT * FROM {table}"
            cur = self.con.execute(query)

        return cur.fetchall()

    def insert(self, table: str, row: dict) -> int:
        columns = ", ".join(row.keys())
        placeholders = ", ".join(":"+k for k in row.keys())
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

        cur = self.con.execute(query, row)
        self.con.commit()

        assert cur.lastrowid is not None
        return cur.lastrowid

    def insert_many(self, table: str, rows: list[dict]) -> int:
        columns = ", ".join(rows[0].keys())
        placeholders = ", ".join(":"+k for k in rows[0].keys())
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

        cur = self.con.executemany(query, rows)
        self.con.commit()

        assert cur.lastrowid is not None
        return cur.lastrowid

    def update(self, table: str, data: dict, filters: dict[str, Any]) -> None:
        placeholders = ", ".join([f"{k} = ?" for k in data.keys()])
        query = f"UPDATE {table} SET {placeholders} WHERE {' AND '.join(k+' = ?' for k in filters.keys())}"

        self.con.execute(query, (*data.values(), *filters.values()))
        self.con.commit()

    def delete(self, table: str, filters: dict[str, Any]) -> None:
        query = f"DELETE FROM {table} WHERE {' AND '.join(k+' = ?' for k in filters.keys())}"

        self.con.execute(query, (*filters.values(),))
        self.con.commit()

    def close(self) -> None:
        self.con.close()


@dataclass
class DataTable:
    name:   str
    scheme: dict

class Tables:
    DATA = DataTable(
        "data",
        {
                "id":               "INTEGER",

                "title":            "TEXT NOT NULL",
                "other_title":      "TEXT",

                "episode_count":    "INTEGER",
                "episode_duration": "INTEGER",

                "type":             "TEXT NOT NULL",
                "year":             "INTEGER",
                "airing_status":    "TEXT CHECK(airing_status IN ('finished', 'airing'))",

                "added_at":         "INTEGER",
                "finished_at":      "INTEGER DEFAULT 0",

                "highlighted":      "INTEGER DEFAULT 0",
                "continue_from":    "INTEGER DEFAULT 1",
                "status":           "TEXT CHECK(status IN ('watchlist', 'completed', 'dropped'))",

                "PRIMARY KEY (id AUTOINCREMENT)": None,
            }
    )

    IDS  = DataTable(
        "ids", 
        {
                "id":           "INTEGER",
                "source":       "TEXT NOT NULL",
                "external_id":  "TEXT NOT NULL",

                "PRIMARY KEY (provider, external_id)": None,
                "FOREIGN KEY (id) REFERENCES data(id)": None,
        }
    )


class Data(DBManager):
    def __init__(self) -> None:
        db_filename = f"data.db"
        path = os.path.join(get_user_data_dir(), db_filename)

        super().__init__(path)

        self.create_table(Tables.DATA.name, Tables.DATA.scheme)
        self.create_table(Tables.IDS.name, Tables.IDS.scheme)


    @property
    def watchlist(self) -> DataList:
        d = self.select_all(Tables.DATA.name, {"status": "watchlist"})
        srted = sorted(d, key=lambda o: o['added_at'])
        return DataList(srted)

    @property
    def completed(self) -> DataList:
        d = self.select_all(Tables.DATA.name, {"status": "completed"})
        srted = sorted(d, key=lambda o: o['finished_at'])
        return DataList(srted)

    @property
    def dropped(self) -> DataList:
        d = self.select_all(Tables.DATA.name, {"status": "dropped"})
        srted = sorted(d, key=lambda o: o['added_at'])
        return DataList(srted)

    def remove_anime(self, anime: DataObject) -> None:
        self.delete(Tables.IDS.name, {"id": anime.id})
        self.delete(Tables.DATA.name, {"id": anime.id})
