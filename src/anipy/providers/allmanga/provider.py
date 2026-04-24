import aiohttp
import json
import html
from typing import Callable, Awaitable
from enum import EnumDict

from anipy.providers.allmanga.extractor import AllAnimeExctractor

from ...core.exceptions import ProviderRequestFailed
from ...core.util import cache
from ...core.types import SearchObject, AnimeInfo, EpisodeSources, AiringStatus


class Exts(EnumDict):
    SEARCH = {"persistedQuery":{"version":1,"sha256Hash":"a24c500a1b765c68ae1d8dd85174931f661c71369c89b92b88b75a725afc471c"}}
    INFO = {"persistedQuery":{"version":1,"sha256Hash":"043448386c7a686bc2aabfbb6b80f6074e795d350df48015023b079527b0848a"}}
    EPISODE = {"persistedQuery":{"version":1,"sha256Hash":"d405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec"}}

BASE_URL = "https://api.allanime.day/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0",
    "Origin": "https://allmanga.to",
    "Referer": "https://allmanga.to/",
}

async def make_request[T](params: dict, func: Callable[[aiohttp.ClientResponse], Awaitable[T]]) -> tuple[int, T]:
    async with aiohttp.ClientSession() as client:
        async with client.get(BASE_URL, headers=HEADERS, params=params) as resp:
            return resp.status, await func(resp)

class AllManga:
    @property
    def extractor_headers(self) -> dict: 
        return {
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0",
            "referer": "https://allanime.day/",
        }


    @cache
    async def search(self, title: str) -> list[SearchObject]:
        variables = json.dumps({
            "search": {"query": title},
            "limit": 25,
            "page": 1,
            "translationType": "sub",
            "countryOrigin": "ALL",
        })
        exts = json.dumps(Exts.SEARCH)

        status, resp = await make_request({"variables": variables, "extensions": exts}, lambda r: r.json())
        if status != 200:
            raise ProviderRequestFailed

        l = []
        data = resp['data']['shows']['edges']

        for d in data:
            l.append(SearchObject(
                external_id=d["_id"],
                title=d["englishName"],
                other_title=d["name"],
                episode_count=d['availableEpisodes']['sub'],
                episode_duration=d['episodeDuration'],
                type=d['type']
            ))

        return l

    @cache
    async def get_anime_info(self, id: str) -> AnimeInfo:
        variables = json.dumps({
            "_id": id
        })
        exts = json.dumps(Exts.INFO)

        status, resp = await make_request({"variables": variables, "extensions": exts}, lambda r: r.json())
        if status != 200:
            raise ProviderRequestFailed

        d = resp['data']['show']
        airing_status: AiringStatus = 'airing' if d['status'] == "Releasing" else 'finished'

        return AnimeInfo(
            external_id=id,
            title=d["englishName"],
            other_title=d["name"],
            episode_count=d['availableEpisodes']['sub'],
            episode_duration=d['episodeDuration'],
            type=d['type'],
            description=html.unescape(d['description']),
            year=d['season']['year'],
            genres=d['genres'],
            airing_status=airing_status,
        )


    @cache
    async def get_episode_sources(self, anime_id: str, ep_num: int) -> EpisodeSources:
        variables = json.dumps({
            "showId": anime_id,
            "translationType": "sub",
            "episodeString": str(ep_num),
        })

        exts = json.dumps(Exts.EPISODE)

        status, resp = await make_request({"variables": variables, "extensions": exts}, lambda r: r.json())
        if status != 200:
            raise ProviderRequestFailed


        e = AllAnimeExctractor()
        return e.exctract(resp)
