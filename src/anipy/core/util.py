import zlib
import aiohttp
import bs4
import base64
import os
import json


def get_user_id() -> int:
    return os.getuid() if os.name == "posix" else os.getlogin()


type Serializable = str | int | list | dict


async def resolve_to_mal(title: str, other_title: str) -> str | None:
    async def req(url: str) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return await resp.text()

    search_url = f"https://myanimelist.net/anime.php?q={title}&cat=anime"
    search_resp = await req(search_url)
    soup = bs4.BeautifulSoup(search_resp, "html.parser")

    results = soup.select_one(".js-categories-seasonal.js-block-list.list")
    if not results:
        soup.decompose()
        return None

    for tr in results.find_all("tr"):
        a = tr.select_one(".hoverinfo_trigger.fw-b.fl-l")
        if a and a.text.strip() in (title, other_title):
            soup.decompose()
            return a.attrs["href"]

    soup.decompose()
    return None


def get_main_dir() -> str:
    temp_dir = "/tmp" if os.name == "posix" else os.getenv("TEMP")
    cache_path = os.path.join(temp_dir, f"anipy-{get_user_id()}")

    if not os.path.exists(cache_path):
        os.mkdir(cache_path)

    return cache_path


def compress_data(data: dict) -> str:
    data_string = json.dumps(data)
    data_compressed = zlib.compress(data_string.encode())
    return base64.b64encode(data_compressed).decode()


def decompress_data(data: str) -> dict:
    data_compressed = base64.b64decode(data)
    data_string = zlib.decompress(data_compressed).decode()
    return json.loads(data_string)
