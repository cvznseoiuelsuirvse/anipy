import json
import datetime
import re
import aiohttp

from enum import StrEnum
from html import unescape
from typing import overload, Literal, Awaitable, Callable, TypeVar

from .megacloud import Servers, Megacloud
from ...core.util import cache
from ...core.exceptions import ProviderRequestFailed
from ...core.types import SearchObject, AnimeInfo, EpisodeSources, AiringStatus

BASE_URL = "https://aniwatchtv.to/"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0"}

clean = lambda h: unescape(re.sub(r"\s", " ", h))


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
        raise ProviderRequestFailed(msg)

    elif not v:
        return default

    return v

async def make_request[T](route: str, params: dict, func: Callable[[aiohttp.ClientResponse], Awaitable[T]]) -> T:
    url = BASE_URL + route

    async with aiohttp.ClientSession() as client:
        async with client.get(url, headers=HEADERS, params=params) as resp:
            return await func(resp)

def convert_ep_duration(s: str) -> int:
    s = s.lower()

    if "?" in s:
        return 0

    if "h" in s:
        dt = datetime.datetime.strptime(s, "%Hh %Mm")
        return dt.hour * 60 * 60000 + dt.minute * 60000

    dt = datetime.datetime.strptime(s, "%Mm")
    return dt.minute * 60000


def card_scraper(card: str) -> SearchObject:
    card = clean(card)

    dynamic_name = _re(Patterns.DYNAMIC_NAME, card)
    sub_count = _re(Patterns.EPISODE_COUNT, card, default=None)

    href = dynamic_name.group("href")
    external_id = _re(Patterns.ID, href).group(1)
    title = dynamic_name.group("title")
    other_title = dynamic_name.group("jtitle")

    episode_count = int(sub_count.group(1)) if sub_count is not None else 0

    items = _re(Patterns.ITEM2, card, all=True)

    type = items[0]
    episode_duration = items[1]

    return SearchObject(
        external_id=external_id,
        title=title,
        other_title=other_title,
        episode_count=episode_count,
        episode_duration=convert_ep_duration(episode_duration),
        type=type,
    )

@cache
async def get_episode_ids(anime_id: str) -> list[str]:
    num_id = anime_id.split("-")[-1]

    resp = await make_request(f"ajax/v2/episode/list/{num_id}", {}, lambda i: i.text())
    html_page = clean(json.loads(resp)["html"])

    episodes = _re(Patterns.EPISODE, html_page, all=True)

    return [ep[1] for ep in episodes]


class HiAnime:
    extractor_headers: dict = Megacloud.headers

    @staticmethod
    @cache
    async def search(title: str) -> list[SearchObject]:
        params = {"keyword": title, "page": 1}
        html_page = await make_request("search", params, lambda r: r.text())
        html_page = re.sub(r"\s", " ", html_page)

        all_cards = _re(Patterns.CARD, html_page, all=True, default=[])
        return [card_scraper(card) for card in all_cards]

    @staticmethod
    @cache
    async def get_anime_info(id: str) -> AnimeInfo:
        html_page = await make_request(id, {}, lambda r: r.text())
        html_page = clean(html_page)

        anis_content = _re(Patterns.ANIS_CONTENT, html_page).group(1)
        anisc_detail = _re(Patterns.ANISC_DETAIL, anis_content).group(1)
        anisc_info_wrap = _re(Patterns.ANISC_INFO_WRAP, anis_content).group(1)

        dynamic_name = _re(Patterns.DYNAMIC_NAME2, anis_content).groupdict()

        sub_count = _re(Patterns.EPISODE_COUNT, anis_content, default=None)
        external_id = id
        title = dynamic_name["title"]
        other_title = dynamic_name["jtitle"]

        episode_count = int(sub_count.group(1)) if sub_count is not None else 0

        items = _re(Patterns.ITEM, anisc_detail, all=True)
        type = items[0]
        episode_duration = items[1]

        description = _re(Patterns.DESCRIPTION, anisc_info_wrap, default=None)
        description = description.group(1) if description is not None else ""
        description = description.replace("[Written by MAL Rewrite]", "").strip()

        genres = [m for m in _re(Patterns.GENRE, anisc_info_wrap, all=True)]

        year = 0
        airing_status: AiringStatus = "finished"

        item_titles = _re(Patterns.ITEM_TITLE, anisc_info_wrap, all=True)
        for item_title in item_titles:
            key = item_title[0].lower()
            value = item_title[1]

            if key == "aired":
                year = re.search(r"(\d{4})", value)
                assert year

                value = int(year.group(1))
                year = value

            elif key == "status" and value != "Finished Airing":
                airing_status = "airing"


        return AnimeInfo(
            external_id=external_id,
            mal_id=None,
            title=title,
            other_title=other_title,
            description=description,
            year=year,
            genres=genres,
            airing_status=airing_status,
            type=type,
            episode_count=episode_count,
            episode_duration=convert_ep_duration(episode_duration),
        )

    @staticmethod
    @cache
    async def get_episode_sources(anime_id: str, ep_num: int) -> EpisodeSources:
        episode_ids = await get_episode_ids(anime_id)
        ep_id = episode_ids[ep_num-1]

        resp = await make_request("ajax/v2/episode/servers", {"episodeId": ep_id}, lambda i: i.text())

        html_page: str = json.loads(resp)["html"]
        html_page = html_page.replace(r"\"", '"')
        html_page = clean(html_page)

        servers = _re(Patterns.SERVER, html_page, all=True)

        for s in servers:
            server_id = s[1]

            if server_id == Servers.VIDSTREAMING:
                source_id = s[0]
                break

        else:
            raise ValueError("source id not found")

        resp = await make_request("ajax/v2/episode/sources", {"id": source_id}, lambda i: i.text())
        video_url = json.loads(resp)["link"]

        e = Megacloud(video_url)
        return await e.extract()
