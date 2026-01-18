from typing import Any, Literal
from dataclasses import dataclass


@dataclass
class BaseObject:
    def __init__(self, obj: dict = {}) -> None:
        self.__obj = obj

        for k, v in self.__obj.items():
            if k != "version":
                setattr(self, k, v)

    def json(self) -> dict[str, Any]:
        d = {}

        for k in dir(self):
            v = getattr(self, k)
            if v is not None and not callable(v) and not k.startswith("_"):
                d[k] = v

        return d


class Extractor:
    headers: dict[str, str]

    def __init__(self, embed_url: str) -> None:
        self.embed_url = embed_url

    async def extract(self) -> dict: ...


class EpisodeSources:
    sources: list[dict]
    tracks: list[dict]
    intro: tuple[int, int]
    outro: tuple[int, int]

    def __init__(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)

    def attrs(self) -> list[str]:
        attrs = [i for i in dir(self) if not callable(getattr(self, i)) and not i.startswith("_")]
        return attrs


class EpisodeInfo(BaseObject):
    id: str
    title: str
    other_title: str
    num: int


class AnimeInfo(BaseObject):
    id: str
    title: str
    other_title: str
    episode_count: int
    airing_status: str
    url: str
    poster: str
    type: str
    episode_duration: str
    description: str
    genres: list[str]
    year: int
    episodes: list[EpisodeInfo]

    def __init__(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __getattr__(self, _: str) -> Any: ...


class SearchObject(BaseObject):
    id: str
    title: str
    other_title: str
    episode_count: int
    episode_duration: str
    type: str
    poster: str
    status: str = "search"


class DataObject(BaseObject):
    id: str
    url: str
    title: str
    other_title: str
    episode_count: int
    airing_status: str
    type: str
    year: int
    episode_duration: str
    description: str
    genres: str
    poster: str
    status: Literal["watchlist", "completed"]
    added_at: int
    highlighted: bool = False
    continue_from: int = 1
    finished_at: int = 0
    message_id: str | None = None


class SearchList(list[SearchObject]):
    name = "search"
    query: str

    def __init__(self, items: list[SearchObject], query: str) -> None:
        super().__init__(items)
        self.query = query


class DataList(list[DataObject]):
    name = "data"
