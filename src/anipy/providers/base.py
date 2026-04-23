from ..core.util import cache
from ..core.types import SearchObject, AnimeInfo, EpisodeSources, EpisodeInfo
from typing import Protocol
from .hianime import HiAnime
from .allmanga import AllManga

from enum import StrEnum

class ProviderBase(Protocol):
    @property
    def headers(self) -> dict: ...

    @property
    def extractor_headers(self) -> dict: ...

    async def search(self, title: str)           -> list[dict]: ...
    async def get_anime_info(self, id: str)      -> dict: ...
    async def get_episode_sources(self, id: str) -> dict: ...

class ProviderTypes(StrEnum):
    HIANIME =  "hianime"
    ALLMANGA = "allmanga"

    @property
    def cls(self) -> type[ProviderBase]:
        if self.value == self.HIANIME:
            return HiAnime

        if self.value == self.ALLMANGA:
            return AllManga

        raise ValueError(f"{self.value} unknown provider")

class Provider:
    def __init__(self, provider_cls: type[ProviderBase]):
        self.provider = provider_cls()

    @cache
    async def search(self, title: str) -> list[SearchObject]:
        resp = await self.provider.search(title)
        return [SearchObject(r) for r in resp]

    @cache
    async def get_anime_info(self, id: str) -> AnimeInfo:
        resp = await self.provider.get_anime_info(id)
        episodes = [EpisodeInfo(ep) for ep in resp["episodes"]]
        resp["episodes"] = episodes
        return AnimeInfo(**resp)

    @cache
    async def get_episode_sources(self, id: str) -> EpisodeSources:
        ep_sources = await self.provider.get_episode_sources(id)
        ep_sources = EpisodeSources(**ep_sources)

        return ep_sources
