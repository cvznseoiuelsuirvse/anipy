from enum import StrEnum
from typing import Any, Literal
from dataclasses import dataclass

type Serializable = str | int | list | dict
type AiringStatus = Literal["finished", "airing"]
type ItemStatus =   Literal["completed", "watchlist"]


class BaseObject:
    def __init__(self, obj: dict = {}) -> None:
        self.__obj = obj

        for k, v in self.__obj.items():
            setattr(self, k, v)

    def json(self) -> dict[str, Any]:
        d = {}

        for k in dir(self):
            v = getattr(self, k)
            if v is not None and not callable(v) and not k.startswith("_"):
                d[k] = v

        return d


@dataclass
class EpisodeSources(BaseObject):
    source:     str
    tracks:     list[dict]
    intro:      tuple[int, int]
    outro:      tuple[int, int]

class EpisodeInfo(BaseObject):
    id:                 str
    title:              str
    other_title:        str
    num:                int

@dataclass
class AnimeInfo(BaseObject):
    external_id:        str

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
class SearchObject(BaseObject):
    external_id:        str
    title:              str
    other_title:        str
    episode_count:      int
    episode_duration:   int
    type:               str

class DataObject(BaseObject):
    id:                 int
    external_id:        str

    title:              str
    other_title:        str

    episode_count:      int
    episode_duration:   int

    type:               str
    year:               int
    added_at:           int
    airing_status:      AiringStatus

    status:             ItemStatus
    highlighted:        bool = False
    continue_from:      int = 1
    finished_at:        int = 0



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
