import json
import random
import re
import urllib.parse
import aiohttp
import base64
from typing import Callable, Literal, Awaitable

from ...core.types import EpisodeSources
from ...core.exceptions import InvalidStatusCode, InvalidResponse

class SyncDataNotFound(Exception): pass
class EpisodeTokensNotFound(Exception): pass
class EpisodeNotFound(Exception): pass

from .t import IFRAME_ROUNDS, SOURCES_ROUNDS, TransformConfig, PARAMS_ROUNDS

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0"

to_text = lambda r: r.text()
to_json = lambda r: r.json()

async def request[T](
        url: str, 
        *,
        headers: dict | None = None, 
        params: dict | None = None, 
        cookies: dict | None = None,
        f: Callable[[aiohttp.ClientResponse], Awaitable[T]]
) -> T:
    async with aiohttp.ClientSession(cookies=cookies) as session:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status != 200:
                raise InvalidStatusCode(resp.status, resp.url)

            try:
                data = await f(resp)

            except Exception as e:
                raise InvalidResponse(resp.url, e)

            return data


def to_base(n, base):
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = []

    if n == 0:
        return "0"

    if not (2 <= base <= len(digits)):
        raise ValueError("base must be between 2 and 36")

    sign = "-" if n < 0 else ""
    n = abs(n)
    while n:
        n, rem = divmod(n, base)
        out.append(digits[rem])

    return sign + "".join(reversed(out))

def transform(
        data: bytes, 
        key: bytes, 
        cfg: TransformConfig, 
        *, 
        extra_key: str | None = None, 
        pre_xor: bool = False) -> bytes:
    
    out = []
    idx = 0

    use_idx = not pre_xor

    for i in range(len(data)):
        if i < cfg.skip:
            if use_idx:
                idx += 1

            if extra_key:
                out.append(extra_key[i])

        if use_idx and idx >= len(data): 
            break

        k = data[idx]
        idx += 1

        if pre_xor:
            k ^= key[i % 32]

        k = cfg.ops[i % 10](k) & 0xFF

        if not pre_xor:
            k ^= key[i % 32]

        out.append(k & 0xFF)

    return bytes(out)

def rc4(key: bytes, data: bytes) -> bytes:
    s = list(range(256))
    j = 0

    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) % 256
        s[j], s[i] = s[i], s[j]

    i = 0
    j = 0

    out = []
    
    for b in data:
        i = (i + 1) % 256
        j = (j + s[i]) % 256

        s[j], s[i] = s[i], s[j]

        t = (s[i] + s[j]) % 256
        out.append(b ^ s[t])

    return bytes(out)


def apply_rounds(data: bytes, rounds: list, key_transform: Callable[[bytes], bytes] | None = None) -> bytes:
    if key_transform is None:
        key_transform = lambda k: k

    for r in rounds:
        if len(r) == 3:
            rc_key, t_key, cfg = r
            data = transform(data, key_transform(t_key), cfg) 
            data = rc4(rc_key, data)

        else:
            rc_key, t_key, t_extra_key, cfg = r
            data = rc4(rc_key, data)
            data = transform(data, key_transform(t_key), cfg, extra_key=t_extra_key, pre_xor=True) 

    return data

def encrypt_param(s: str) -> str:
    data = apply_rounds(s.encode(), PARAMS_ROUNDS)
    return base64.urlsafe_b64encode(data).decode()


class Megaup:
    @staticmethod
    async def get_iframe(url: str, ep: int, ver: str) -> str:
        resp = await request(url, f=to_text)
        m = re.search(r'({"page".+?})', resp)
        if not m:
            raise SyncDataNotFound

        sync_data = json.loads(m.group(1))

        list_episodes_url = "https://animekai.to/ajax/episodes/list"
        list_episodes_params = {
            "ani_id": sync_data['anime_id'],
            "_": encrypt_param(sync_data['anime_id'])
        }

        resp = await request(list_episodes_url, params=list_episodes_params, f=to_json)
        result = resp['result']

        tokens = re.findall(r'token="([\w-]+)"', result)
        if not tokens:
            raise EpisodeTokensNotFound

        assert(ep <= len(tokens))

        token = tokens[ep-1]

        list_links_url = "https://animekai.to/ajax/links/list"
        list_links_params = {
            "token": token,
            "_": encrypt_param(token),
        }

        resp = await request(list_links_url, params=list_links_params, f=to_json)
        result = resp['result']

        m = re.search(rf'data-id="{ver}" style="display: (?:none)?;">.+?data-lid="([\w-]+)"', result)
        if not m:
            raise EpisodeNotFound(ver)

        data_lid = m.group(1)

        links_view_url = "https://animekai.to/ajax/links/view"
        links_view_params = {
            "id": data_lid,
            "_": encrypt_param(data_lid)
        }

        resp = await request(links_view_url, params=links_view_params, f=to_json)
        return resp['result']

    @staticmethod
    def decrypt_iframe(cipher: str) -> dict:
        data = apply_rounds(base64.urlsafe_b64decode(cipher + "=="), IFRAME_ROUNDS)
        res = data.decode("latin-1")
        return json.loads(urllib.parse.unquote(res))

    @staticmethod
    async def decrypt_sources(iframe: str) -> dict:
        resp = await request(iframe, f=to_text)
        
        m = re.search(r'iframe src="(https:\/\/megaup.n.\/e\/[\w-]+)\?"', resp)
        if not m:
            raise ValueError("embedded url not found")
        
        embedded_url = m.group(1)
        embedded_url = embedded_url.replace("/e/", "/media/")

        cookie_key = to_base(sum(ord(c) for c in USER_AGENT), 23)
        cookie_val = to_base(random.randint(0, 90000), 23)
        
        cookies = {cookie_key: cookie_val}
        headers = {"User-Agent": USER_AGENT, "Referer": embedded_url}

        resp = await request(
            embedded_url, 
            cookies=cookies, 
            headers=headers, 
            params={"autostart": "true"}, 
            f=to_json
        )

        user_agent_key = re.sub(r"[^A-Z0-9]", "", USER_AGENT)[-30:]

        def t_key_apply_transform(key: bytes) -> bytes:
            out = list(map(int, key))

            i = 0
            while i < len(key):
                out[i] = ord(user_agent_key[i % len(user_agent_key)])
                i += 4

            i = 0
            while i < len(key):
                out[i] = ord(cookie_val[i % len(cookie_val)])
                i += 6

            return bytes(out)


        sources = resp['result']
        data = apply_rounds(base64.urlsafe_b64decode(sources + "=="), SOURCES_ROUNDS, t_key_apply_transform)
        res = data.decode("latin-1")
        return json.loads(urllib.parse.unquote(res))


    @classmethod
    async def extract(cls, url: str, ep: int, ver: Literal['sub', 'softsub', 'dub']) -> EpisodeSources:
        iframe = await cls.get_iframe(url, ep, ver)
        embedded = cls.decrypt_iframe(iframe)

        intro = embedded['skip']['intro'][0], embedded['skip']['intro'][1]
        outro = embedded['skip']['outro'][0], embedded['skip']['outro'][1]

        sources = await cls.decrypt_sources(embedded['url'])

        return EpisodeSources(
                    sources['sources'][0]['file'],
                    sources['tracks'],
                    intro,
                    outro
                )
