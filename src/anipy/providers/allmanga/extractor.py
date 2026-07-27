import asyncio
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

def sign(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()

def derive_key(mask: bytes, xor_key: str) -> bytes:
    xor_key_b = base64.b64decode(xor_key)

    key = b""
    
    for a, b in zip(xor_key_b, mask):
        val = a ^ b
        key += val.to_bytes(1)

    return key

def get_build_id_mask(build_id: str) -> bytes:
    ret = b""
    for i in range(32):
        ch = build_id[i % len(build_id)]
        mask = 255 & (i * 17 + 31)
        ret += int.to_bytes(ord(ch) ^ mask)

    return ret

def get_sign_key(build_id: str) -> bytes:
    build_id_mask = get_build_id_mask(build_id)

    # hopefully it stays the same
    hmac_mask = b'\xd7\x47\x75\xdf\xfd\xb5\xde\x12\x5d\xd4\xc0\xe8\x56\x80\x41\x2a\x29\x10\x94\x4f\xd9\x59\x87\x5a\x02\x3d\xc0\x48\x22\x03\x32\x7c'

    sign_key = b""
    for i, (b, h) in enumerate(zip(build_id_mask, hmac_mask)):
        v1 = b ^ h
        v2 = 255 & ((i // 8) * 41 + (i % 8) * 7)
        sign_key += int.to_bytes(v1 ^ v2)


    return sign_key

def derive_nonce(*args) -> bytes:
    encoded = ":".join(map(str, args)).encode()
    return hashlib.sha256(encoded).digest()[:12]


def decode_url(s: str) -> str:
    chars = [HEX_TO_CHAR[b] for b in bytes.fromhex(s)]
    return ''.join(chars)

async def resolve_mp4(url: str) -> str:
    resp = await request_get(url, func=return_text)
    m = re.search(r"https:\/\/.+?mp4upload.com.*video\.mp4", resp)

    if not m:
        raise InvalidResponse("failed to resolve Mp4 source. video url not found")
    
    return m.group()
    
class AllAnime:
    headers = {
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0",
        "referer": "https://allanime.day/",
    }

    __frontend = "https://youtu-chan.com"
    __cdn = "https://cdn.mkissa.net"

    __crypto_key: bytes = b""
    
    @classmethod
    async def _get_aa_crypto(cls, sign_key: bytes, build_id: str, epoch: int, content_lane: str, host: str) -> dict:
        pre_aa_boot = sign(sign_key, f'aa-boot:{build_id}'.encode())

        if host == "mkissa.to":
            domain = "mkissa"
        else:
            domain = "mirror"

        aa_boot = sign(pre_aa_boot, f'{build_id}:{domain}:{host}:{epoch}:{content_lane}'.encode())

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

    @classmethod
    async def _get_aa_params(cls, page: str) -> tuple[str, str]:
        app_pattern    = rf'({cls.__cdn}/all/mk/_app/immutable/entry/app\.[\w-]+\.js)'
        chunk_pattern  = r'(\.\./chunks/[\w-]+\.js)'
        params_pattern = r'"(\d+)":""'

        m = re.search(app_pattern, page)
        if not m:
            raise InvalidFrontendPage("app .js file not found")

        app_script_url = m.group(1)
        app_script = await request_get(app_script_url, func=return_text)

        m = re.findall(chunk_pattern, app_script)
        if not m:
            raise InvalidScript("no chunks found")

        chunk_urls = [chunk.replace("..", f"{cls.__cdn}/all/mk/_app/immutable/") for chunk in m[:2]]
        tasks = [request_get(u, func=return_text) for u in chunk_urls]
        done = await asyncio.gather(*tasks)

        for text in done:
            m = re.search(params_pattern, text)
            if m: 
                break
        else:
            raise InvalidScript("no build_id found")

        build_id = m.group(1)
        return "k7", build_id

    @classmethod
    async def generate_aareq(cls, qh: str, host: str) -> dict:
        headers = {
            "Origin": f"https://mkissa.to", 
            "Referer": f"https://mkissa.to/"
        }

        front_end_page = await request_get(
            cls.__frontend, 
            headers=headers,
            func=return_text
        )

        epoch = int(time.time()) // 259200 - 1
        content_lane, build_id = await cls._get_aa_params(front_end_page)

        sign_key = get_sign_key(build_id)
        aa_crypto = await cls._get_aa_crypto(sign_key, build_id, epoch, content_lane, host)

        ts = int(time.time() * 1000) // 300_000 * 300_000
        json_blob = {
            "v": 1,
            "ts": ts,
            "epoch": epoch,
            "buildId": build_id,
            "qh": qh,
            "k": content_lane,
        }

        nonce = derive_nonce(epoch, build_id, qh, ts, content_lane)
        cls.__crypto_key = derive_key(sign_key, aa_crypto['partB'])
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
