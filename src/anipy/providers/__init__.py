from typing import Protocol
from enum import StrEnum

from ..core.types import SearchObject, AnimeInfo, EpisodeSources
from .hianime import HiAnime
from .allmanga import AllManga


class Provider(Protocol):
    @property
    def extractor_headers(self) -> dict: ...

    async def search(self, title: str)           -> list[SearchObject]: ...
    async def get_anime_info(self, id: str)      -> AnimeInfo: ...
    async def get_episode_sources(self, anime_id: str, ep_num: int) -> EpisodeSources: ...

class ProviderTypes(StrEnum):
    HIANIME =  "hianime"
    ALLMANGA = "allmanga"

    @property
    def cls(self) -> type[Provider]:
        if self.value == self.HIANIME:
            return HiAnime

        if self.value == self.ALLMANGA:
            return AllManga

        raise ValueError(f"unknown provider: {self.value}")
