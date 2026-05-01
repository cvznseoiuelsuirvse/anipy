from Crypto.Cipher import AES
import hashlib
import base64
import json

from ...core.types import EpisodeSources
from ...core.exceptions import InvalidResponse


KEY = hashlib.sha256(b"Xot36i3lK3:v1").digest()
hex_to_char = {
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

def decode_url(s: str) -> str:
    chars = [hex_to_char[b] for b in bytes.fromhex(s)]
    return ''.join(chars)

class AllAnime:
    headers = {
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0",
        "referer": "https://allanime.day/",
    }

    @staticmethod
    def exctract(data: dict) -> EpisodeSources:
        tobeparsed = data['data']['tobeparsed']
        # tobeparsed = data

        raw = base64.b64decode(tobeparsed)
        raw = raw[1:]
        nonce = raw[:12]
        ciphertext = raw[12:-16]

        aes = AES.new(KEY, AES.MODE_GCM, nonce=nonce)
        plain = aes.decrypt(ciphertext)

        json_blob = plain.decode(encoding='utf-8')
        json_data = json.loads(json_blob)

        episode = json_data['episode']
        for src in episode['sourceUrls']:
            if src['sourceName'] == 'Yt-mp4':
                url = decode_url(src['sourceUrl'].lstrip('-'))

                return EpisodeSources(
                    source=url,
                    tracks=[],
                    intro=(0, 0),
                    outro=(0, 0),
                )


        raise InvalidResponse('Yt-mp4 source not found')
