from typing import Awaitable, Callable
import re
import aiohttp

from .._types.structs import Extractor
from .._types.exceptions import InvalidURL


async def make_request[T](url: str, headers: dict, params: dict, func: Callable[[aiohttp.ClientResponse], Awaitable[T]]) -> T:
    async with aiohttp.ClientSession() as client:
        async with client.get(url, headers=headers, params=params) as resp:
            return await func(resp)


class Megaplay(Extractor):
    __base_url = "https://megaplay.buzz/stream"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0",
        "Origin": "https://megaplay.buzz",
        "Referer": "https://megaplay.buzz/",
    }

    def __init__(self, ep_id: str) -> None:
        self.ep_id = ep_id

    async def _get_server_id(self) -> str:
        url = f"{self.__base_url}/s-2/{self.ep_id}/sub"
        resp = await make_request(url, self.headers, {}, lambda i: i.text())

        pattern = r'data-id="(\d+)"'
        mtch = re.search(pattern, resp)

        if not mtch:
            raise InvalidURL(f"{url} doesn't contain data-id attrib")

        return mtch.group(1)

    async def extract(self) -> dict:
        id = await self._get_server_id()
        get_sources_url = f"{self.__base_url}/getSources"

        resp = await make_request(get_sources_url, self.headers, {"id": id}, lambda i: i.json())

        resp["sources"] = [resp["sources"]]
        resp["intro"] = resp["intro"]["start"], resp["intro"]["end"]
        resp["outro"] = resp["outro"]["start"], resp["outro"]["end"]

        return resp
