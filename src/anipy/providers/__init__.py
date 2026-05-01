from typing import Protocol
from enum import StrEnum

from ..core.types import SearchObject, AnimeInfo, EpisodeSources
from ..core.exceptions import ProviderUnknown

from .hianime import HiAnime
from .allmanga import AllManga
from .animekai import AnimeKai


class Provider(Protocol):
    extractor_headers: dict

    @staticmethod
    async def search(title: str)                       -> list[SearchObject]: ...
    @staticmethod
    async def get_anime(id: str)                       -> AnimeInfo: ...
    @staticmethod
    async def get_episodes(anime_id: str, ep_num: int) -> EpisodeSources: ...

class Providers(StrEnum):
    HIANIME =  "hianime"
    ALLMANGA = "allmanga"
    ANIMEKAI = "animekai"

    @property
    def cls(self) -> type[Provider]:
        if self.value == self.HIANIME:
            return HiAnime

        if self.value == self.ALLMANGA:
            return AllManga

        if self.value == self.ANIMEKAI:
            return AnimeKai

        raise ProviderUnknown(self.value)
