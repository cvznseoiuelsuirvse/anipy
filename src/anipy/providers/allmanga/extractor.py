from typing import Awaitable, Callable

from Crypto.Cipher import AES
import hmac
import hashlib
import time
import base64
import json
import aiohttp
import re

from ...core.types import EpisodeSources
from ...core.exceptions import InvalidFrontendPage, InvalidScript, InvalidResponse

HEX_TO_CHAR = {
    0x79: "A", 0x7A: "B", 0x7B: "C", 0x7C: "D", 0x7D: "E", 0x7E: "F", 0x7F: "G",
    0x70: "H", 0x71: "I", 0x72: "J", 0x73: "K", 0x74: "L", 0x75: "M", 0x76: "N", 0x77: "O",
    0x68: "P", 0x69: "Q", 0x6A: "R", 0x6B: "S", 0x6C: "T", 0x6D: "U", 0x6E: "V", 0x6F: "W",
    0x60: "X", 0x61: "Y", 0x62: "Z",
    0x59: "a", 0x5A: "b", 0x5B: "c", 0x5C: "d", 0x5D: "e", 0x5E: "f", 0x5F: "g",
    0x50: "h", 0x51: "i", 0x52: "j", 0x53: "k", 0x54: "l", 0x55: "m", 0x56: "n", 0x57: "o",
    0x48: "p", 0x49: "q", 0x4A: "r", 0x4B: "s", 0x4C: "t", 0x4D: "u", 0x4E: "v", 0x4F: "w",
    0x40: "x", 0x41: "y", 0x42: "z",
    0x08: "0", 0x09: "1", 0x0A: "2", 0x0B: "3", 0x0C: "4", 0x0D: "5", 0x0E: "6", 0x0F: "7",
    0x00: "8", 0x01: "9",
    0x15: "-", 0x16: ".", 0x67: "_", 0x46: "~", 0x02: ":", 0x17: "/", 0x07: "?", 0x1B: "#",
    0x63: "[", 0x65: "]", 0x78: "@", 0x19: "!", 0x1C: "$", 0x1E: "&", 0x10: "(", 0x11: ")",
    0x12: "*", 0x13: "+", 0x14: ",", 0x03: ";", 0x05: "=", 0x1D: "%"
}

return_text = lambda r: r.text()
return_json = lambda r: r.json()

async def request_get[T](
        url: str, *, headers: dict | None = None, params: dict | None = None,
        func: Callable[[aiohttp.ClientResponse], Awaitable[T]]) -> T:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as resp:
            return await func(resp)
            
def parse_int(v: str) -> int | None:
    m = re.search(r"^(\d+)[a-zA-z]+$", v)
    if not m:
        return m
    return int(m.group(1))

def decode_url(s: str) -> str:
    chars = [HEX_TO_CHAR[b] for b in bytes.fromhex(s)]
    return ''.join(chars)

async def resolve_mp4(url: str) -> str:
    resp = await request_get(url, func=return_text)
    m = re.search(r"https:\/\/.+?mp4upload.com.*video\.mp4", resp)

    if not m:
        raise InvalidResponse("failed to resolve Mp4 source. video url not found")
    
    return m.group()

def current_epoch() -> int:
    now = int(time.time())

    EPOCH = 259200
    GRACE = 86400

    epoch = now // EPOCH
    return epoch - (epoch > 0 and now % EPOCH < GRACE)


class AllAnimeCrypto:
    __cdn = "https://cdn.mkissa.net"
    __frontend = "https://youtu-chan.com"

    @staticmethod
    def sign(msg: str, key: bytes) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    @staticmethod
    def derive_key(mask: bytes, xor_key: str) -> bytes:
        xor_key_b = base64.b64decode(xor_key)
        key = b""
        for a, b in zip(xor_key_b, mask):
            val = a ^ b
            key += val.to_bytes(1)
        return key

    @staticmethod
    def _get_build_id_mask(build_id: str) -> bytes:
        ret = b""
        for i in range(32):
            ch = build_id[i % len(build_id)]
            mask = 255 & (i * 17 + 31)
            ret += int.to_bytes(ord(ch) ^ mask)
        return ret


    @staticmethod
    def derive_nonce(*args) -> bytes:
        encoded = ":".join(map(str, args)).encode()
        return hashlib.sha256(encoded).digest()[:12]

    @staticmethod
    def _get_sign_key_mask(script: str) -> bytes:
        p_array_item = r'(?:"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')'
        p_array = r'function (\w{2})\(\){const\s+\w+=\[((?=[^\]]*"__prot")[^\]]*)\]'

        m = re.search(p_array, script)
        if not m:
            raise InvalidScript("array not found")

        array_func = m.group(1)
        all_items = list(map(lambda s: s.strip("'").strip('"'), re.findall(p_array_item, m.group(2))))

        p_shuffle_func = r"}\(function\(\w,\w\){([\w\s=\(\);,{}\-\+\.*\/]+)\)\(" + array_func + r",([\d\+\-\*\/ ]+)\)"
        m = re.search(p_shuffle_func, script)
        if not m:
            raise InvalidScript("array shuffle function not found")

        shuffle_func = m.group(1)

        sub_index_funcs: dict[str, Callable[[int], int]] = {}
        index_funcs: dict[str, Callable[[int], int]] = {}

        local_funcs = re.findall(r"function (\w)\(\w,\w\){return (\w{2})\(\w-([\d\- ]+)\)}", shuffle_func)
        if not local_funcs:
            raise InvalidScript("no local index functions found")

        for local_name, global_name, local_value in local_funcs:
            p_global = r"function " + global_name + r"\(\w,\w\){return \w=\w-([\(\)\d\-+*\/]+)," + array_func + r"\(\)"
            m = re.search(p_global, script)
            if not m:
                raise InvalidScript(f"global index function {global_name} not found")

            gv = eval(m.group(1))
            lv = eval(local_value)
            index_funcs[global_name] = lambda v, _gv=gv: v - _gv
            sub_index_funcs[local_name] = lambda v, _lv=lv, _gn=global_name: index_funcs[_gn](v - _lv)

        indexes = [
            sub_index_funcs[fn](int(val))
            for fn, val in re.findall(r"parseInt\((\w)\([-\d]+,([-\d]+)", shuffle_func)
        ]

        while None in [parse_int(all_items[i]) for i in indexes]:
            all_items.append(all_items.pop(0))

        m = re.search(r"\w{2}=\[(\w{2}\([^\]]+)", script)
        if not m:
            raise InvalidScript("mask array not found")

        mask_indexes = []
        for local_name, value in re.findall(r"([a-zA-Z]{2}).+?([\d-]+)\)", m.group(1)):
            p_sub = r"function " + local_name + r"\(\w,\w\){return (\w{2})\(\w-([\d\- ]+)\)}"
            m_ = re.search(p_sub, script)
            if not m_:
                raise InvalidScript(f"no {local_name} sub index function found")

            global_name = m_.group(1)
            if global_name not in index_funcs:
                raise InvalidScript(f"unknown global index function {global_name}")

            mask_indexes.append(index_funcs[global_name](int(value) - int(m_.group(2))))

        mask = b""
        for i in range(0, len(mask_indexes), 2):
            p1 = all_items[mask_indexes[i]]
            p2 = all_items[mask_indexes[i+1]]
            mask += base64.b64decode(p1 + p2)

        return mask

    @classmethod
    async def _process_chunk(cls, chunk_url: str) -> tuple[str, str, bytes]:
        chunk = await request_get(chunk_url, func=return_text)

        build_id_pattern = r'"(\d+)":""'
        m = re.search(build_id_pattern, chunk)
        if not m:
            raise InvalidScript(f"build_id not found (chunk url: {chunk_url})")

        build_id = m.group(1)
        sign_key_mask = cls._get_sign_key_mask(chunk)

        return "k7", build_id, sign_key_mask

    @classmethod
    async def get_aa_params(cls) -> tuple[str, str, bytes]:
        headers = {
            "Origin": f"https://mkissa.to", 
            "Referer": f"https://mkissa.to/"
        }

        front_end = await request_get(
            cls.__frontend, 
            headers=headers,
            func=return_text
        )

        app_pattern    = rf'({cls.__cdn}/all/mk/_app/immutable/entry/app\.[\w-]+\.js)'
        chunk_pattern  = r'(\.\./chunks/[\w-]+\.js)'

        m = re.search(app_pattern, front_end)
        if not m:
            raise InvalidFrontendPage("app .js file not found")

        app_script_url = m.group(1)
        app_script = await request_get(app_script_url, func=return_text)

        m = re.findall(chunk_pattern, app_script)
        if not m:
            raise InvalidScript(f"no chunks found. (script url: {app_script_url})")

        chunk_url = m[0].replace("..", f"{cls.__cdn}/all/mk/_app/immutable/")
        return await cls._process_chunk(chunk_url)

    @classmethod
    def get_sign_key(cls, build_id: str, mask: bytes) -> bytes:
        build_id_mask = cls._get_build_id_mask(build_id)
        sign_key = b""
        for i, (b1, b2) in enumerate(zip(build_id_mask, mask)):
            v1 = b1 ^ b2
            v2 = 255 & ((i // 8) * 41 + (i % 8) * 7)
            sign_key += int.to_bytes(v1 ^ v2)
        return sign_key

    @classmethod
    async def get_aa_crypto(cls, sign_key: bytes, build_id: str, epoch: int, content_lane: str, host: str) -> dict:
        if host == "mkissa.to":
            domain = "mkissa"
        else:
            domain = "mirror"

        aa_boot_key = cls.sign(f'aa-boot:{build_id}', sign_key)
        print(f"{list(aa_boot_key)=}")

        aa_boot = cls.sign(f'{build_id}:{domain}:{host}:{epoch}:{content_lane}', aa_boot_key)
        print(f"{list(aa_boot)=}")

        url = "https://api.mkissa.net/client-crypto/v1/bootstrap"
        headers = {
            "Origin": f"https://{host}",
            "Referer": f"https://{host}/",
            "x-aa-boot": aa_boot.hex(),
            "x-build-id": build_id,
        }

        params = {
            "buildId": build_id,
            "k": content_lane,
        }

        resp = await request_get(url, headers=headers, params=params, func=return_json)
        return resp



class AllAnime:
    headers = {
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0",
        "referer": "https://allanime.day/",
    }
    __crypto_key: bytes = b""
    
    @classmethod
    async def generate_aareq(cls, qh: str, host: str) -> dict:
        epoch = current_epoch()
        print(f"{epoch=}")

        content_lane, build_id, sign_key_mask = await AllAnimeCrypto.get_aa_params()
        print(f"{content_lane=} {build_id=} {list(sign_key_mask)=}")

        sign_key = AllAnimeCrypto.get_sign_key(build_id, sign_key_mask)
        print(f"{list(sign_key)=}")

        aa_crypto = await AllAnimeCrypto.get_aa_crypto(sign_key, build_id, epoch, content_lane, host)
        print(f"{aa_crypto=}")

        ts = int(time.time() * 1000) // 300_000 * 300_000
        json_blob = {
            "v": 1,
            "ts": ts,
            "epoch": epoch,
            "buildId": build_id,
            "qh": qh,
            "k": content_lane,
        }

        nonce = AllAnimeCrypto.derive_nonce(epoch, build_id, qh, ts, content_lane)
        cls.__crypto_key = AllAnimeCrypto.derive_key(sign_key, aa_crypto['partB'])
        json_blob_string = json.dumps(json_blob, separators=(',',':'))

        aes = AES.new(cls.__crypto_key, AES.MODE_GCM, nonce=nonce)
        cipher, tag = aes.encrypt_and_digest(json_blob_string.encode())

        aaReq_bytes = b"\x01" + nonce + cipher + tag

        return {"aa_req": base64.b64encode(aaReq_bytes).decode(), "build_id": build_id}


    @classmethod
    async def exctract(cls, data: dict) -> EpisodeSources:
        tobeparsed = data['data']['tobeparsed']

        raw = base64.b64decode(tobeparsed)
        raw = raw[1:]
        nonce = raw[:12]
        ciphertext = raw[12:-16]

        aes = AES.new(cls.__crypto_key, AES.MODE_GCM, nonce=nonce)
        plain = aes.decrypt(ciphertext)

        try:
            json_blob = plain.decode(encoding='utf-8')

        except UnicodeDecodeError:
            if cls.__crypto_key.startswith(b"\xa2\x54\xaa\x27"):
                raise 

            cls.__crypto_key = hashlib.sha256(b"Xot36i3lK3:v1").digest()
            return await cls.exctract(data)

        json_data = json.loads(json_blob)

        episode = json_data['episode']
        source_urls = episode['sourceUrls']

        if not source_urls:
            raise InvalidResponse("'sourceUrls' is empty")

        source_urls = sorted(source_urls, key=lambda d: d['priority'], reverse=True)

        for src in source_urls:
            url = src['sourceUrl']
            name = src['sourceName']

            match name:
                case "Yt-mp4" | "S-mp4":
                    if url.startswith("--"):
                        url = decode_url(url.lstrip('-'))

                case "Mp4":
                    url = await resolve_mp4(url)
                    cls.headers['referer'] = "https://www.mp4upload.com/"
                     
                case _:
                    continue

            return EpisodeSources(
                source=url,
                tracks=[],
                intro=(0, 0),
                outro=(0, 0),
            )

        raise InvalidResponse('source not found')
