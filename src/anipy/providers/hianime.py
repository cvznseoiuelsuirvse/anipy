import asyncio
import functools
import json
import re
import aiohttp

from enum import StrEnum
from html import unescape
from typing import overload, Literal, Awaitable, Callable, TypeVar

from ..core.exceptions import AttributeNotFound
from ..core.types import AnimeInfo, EpisodeInfo, EpisodeSources, SearchObject, Servers
from ..extractors import Extractors

BASE_URL = "https://hianimez.to/"

clean = lambda h: unescape(re.sub(r"\s", " ", h))


def __make_key(args, kwargs):
    return (args, tuple(sorted(kwargs.items())))


def cache(func):
    __cache = {}

    if asyncio.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            key = __make_key(args, kwargs)
            if key in __cache:
                return __cache[key]

            value = await func(*args, **kwargs)
            __cache[key] = value

            return value

        return async_wrapper

    else:

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            key = __make_key(args, kwargs)

            if key in __cache:
                return __cache[key]

            value = func(*args, **kwargs)
            __cache[key] = value

            return value

        return sync_wrapper


async def make_request[T](route: str, params: dict, func: Callable[[aiohttp.ClientResponse], Awaitable[T]]) -> T:
    url = BASE_URL + route
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0"}

    async with aiohttp.ClientSession() as client:
        async with client.get(url, headers=headers, params=params) as resp:
            return await func(resp)


class Patterns(StrEnum):
    CARD = r"<div class=\"flw-item\">(.+?)<div class=\"clearfix\"><\/div>"
    POSTER = r"<img.+?src=\"(?P<src>[^\"]+).+?>"
    DYNAMIC_NAME = r"<h3.+?<a href=\"(?P<href>[^\"]+)\" title=\"(?P<title>[^\"]+)\".+?data-jname=\"(?P<jtitle>[^\"]*).+?>"
    DYNAMIC_NAME2 = r"<h2.+?data-jname=\"(?P<jtitle>[^\"]*).+?>(?P<title>[^<]+)"
    EPISODE_COUNT = r"<div class=\"tick-item tick-sub\">.+?<\/i>(\d+).+?>"
    ID = r"\/([\w\-]+)?"

    ANIS_CONTENT = r"<div class=\"anis-content\">(.+?)<!"
    ANISC_DETAIL = r"<div class=\"anisc-detail\">(.+?)Share Anime"
    ANISC_INFO_WRAP = r"<div class=\"anisc-info-wrap\">(.+?)clearfix"

    DESCRIPTION = r"Overview:.+?text\">([^<]+)"
    ITEM = r"<span class=\"item\">([^<]+)<\/span>"
    ITEM2 = r"<span class=\"fdi-item[^>]+>([^<]+)<\/span>"
    ITEM_TITLE = r"<div class=\"item item-title\">[^>]+>(?P<key>[\w ]+).+?name\">(?P<value>[^<]+)<\/span>"

    GENRE = r"<a.+?title=\"([\w ]+)\">"

    EPISODE = r"<a title=\"(?P<title>.+?)\".+?data-id=\"(?P<id>\d+).+?data-jname=\"(?P<jtitle>[^\"]*)"
    SERVER = r"<div class=\"item server-item\" data-type=\"sub\" data-id=\"(?P<source_id>\d+)\".+?data-server-id=\"(?P<server_id>\d+)\">"

    def fmt(self, **kwargs) -> "Patterns":
        for k, v in kwargs.items():
            v = re.escape(v)
            self._fmted = self.value.replace(f"%%{k}%%", v)

        return self

    @property
    def formatted(self) -> str:
        return getattr(self, "_fmted", self.value)


DEFAULT = object()
T = TypeVar("T")


@overload
def _re(pattern: "Patterns", string: str) -> re.Match: ...
@overload
def _re(pattern: "Patterns", string: str, *, default: T) -> re.Match | T: ...
@overload
def _re(pattern: "Patterns", string: str, *, all: Literal[True]) -> list[str]: ...
@overload
def _re(pattern: "Patterns", string: str, *, all: Literal[True], default: T) -> list[str] | T: ...


def _re(pattern: "Patterns", string: str, *, all: bool = False, default: T = DEFAULT) -> re.Match | list[str] | T:
    v = re.findall(pattern.formatted, string) if all else re.search(pattern.formatted, string)

    if not v and default is DEFAULT:
        msg = f"{pattern.name} not found"
        raise ValueError(msg)

    elif not v:
        return default

    return v


class Provider:
    def _card_scraper(self, card: str) -> dict:
        ret = {}
        card = clean(card)

        dynamic_name = _re(Patterns.DYNAMIC_NAME, card)
        poster = _re(Patterns.POSTER, card)
        sub_count = _re(Patterns.EPISODE_COUNT, card, default=None)

        href = dynamic_name.group("href")
        ret["id"] = _re(Patterns.ID, href).group(1)
        ret["title"] = dynamic_name.group("title")
        ret["other_title"] = dynamic_name.group("jtitle")

        ret["episode_count"] = int(sub_count.group(1)) if sub_count is not None else 0
        ret["url"] = BASE_URL + ret["id"]
        ret["poster"] = poster.group("src")

        items = _re(Patterns.ITEM2, card, all=True)

        ret["type"] = items[0]
        ret["episode_duration"] = items[1]

        return ret

    async def search(self, query: str, page: int) -> list[dict]:
        params = {"keyword": query, "page": page}
        html_page = await make_request("search", params, lambda r: r.text())
        html_page = re.sub(r"\s", " ", html_page)

        all_cards = _re(Patterns.CARD, html_page, all=True, default=[])
        return [self._card_scraper(card) for card in all_cards]

    async def _get_episode_list(self, anime_id: str) -> list[dict]:
        ret = []
        num_id = anime_id.split("-")[-1]

        resp = await make_request(f"ajax/v2/episode/list/{num_id}", {}, lambda i: i.text())
        html_page = clean(json.loads(resp)["html"])

        episodes = _re(Patterns.EPISODE, html_page, all=True)

        for i, episode in enumerate(episodes):
            ep_info = {
                "id": episode[1],
                "title": episode[0],
                "other_title": episode[2],
                "num": i + 1,
            }

            ret.append(ep_info)

        return ret

    async def get_anime_info(self, anime_id: str) -> dict:
        ret = {}

        html_page = await make_request(anime_id, {}, lambda r: r.text())
        html_page = clean(html_page)

        anis_content = _re(Patterns.ANIS_CONTENT, html_page).group(1)
        anisc_detail = _re(Patterns.ANISC_DETAIL, anis_content).group(1)
        anisc_info_wrap = _re(Patterns.ANISC_INFO_WRAP, anis_content).group(1)

        dynamic_name = _re(Patterns.DYNAMIC_NAME2, anis_content).groupdict()
        poster = _re(Patterns.POSTER, anis_content)

        sub_count = _re(Patterns.EPISODE_COUNT, anis_content, default=None)
        ret["id"] = anime_id
        ret["title"] = dynamic_name["title"]
        ret["other_title"] = dynamic_name["jtitle"]

        ret["episode_count"] = int(sub_count.group(1)) if sub_count is not None else 0

        ret["url"] = BASE_URL + anime_id
        ret["poster"] = poster.group("src")

        items = _re(Patterns.ITEM, anisc_detail, all=True)
        ret["type"] = items[0]
        ret["episode_duration"] = items[1]

        description = _re(Patterns.DESCRIPTION, anisc_info_wrap, default=None)
        description = description.group(1) if description is not None else ""
        ret["description"] = description.replace("[Written by MAL Rewrite]", "").strip()

        ret["genres"] = [m for m in _re(Patterns.GENRE, anisc_info_wrap, all=True)]

        item_titles = _re(Patterns.ITEM_TITLE, anisc_info_wrap, all=True)
        for item_title in item_titles:
            key = item_title[0].lower()
            value = item_title[1]

            if key == "aired":
                year = re.search(r"(\d{4})", value)
                assert year

                value = int(year.group(1))
                ret["year"] = value

            elif key == "status":
                status = re.sub(r" ?air\w+ ?", "", value.lower())
                ret["airing_status"] = status.strip()

        ret["episodes"] = await self._get_episode_list(anime_id)

        return ret

    async def get_episode_sources(self, episode_id: str, extractor: Extractors, server: Servers) -> dict:
        if extractor == Extractors.MEGACLOUD:
            resp = await make_request("ajax/v2/episode/servers", {"episodeId": episode_id}, lambda i: i.text())

            html_page: str = json.loads(resp)["html"]
            html_page = html_page.replace(r"\"", '"')
            html_page = clean(html_page)

            servers = _re(Patterns.SERVER, html_page, all=True)

            for s in servers:
                server_id = s[1]

                if server_id == server:
                    source_id = s[0]
                    break

            else:
                raise AttributeNotFound("source id not found")

            resp = await make_request("ajax/v2/episode/sources", {"id": source_id}, lambda i: i.text())
            video_url = json.loads(resp)["link"]

            megacloud_extractor = extractor.value
            e = megacloud_extractor(video_url)
            ep_info = await e.extract()

        else:
            megaplay_extractor = extractor.value
            e = megaplay_extractor(episode_id)
            ep_info = await e.extract()

        return ep_info


class HiAnimeAPI:
    def __init__(self):
        self.provider = Provider()

    @cache
    async def search(self, title: str, page: int = 1) -> list[SearchObject]:
        resp = await self.provider.search(title, page)
        return [SearchObject(r) for r in resp]

    @cache
    async def get_anime_info(self, anime_id: str) -> AnimeInfo:
        resp = await self.provider.get_anime_info(anime_id)
        episodes = [EpisodeInfo(ep) for ep in resp["episodes"]]
        resp["episodes"] = episodes
        return AnimeInfo(**resp)

    @cache
    async def get_episode_sources(self, episode_id: str, extractor: Extractors, server: Servers) -> EpisodeSources:
        ep_sources = await self.provider.get_episode_sources(episode_id, extractor, server)
        ep_sources = EpisodeSources(**ep_sources)

        return ep_sources
