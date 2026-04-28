import zlib
import aiohttp
import re
import bs4
import base64
import os
import json
import inspect
import functools


def get_user_id() -> int:
    return os.getuid() if os.name == "posix" else os.getlogin()


type Serializable = str | int | list | dict

async def resolve_to_mal_id(title: str, other_title: str) -> str | None:
    async def req(url: str) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return await resp.text()

    search_url = f"https://myanimelist.net/anime.php?q={other_title}&cat=anime"
    search_resp = await req(search_url)
    soup = bs4.BeautifulSoup(search_resp, "html.parser")

    results = soup.select_one(".js-categories-seasonal.js-block-list.list")
    if not results:
        soup.decompose()
        return None

    for tr in results.find_all("tr"):
        a = tr.select_one(".hoverinfo_trigger.fw-b.fl-l")
        if a:
            title = a.text.strip().lower()
            title = unordinal(title)

            if title in (title.lower(), other_title.lower()):
                soup.decompose()
                return a.attrs["data-l-content-id"]

    soup.decompose()
    return None

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


def get_temp_dir() -> str:
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

def __make_key(args, kwargs):
    return (args, tuple(sorted(kwargs.items())))

def cache(func):
    __cache = {}

    if inspect.iscoroutinefunction(func):
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

def ordinal(s: str) -> str:
    def h(n):
        n = int(n)
        if 10 <= n % 100 <= 13:
            return f"{n}th"
        return f"{n}{['th','st','nd','rd','th','th','th','th','th','th'][n % 10]}"

    s = re.sub(r'([Ss])eason (\d+)', lambda m: f"{h(m.group(2))} {m.group(1)}eason", s)
    return s

def unordinal(s: str) -> str:
    return re.sub(r"(\d+)(?:th|st|nd|rd) ([Ss])eason", lambda m: f"{m.group(2)}eason {m.group(1)}", s)

