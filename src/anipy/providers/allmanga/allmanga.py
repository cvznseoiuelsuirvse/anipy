import aiohttp
import json
import re
from typing import Callable, Awaitable
from enum import EnumDict

from ...core.exceptions import ProviderRequestFailed
from ...core.util import cache
from ...core.types import SearchObject, AnimeInfo, EpisodeSources, AiringStatus
from .allanime import AllAnime


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

async def make_request[T](params: dict, func: Callable[[aiohttp.ClientResponse], Awaitable[T]]) -> T:
    async with aiohttp.ClientSession() as client:
        async with client.get(BASE_URL, headers=HEADERS, params=params) as resp:
            if resp.status != 200:
                raise ProviderRequestFailed(resp.url)

            try:
                return await func(resp)

            except Exception:
                raise ProviderRequestFailed(resp.url)


def clean_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<.*?>|\n", "", s))

class AllManga:
    extractor_headers: dict = {
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0",
            "referer": "https://allanime.day/",
        }


    @staticmethod
    @cache
    async def search(title: str) -> list[SearchObject]:
        variables = json.dumps({
            "search": {"query": title},
            "limit": 25,
            "page": 1,
            "translationType": "sub",
            "countryOrigin": "ALL",
        })
        exts = json.dumps(Exts.SEARCH)

        resp = await make_request({"variables": variables, "extensions": exts}, lambda r: r.json())

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

    @staticmethod
    @cache
    async def get_anime_info(id: str) -> AnimeInfo:
        variables = json.dumps({
            "_id": id
        })
        exts = json.dumps(Exts.INFO)

        resp = await make_request({"variables": variables, "extensions": exts}, lambda r: r.json())

        d = resp['data']['show']
        airing_status: AiringStatus = 'airing' if d['status'] == "Releasing" else 'finished'

        return AnimeInfo(
            external_id=id,
            mal_id=None,
            title=d["englishName"],
            other_title=d["name"],
            episode_count=d['availableEpisodes']['sub'],
            episode_duration=d['episodeDuration'],
            type=d['type'],
            description=clean_html(d['description']),
            year=d['season']['year'],
            genres=d['genres'],
            airing_status=airing_status,
        )


    @staticmethod
    async def get_episode_sources(anime_id: str, ep_num: int) -> EpisodeSources:
        variables = json.dumps({
            "showId": anime_id,
            "translationType": "sub",
            "episodeString": str(ep_num),
        })

        exts = json.dumps(Exts.EPISODE)

        resp = await make_request({"variables": variables, "extensions": exts}, lambda r: r.json())

        return AllAnime.exctract(resp)
