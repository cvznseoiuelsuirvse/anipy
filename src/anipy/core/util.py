import zlib
import aiohttp
import difflib
import re
import parsel
import base64
import os
import json
import inspect
import functools


def get_user_id() -> str:
    return str(os.getuid()) if os.name == "posix" else os.getlogin()


type Serializable = str | int | list | dict

async def resolve_to_mal(title: str, other_title: str, *, return_id: bool = False) -> str | None:
    search_url = f"https://myanimelist.net/anime.php?q={title}&cat=anime"

    async with aiohttp.ClientSession() as session:
        async with session.get(search_url) as resp:
            search_resp = await resp.text()

    selector = parsel.Selector(search_resp)

    for i, tr in enumerate(selector.css("tr")):
        if i == 0:
            continue

        a = tr.css("div.title > a")
        if not a: continue

        anime_title = a.xpath("normalize-space()").get("")
        anime_title = unordinal(anime_title)

        anime_href = a.attrib["href"]
        anime_id = a.attrib["data-l-content-id"]

        if anime_title.lower() in (title.lower(), other_title.lower()):
            return anime_id if return_id else anime_href

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

def _make_key(args, kwargs):
    return (args, tuple(sorted(kwargs.items())))

def cache(func):
    __cache = {}

    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            key = _make_key(args, kwargs)
            if key in __cache:
                return __cache[key]

            value = await func(*args, **kwargs)
            __cache[key] = value

            return value

        return async_wrapper

    else:

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            key = _make_key(args, kwargs)

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

def is_similar(a: str, b: str, threshold: float = 0.8) -> bool:
    sm = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return sm >= threshold
