import aiohttp
import json
import re
from typing import Callable, Awaitable
from enum import EnumDict

from ...core.exceptions import InvalidResponse, InvalidStatusCode
from ...core.util import cache
from ...core.types import SearchObject, AnimeInfo, EpisodeSources, AiringStatus
from .extractor import AllAnime

BASE_URL = "https://api.mkissa.net/api"
HOST = "youtu-chan.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0",
    "Origin": f"https://{HOST}",
    "Referer": f"https://{HOST}/",
}

class Exts(EnumDict):
    SEARCH = {"persistedQuery":{"version":1,"sha256Hash":"a24c500a1b765c68ae1d8dd85174931f661c71369c89b92b88b75a725afc471c"}}
    INFO = {"persistedQuery":{"version":1,"sha256Hash":"043448386c7a686bc2aabfbb6b80f6074e795d350df48015023b079527b0848a"}}
    EPISODE = {
        "persistedQuery": {
            "version":1,
            "sha256Hash":"f4662f4b7510b26795dd53ef824a0bf1740fbbc5d1273fab18222ac831bca8d0",
        },
        "k": "k7",
    }


async def make_request[T](params: dict, *, headers: dict = {}, func: Callable[[aiohttp.ClientResponse], Awaitable[T]]) -> T:
    headers |= HEADERS

    async with aiohttp.ClientSession() as client:
        async with client.get(BASE_URL, headers=headers, params=params) as resp:
            if resp.status != 200:
                raise InvalidStatusCode(resp.status, resp.url)

            try:
                return await func(resp)

            except Exception:
                raise InvalidResponse(resp.status, resp.url)


def clean_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<.*?>|\n", "", s))


class AllManga:
    extractor_headers = AllAnime.headers

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

        resp = await make_request({"variables": variables, "extensions": exts}, func=lambda r: r.json())

        l = []
        data = resp['data']['shows']['edges']

        for d in data:
            l.append(SearchObject(
                external_id=d["_id"],
                title=d["englishName"],
                other_title=d["name"],
                episode_count=d['availableEpisodes']['sub'],
                episode_duration=int(d['episodeDuration']),
                type=d['type']
            ))

        return l

    @staticmethod
    @cache
    async def get_anime(id: str) -> AnimeInfo:
        variables = json.dumps({
            "_id": id
        })
        exts = json.dumps(Exts.INFO)

        resp = await make_request({"variables": variables, "extensions": exts}, func=lambda r: r.json())

        d = resp['data']['show']
        airing_status: AiringStatus = 'airing' if d['status'] == "Releasing" else 'finished'

        return AnimeInfo(
            external_id=id,
            mal_id=None,
            title=d["englishName"],
            other_title=d["name"],
            episode_count=d['availableEpisodes']['sub'],
            episode_duration=int(d['episodeDuration']),
            type=d['type'],
            description=clean_html(d['description']),
            year=d['season']['year'],
            genres=d['genres'],
            airing_status=airing_status,
        )


    @staticmethod
    async def get_episodes(anime_id: str, ep_num: int) -> EpisodeSources:
        variables = json.dumps({
            "showId": anime_id,
            "translationType": "sub",
            "episodeString": str(ep_num),
        })

        exts: dict = Exts.EPISODE

        aa_req = await AllAnime.generate_aareq(exts['persistedQuery']['sha256Hash'], HOST)
        exts['aaReq'] = aa_req['aa_req']
        exts_string = json.dumps(exts)

        headers = {
            "x-build-id": aa_req["build_id"]
        }

        resp = await make_request(
            {"variables": variables, "extensions": exts_string},
            headers=headers, func=lambda r: r.json()
        )

        if 'errors' in resp:
            raise InvalidResponse(resp['errors'])

        return await AllAnime.exctract(resp)
