import asyncio
import base64
import hashlib
import json
import re

from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import unpad
import aiohttp

from ..exceptions import InvalidURL, BadResponse
from .._types import Extractor


def key_rename(old_name: str, new_name: str, old_dict: dict) -> dict:
    oldKeyIndex = list(old_dict.keys()).index(old_name)

    new_dict = list(old_dict.items())
    new_dict[oldKeyIndex] = (new_name, old_dict.get(old_name))

    return dict(new_dict)


class Megacloud(Extractor):
    __srcipt_url = "https://megacloud.tv/js/player/a/e1-player.min.js"
    __get_sources = "https://megacloud.tv/embed-2/ajax/e-1/getSources"

    def __init__(self, video_url: str) -> None:
        self.__vid_url = video_url

    def _is_hex(self, s):
        try:
            int(s, 16)
            return True

        except ValueError:
            return False

    async def _make_request(self, url: str, params: dict, response_func):
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"}
        async with aiohttp.ClientSession() as client:
            async with client.get(url, params=params, headers=headers) as response:
                return await response_func(response)

    def _find_value(self, key: str, script: str) -> str:
        value = re.search(rf",{key}=((?:0x)?([0-9a-fA-F]+))", script)

        if not value:
            raise KeyError(f"value for {key} not found")

        return value.group(2)

    def _get_keys(self, script: str) -> list[tuple[int, int]]:
        allvars = re.findall(r"case\s*0x[0-9a-f]+:(?![^;]*=partKey)\s*\w+\s*=\s*(\w+)\s*,\s*\w+\s*=\s*(\w+);", script)
        keys = []

        if not allvars:
            raise ValueError("unable to match regex with the script")

        for var_pair in allvars:
            k1, k2 = var_pair
            v1, v2 = self._find_value(k1, script), self._find_value(k2, script)

            keys.append((int(v1, 16), int(v2, 16)))

        return keys

    def _get_secret(self, encrypted_src: str, values: list[tuple[int, int]]) -> tuple[str, str]:
        """
        :param encrypted source url
        :param list with pairs of extracted variables

        :return secret and modified encrypted_src
        """
        encrypted_src_arr = list(encrypted_src)

        secret = ""
        offset = 0

        for value_pair in values:
            start = value_pair[0] + offset
            end = start + value_pair[1]

            for i in range(start, end):
                secret += encrypted_src[i]
                encrypted_src_arr[i] = ""

            offset += value_pair[1]

        return secret, "".join(encrypted_src_arr)

    def _decrypt(self, key: str, enc_src: str) -> str:
        cypher = base64.b64decode(enc_src)
        salt = cypher[8:16]
        password = key.encode("latin1") + salt

        hashes = []
        digest = password

        for _ in range(3):
            hash = hashlib.md5(digest).digest()
            hashes.append(hash)
            digest = hash + password

        secret_key = hashes[0] + hashes[1]
        iv = hashes[2]
        contents = cypher[16:]

        aes = AES.new(secret_key, AES.MODE_CBC, iv=iv)
        decrypted = aes.decrypt(contents)

        return unpad(decrypted, AES.block_size).decode()

    async def extract(self) -> dict:
        if not (match := re.search(r"/e-1/(?P<id>[^/?]+)", self.__vid_url)):
            raise InvalidURL(f"{self.__vid_url} doesn't contain id")

        vid_id = match.group("id")

        script_params = {"v": "0.1.0"}
        embed_params = {"id": vid_id}

        tasks = [
            self._make_request(self.__srcipt_url, script_params, lambda r: r.text()),
            self._make_request(self.__get_sources, embed_params, lambda r: r.json()),
        ]
        responses = await asyncio.gather(*tasks)

        script = responses[0]
        episode = responses[1]

        sources = episode["sources"]

        if not sources:
            keys = self._get_keys(script)
            secret, new_source = self._get_secret(sources, keys)

            raise BadResponse("no sources found")

        if isinstance(sources, str):
            keys = self._get_keys(script)
            secret, new_source = self._get_secret(sources, keys)

            sources = json.loads(self._decrypt(secret, new_source))

        return {
            "sources": sources,
            "subtitles": episode["tracks"],
            "intro": episode["intro"],
            "outro": episode["outro"],
        }
