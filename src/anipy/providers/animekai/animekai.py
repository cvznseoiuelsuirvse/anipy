import parsel
import asyncio
import datetime
import aiohttp
from typing import Callable, Awaitable


from ...core.exceptions import SelectorNotFound, InvalidResponse, InvalidStatusCode
from ...core.util import cache
from ...core.types import SearchObject, AnimeInfo, EpisodeSources, AiringStatus

from .megaup import Megaup

BASE_URL = "https://animekai.to"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0",
}

async def make_request[T](route: str, *, params: dict | None = None, f: Callable[[aiohttp.ClientResponse], Awaitable[T]]) -> T:
    url = BASE_URL + route
    async with aiohttp.ClientSession() as client:
        async with client.get(url, headers=HEADERS, params=params) as resp:
            if resp.status != 200:
                raise InvalidStatusCode(resp.status, resp.url)

            try:
                return await f(resp)

            except Exception:
                raise InvalidResponse(resp.url)

def convert_ep_duration(s: str) -> int:
    s = s.lower()

    if "?" in s:
        return 0

    dt = datetime.datetime.strptime(s, "%M min")
    return dt.hour * 60 * 60000 + dt.minute * 60000

def card_scraper(card: str) -> SearchObject:
    selector = parsel.Selector(card)

    id = selector.css("a.poster::attr(href)").get()
    if not id:
        raise SelectorNotFound("a.poster::attr(href)")

    title = selector.css("a.title::text").get()
    if not title:
        raise SelectorNotFound("a.title::text")

    other_title = selector.css("a.title::attr(data-jp)").get("")

    info = selector.css("div.info")

    episode_count = int(info.css("span.sub::text").get() or 0)

    anime_type = info.css("span > b::text").getall()
    if not anime_type:
        raise SelectorNotFound("span > b")

    return SearchObject(
            id[7:],
            title,
            other_title,
            episode_count,
            0,
            anime_type[-1]
    )


class AnimeKai:
    extractor_headers: dict = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0",
            "Origin": "https://megaup.nl",
            "Referer": "https://megaup.nl/"
        }


    @staticmethod
    @cache
    async def search(title: str) -> list[SearchObject]:
        params = {
            "keyword": title,
            "sort": "most_relevance",
        }
        resp = await make_request("/browser", params=params, f=lambda r: r.text())
        selector = parsel.Selector(resp)
        cards = selector.css("div.aitem").getall()

        return [card_scraper(c) for c in cards]

    @staticmethod
    @cache
    async def get_anime(id: str) -> AnimeInfo:
        resp = await make_request(f"/watch/{id}", f=lambda r: r.text())
        selector = parsel.Selector(resp).css("div#watch-page")

        mal_id = selector.css("::attr(data-mal-id)").get()

        info = selector.css("div.entity-scroll")

        title = info.css("h1.title::text").get()
        if not title:
            raise SelectorNotFound("h1.title::text")

        other_title = info.css("h1.title::attr(data-jp)").get("")
        description = info.css("div.desc::text").get("")
        episode_count = int(info.css("span.sub::text").get() or 0)

        anime_type = info.css("span > b::text").getall()
        if not anime_type:
            raise SelectorNotFound("span > b")
        anime_type = anime_type[-1]

        details = info.css("div.detail").css("div").getall()

        genres = []
        year = 0
        duration = 0

        for div in parsel.Selector(details[0]).css("div"):
            k = div.css("::text").get("")
            k = k.strip().lower()[:-1]

            if not k: continue

            if k == "genres":
                for a in div.css("span > a"):
                    genres.append(a.css("::text").get("").lower())

            elif k == "premiered":
                v = div.css("span > a::text").get("")
                v = v.strip()
                year = int(v.split()[-1])

            elif k == "duration":
                v = div.css("span::text").get("")
                v = v.strip()

                duration = convert_ep_duration(v)


        status: AiringStatus = "finished"

        for div in parsel.Selector(details[1]).css("div"):
            k = div.css("::text").get("")
            k = k.strip().lower()[:-1]

            if not k: continue

            if k == "status":
                v = div.css("span::text").get("")
                v = v.strip()

                if v == "Releasing":
                    status = "airing"

        return AnimeInfo(
                id,
                mal_id,
                title,
                other_title,
                description,
                year,
                genres,
                status,
                anime_type,
                episode_count,
                duration,
        )


    @staticmethod
    async def get_episodes(anime_id: str, ep_num: int) -> EpisodeSources:
        return await Megaup.extract(f"{BASE_URL}/watch/{anime_id}", ep_num, "sub")


if __name__ == "__main__":
    async def main():
        # resp = await AnimeKai.search("rent a girl")
        # for r in resp:
        #     print(r)
        info = await AnimeKai.get_anime("kanojo-okarishimasu-ywy9")
        print(info)

        sources = await AnimeKai.get_episodes("kanojo-okarishimasu-ywy9", 1)
        print(sources)

    asyncio.run(main())
