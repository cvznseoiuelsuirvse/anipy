from enum import StrEnum
from typing import Any, Literal
from dataclasses import dataclass
from typing import TypedDict
import inspect

type Serializable = str | int | list | dict
type AiringStatus = Literal["finished", "airing"]
type ItemStatus =   Literal["completed", "watchlist", "dropped"]


class BaseObject:
    def __init__(self, obj: dict = {}) -> None:
        self.__obj = obj

        an = inspect.get_annotations(type(self))

        for k, v in self.__obj.items():
            if k in an:
                setattr(self, k, v)

    def json(self) -> dict[str, Any]:
        d = {}

        for k in dir(self):
            v = getattr(self, k)
            if v is not None and not callable(v) and not k.startswith("_"):
                d[k] = v

        return d

class JsonSerializable:
    def json(self) -> dict:
        d = {}

        for k in dir(self):
            if not k.startswith("_"):
                v = getattr(self, k)
                if v is not None and not callable(v):
                    if isinstance(v, JsonSerializable):
                        d[k] = v.json()
                    else:
                        d[k] = v

        return d



@dataclass
class EpisodeSources(JsonSerializable):
    source:     str
    tracks:     list[dict]
    intro:      tuple[int, int]
    outro:      tuple[int, int]

class EpisodeInfo(JsonSerializable):
    id:                 str
    title:              str
    other_title:        str
    num:                int

@dataclass
class AnimeInfo(JsonSerializable):
    external_id:        str
    mal_id:             str | None

    title:              str
    other_title:        str

    description:        str
    year:               int
    genres:             list[str]
    airing_status:      AiringStatus
    type:               str

    episode_count:      int
    episode_duration:   int

    # episodes:           list[EpisodeInfo]


@dataclass
class SearchObject(JsonSerializable):
    external_id:        str

    title:              str
    other_title:        str

    episode_count:      int
    episode_duration:   int
    type:               str

@dataclass
class DataObject(JsonSerializable):
    status:             ItemStatus

    title:              str
    other_title:        str

    episode_count:      int
    episode_duration:   int

    type:               str
    year:               int
    airing_status:      AiringStatus

    added_at:           int
    finished_at:        int = 0

    highlighted:        bool = False
    continue_from:      int = 1
    id:                 int = 0

class DataObjectDict(TypedDict):
    id:                 int
    status:             ItemStatus

    title:              str
    other_title:        str

    episode_count:      int
    episode_duration:   int

    type:               str
    year:               int
    airing_status:      AiringStatus

    added_at:           int
    finished_at:        int

    highlighted:        bool
    continue_from:      int


class SearchList(list[SearchObject]):
    name = "search"
    query: str

    def __init__(self, items: list[SearchObject], query: str) -> None:
        super().__init__(items)
        self.query = query


class DataList(list[DataObject]):
    name = "data"


class LockFileKeys(StrEnum):
    DB_LAST_UPDATE = "db_last_updated"
    DB_PAGES = "db_pages"
    WATCHLIST_LAST_REFRESH = "watchlist_last_refresh"
