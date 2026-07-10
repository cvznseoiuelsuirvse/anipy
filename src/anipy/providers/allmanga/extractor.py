from Crypto.Cipher import AES
import hashlib
import time
import math
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

async def get_request_text(url: str, headers: dict | None = None):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            return await resp.text()

def derive_key(mask: str, xor_key: str) -> bytes:
    mask_b = bytes.fromhex(mask)
    xor_key_b = base64.b64decode(xor_key)

    key = b""
    
    for a, b in zip(xor_key_b, mask_b):
        val = a ^ b
        key += val.to_bytes(1)

    return key

def decode_url(s: str) -> str:
    chars = [HEX_TO_CHAR[b] for b in bytes.fromhex(s)]
    return ''.join(chars)

async def resolve_mp4(url: str) -> str:
    resp = await get_request_text(url)
    m = re.search(r"https:\/\/.+?mp4upload.com.*video\.mp4", resp)

    if not m:
        raise InvalidResponse("failed to resolve Mp4 source. video url not found")
    
    return m.group()
    
class AllAnime:
    headers = {
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0",
        "referer": "https://allanime.day/",
    }

    __frontend = "https://mkissa.to/"
    __crypto_key: bytes = b""
    
    @classmethod
    def _get_aa_crypto(cls, page: str) -> dict:
        pattern  = r'window\.__aaCrypto=({[^}]+})'
        m = re.search(pattern, page)
        if not m:
            raise InvalidFrontendPage("__aaCrypto object not found")

        return json.loads(m.group(1))

    @classmethod
    async def _get_aa_params(cls, page: str) -> tuple[str, str]:
        app_pattern    = r'(https://cdn\.allanime\.day/all/mk/_app/immutable/entry/app\.\w+\.js)'
        chunk_pattern  = r'(\.\./chunks/[\w-]+\.js)'
        params_pattern = r'([a-f0-9]{64}).+?\w{2}=.+\"(\d{2})\"'

        m = re.search(app_pattern, page)
        if not m:
            raise InvalidFrontendPage("app .js file not found")

        app_script_url = m.group(1)
        # print(f"{app_script_url=}")
        app_script = await get_request_text(app_script_url)

        m = re.search(chunk_pattern, app_script)
        if not m:
            raise InvalidScript("no chunks found")

        chunk_url = m.group(1).replace("..", "https://cdn.allanime.day/all/mk/_app/immutable/")
        # print(f"{chunk_url=}")
        chunk = await get_request_text(chunk_url)

        m = re.search(params_pattern, chunk)
        if not m:
            raise InvalidScript("no mask or build_id found")

        mask, build_id = m.groups()

        return mask, build_id

    @classmethod
    async def generate_aareq(cls) -> str:
        front_end_page = await get_request_text(cls.__frontend)

        aa_crypto = cls._get_aa_crypto(front_end_page)

        mask, build_id = await cls._get_aa_params(front_end_page)

        ts = math.floor((time.time() * 1000) / 300_000) * 300_000
        epoch = aa_crypto['epoch']

        query_hash =  "d405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec"

        json_blob = {
            "v": 1,
            "ts": ts,
            "epoch": epoch,
            "buildId": build_id,
            "qh": query_hash,
        }

        nonce_raw = f"{epoch}:{build_id}:{query_hash}:{ts}".encode()
        nonce = hashlib.sha256(nonce_raw).digest()[:12]

        cls.__crypto_key = derive_key(mask, aa_crypto['partB'])
        json_blob_string = json.dumps(json_blob, separators=(',',':'))

        aes = AES.new(cls.__crypto_key, AES.MODE_GCM, nonce=nonce)
        cipher, tag = aes.encrypt_and_digest(json_blob_string.encode())

        aaReq_bytes = b"\x01" + nonce + cipher + tag
        return base64.b64encode(aaReq_bytes).decode()


    @classmethod
    async def exctract(cls, data: dict) -> EpisodeSources:
        tobeparsed = data['data']['tobeparsed']

        raw = base64.b64decode(tobeparsed)
        raw = raw[1:]
        nonce = raw[:12]
        ciphertext = raw[12:-16]

        aes = AES.new(cls.__crypto_key, AES.MODE_GCM, nonce=nonce)
        plain = aes.decrypt(ciphertext)

        json_blob = plain.decode(encoding='utf-8')
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
                case "Yt-mp4":
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
