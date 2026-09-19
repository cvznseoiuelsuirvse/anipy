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
 
CONTENT_LANE = "k7"

RE_INDEX           = r"-?(?:[\d ]+|(\w)\._(0x[a-f0-9]{1,6}))"
RE_INDEX_FUNC_BODY = r"\((\w),\w\){return ([\w$]{2})\((\w)- ?(" + RE_INDEX + r")\)}"
RE_INDEX_FUNC_BODY2 = r"\((\w),\w\){return ([\w$]{2})\((\w)- ?((?:-?(?:[\d ]+|(\w)\._(0x[a-f0-9]{1,6}))|{_0x[a-f0-9]{1,6}:(\d+)}\._0x[a-f0-9]{1,6}))\)}"

RE_PARSE_INT              = r"^(\d+)[a-zA-z]+$"
RE_GLOBAL_INDEX_FUNC_CALL = r"([\w\$]{2})\((?:[\de\-]+,)?([\de\-]+)\)"
RE_ARRAY_BODY             = r"([\w\$]{2}\([^\]]+)"
RE_NUM_MAP_ENTRY          = r"_(0x[a-f0-9]{1,6}):(\d+)"
RE_NUM_MAP                = r"(\w)={((?:" + RE_NUM_MAP_ENTRY + r",?)+)}"

RE_QUOTED_STRING          = r'(?:"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')'
RE_ARRAY_FUNC             = r'function (\w{2})\(\){const\s+\w+=\[((?=[^\]]*"epo")[^\]]*)\]'
RE_LOCAL_INDEX_FUNC       = r"function (\w)" + RE_INDEX_FUNC_BODY
RE_SHUFFLE_CHECK          = r"parseInt\((\w)\((" + RE_INDEX + "),(" + RE_INDEX + ")"
RE_MASK_ARRAY             = r"\w{2}=\[((?:(?:" + RE_GLOBAL_INDEX_FUNC_CALL + r"\+?){4},?){4})"
RE_BUILD_ID               = r"const [\w$]{2}=" + RE_GLOBAL_INDEX_FUNC_CALL + r",[\w$]{2}"
RE_CHUNK_URL              = r"(\.\./chunks/[\w-]+\.js)"
RE_BOOT_CFG               = r'\{v:\d+,saltMul:(\d+),saltAdd:(\d+),fragMul:(\d+),fragAdd:(\d+),bootPrefix:((?:([\w\$]{2})\((?:[\de\-]+,)?([\de\-]+)\)\+?)+(?:"[\w:]+")?),join:"([^"]+)",parts:\[([\w\$]{2}\([^\]]+)\],omitEmptyLane:([^,]+),envXor:(\d+)'

RE_SHUFFLE_FUNC_PREFIX    = r"}\(function\(\w,\w\){([\w\s={:,};\(\)-\.\/!$]+)"
RE_SHUFFLE_FUNC_SUFFIX    = r",([\d\+\-\*\/ ]+)\)"
RE_GLOBAL_FUNC_INFIX      = r"\(\w,\w\){return \w=\w-([\(\)\d\-+*\/]+),"
RE_GLOBAL_FUNC_SUFFIX     = r"\(\)"
RE_SUB_INDEX_FUNC_PREFIX  = r"function "

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

def _make_global_index_func(offset: int) -> Callable[[int], int]:
    return lambda v: v - offset

def _make_sub_index_func(local_offset: int, arg_index: int, global_func: Callable[[int], int]) -> Callable[[tuple], int]:
    return lambda pair: global_func(pair[arg_index] - local_offset)

async def request_get[T](
    url: str, *, headers: dict | None = None, resp_headers: dict | None = None, params: dict | None = None,
        func: Callable[[aiohttp.ClientResponse], Awaitable[T]]) -> T:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp_headers is not None:
                resp_headers |= resp.headers
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

    EPOCH = 604800
    GRACE = 86400

    epoch = now // EPOCH
    return epoch - (epoch > 0 and now % EPOCH < GRACE)


class AllAnimeCryptoConfig:
    lane:        str
    epoch:       int
    build_id:    str
    mask:        bytes
    salt:        tuple[int, int]
    frag:        tuple[int, int]
    boot_prefix: str
    join:        str
    parts:       list[str]

    def __str__(self) -> str:
        s = f"""
lane={self.lane}  epoch={self.epoch} build_id={self.build_id}
salt={self.salt}  frag={self.frag}
boot_prefix={self.boot_prefix}  join={self.join}  parts={self.parts}
mask={list(self.mask)}
        """

        return s.strip()

class AllAnimeCrypto:
    __cdn = "https://cdn.mkissa.net"
    __frontend = "https://youtu-chan.com"
    __cache = ""

    def __init__(self) -> None:
        self.__global_index: dict[str, Callable[[int], int]] = {}
        self.__sub_index: dict[str, Callable[[tuple], int]] = {}
        self.__chunk: str = ""
        self.__cfg: AllAnimeCryptoConfig

    @property
    def config(self) -> AllAnimeCryptoConfig:
        return self.__cfg

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
    def derive_nonce(*args) -> bytes:
        encoded = ":".join(map(str, args)).encode()
        return hashlib.sha256(encoded).digest()[:12]

    def hash(self, value: str) -> bytes:
        mul, add = self.__cfg.salt
        ret = b""
        for i in range(32):
            ch = value[i % len(value)]
            mask = 255 & (i * mul + add)
            ret += int.to_bytes(ord(ch) ^ mask)
        return ret

    def xor(self, value1: bytes, value2: bytes) -> bytes:
        ret = b""
        mul, add = self.__cfg.frag
        for i, (b1, b2) in enumerate(zip(value1, value2)):
            v1 = b1 ^ b2
            v2 = 255 & ((i // 8) * mul + (i % 8) * add)
            ret += int.to_bytes(v1 ^ v2)

        return ret


    def _load_index_functions(self, chunk: str, array_func_name: str, specs: list[tuple[str, str, str]]) -> None:
        for func_name, global_name, local_offset_expr in specs:
            global_func_pattern = RE_SUB_INDEX_FUNC_PREFIX + global_name.replace("$", r"\$") + \
                RE_GLOBAL_FUNC_INFIX + array_func_name + RE_GLOBAL_FUNC_SUFFIX
            match = re.search(global_func_pattern, chunk)
            if not match:
                raise InvalidScript(f"global index function {global_name} not found")

            global_offset = eval(match.group(1))
            local_offset = eval(local_offset_expr)

            self.__global_index[global_name] = _make_global_index_func(global_offset)
            self.__sub_index[func_name] = _make_sub_index_func(local_offset, 1, self.__global_index[global_name])


    def _load_array(self) -> tuple[list[str], str]:
        match = re.search(RE_ARRAY_FUNC, self.__chunk)
        if not match:
            raise InvalidScript("array not found")

        array_func_name = match.group(1)
        array_func_body = match.group(2)
        
        array_items = [s.strip("'").strip('"') for s in re.findall(RE_QUOTED_STRING, array_func_body)]
        

        shuffle_func_pattern = RE_SHUFFLE_FUNC_PREFIX + array_func_name + RE_SHUFFLE_FUNC_SUFFIX
        match = re.search(shuffle_func_pattern, self.__chunk)
        if not match:
            raise InvalidScript("array shuffle function not found")

        shuffle_func_body = match.group(1)
        

        local_num_maps = {}
        local_num_map_matches = re.findall(RE_NUM_MAP, shuffle_func_body)
        if not local_num_map_matches:
            raise InvalidScript("no num maps found inside array shuffle func")

        for m_name, m, _, _ in local_num_map_matches:
            local_num_maps[m_name] = {}
            for k, v in re.findall(RE_NUM_MAP_ENTRY, m):
                local_num_maps[m_name][k] = int(v)

        

        
        local_func_matches = re.findall(RE_LOCAL_INDEX_FUNC, shuffle_func_body)
        if not local_func_matches:
            raise InvalidScript("no local index functions found")

        local_index: dict[str, Callable[[tuple], int]] = {}
        for local_name, arg_name, global_name, local_arg_name,\
            local_offset_expr, local_offset_expr_hex_key, local_offset_expr_hex_key2 in local_func_matches:

            global_func_pattern = RE_SUB_INDEX_FUNC_PREFIX + global_name.replace("$", r"\$") + \
                RE_GLOBAL_FUNC_INFIX + array_func_name + RE_GLOBAL_FUNC_SUFFIX
            match = re.search(global_func_pattern, self.__chunk)
            if not match:
                raise InvalidScript(f"global index function {global_name} not found")

            global_offset = eval(match.group(1))
            if local_offset_expr_hex_key:
                local_offset = local_num_maps[local_offset_expr_hex_key][local_offset_expr_hex_key2]
            else:
                local_offset = eval(local_offset_expr)

            
            self.__global_index[global_name] = _make_global_index_func(global_offset)
            arg_index = int(arg_name != local_arg_name)
            local_index[local_name] = \
                _make_sub_index_func(local_offset, arg_index, self.__global_index[global_name])

        
        shuffle_check_indexes = []
        for fn,\
            val1, val1_hex_key1, val1_hex_key2,\
            val2, val2_hex_key1, val2_hex_key2 in re.findall(RE_SHUFFLE_CHECK, shuffle_func_body):

            
            if val1_hex_key1:
                val1 = local_num_maps[val1_hex_key1][val1_hex_key2] * (1 - val1.startswith('-') * 2)

            if val2_hex_key1:
                val2 =  local_num_maps[val2_hex_key1][val2_hex_key2]  * (1 - val2.startswith('-') * 2)

            
            
            shuffle_check_indexes.append(local_index[fn]((int(val1), int(val2))))

        

        while None in [parse_int(array_items[i]) for i in shuffle_check_indexes]:
            array_items.append(array_items.pop(0))

        
        return array_items, array_func_name

    def _get_mask(self, array: list[str], array_func_name: str) -> bytes:
        match = re.search(RE_MASK_ARRAY, self.__chunk)
        if not match:
            raise InvalidScript("mask array not found")

        mask_array_body = match.group(1)
        specs = []
        mask_data = []
        for sub_func_name, value_str in re.findall(RE_GLOBAL_INDEX_FUNC_CALL, mask_array_body):
            
            sub_func_pattern = RE_SUB_INDEX_FUNC_PREFIX + sub_func_name.replace("$", r'\$') + RE_INDEX_FUNC_BODY2
            
            sub_match = re.search(sub_func_pattern, self.__chunk)
            if not sub_match:
                raise InvalidScript(f"no {sub_func_name} sub index function found")

            groups = list(filter(None, sub_match.groups()))

            global_name = groups[1]
            local_offset_expr = groups[-1]
            
            

            if global_name not in self.__global_index:
                raise InvalidScript(f"unknown global index function {global_name}")

            specs.append((sub_func_name, global_name, local_offset_expr))
            mask_data.append((global_name, value_str, eval(local_offset_expr)))

        self._load_index_functions(self.__chunk, array_func_name, specs)

        mask_indexes = [
            self.__global_index[global_name](int(float(value_str) - local_offset))
            for global_name, value_str, local_offset in mask_data
        ]
        

        mask = b""
        step = 4
        for i in range(0, len(mask_indexes), step):
            parts = [array[mask_indexes[i+ii]] for ii in range(step)]
            
            mask += base64.b64decode("".join(parts))

        return mask

    def _get_build_id(self, array: list[str]) -> str:
        match = re.search(RE_BUILD_ID, self.__chunk)
        if not match:
            raise InvalidScript("build id not found")

        sub_func_name = match.group(1)
        arg = int(match.group(2))
        build_id_idx = self.__sub_index[sub_func_name]((0, arg))
        return array[build_id_idx]

    def _get_base_config(self, array: list[str]) -> AllAnimeCryptoConfig:
        cfg = AllAnimeCryptoConfig()

        cfg_m = re.search(RE_BOOT_CFG, self.__chunk)
        if not cfg_m:
            raise InvalidScript("boot config not found")

        cfg.salt = (int(cfg_m.group(1)), int(cfg_m.group(2)))
        cfg.frag = (int(cfg_m.group(3)), int(cfg_m.group(4)))

        boot_prefix_body = cfg_m.group(5)
        boot_prefix_parts = []
        for fn, idx in re.findall(RE_GLOBAL_INDEX_FUNC_CALL, boot_prefix_body):
            arr_idx = self.__sub_index[fn]((0, int(float(idx))))
            boot_prefix_parts.append(array[arr_idx])
            
        if '"' in boot_prefix_body:
            suffix = re.search(r'"([\w:]+)"', boot_prefix_body)
            if suffix:
                boot_prefix_parts += suffix.group(1)

        cfg.boot_prefix = ''.join(boot_prefix_parts)

        cfg.join = cfg_m.group(8)
        cfg.parts = []

        parts_body = cfg_m.group(9)
        for *_, string in re.findall(RE_GLOBAL_INDEX_FUNC_CALL + r'\+\"(\w+)\"', parts_body):
            part = ""
            match string:
                case "up":
                    part = "group"
                case "e":
                    part = "lane"
                case "ch":
                    part = "epoch"
                case "t":
                    part = "host"
                case "d":
                    part = "buildId"

            assert(part)
            cfg.parts.append(part)

        return cfg

    # return True if page changed
    async def _load_chunk(self) -> bool:
        headers = {
            "Origin": f"https://mkissa.to", 
            "Referer": f"https://mkissa.to/"
        }
        resp_headers = {}

        front_end = await request_get(
            self.__frontend, 
            headers=headers,
            resp_headers=resp_headers,
            func=return_text
        )

        link = resp_headers["Link"]
        cache = hashlib.sha256(link.encode()).digest()

        if cache == self.__cache:
            return False

        self.__cache = cache
        app_pattern = rf'({self.__cdn}/all/mk/_app/immutable/entry/app\.[\w-]+\.js)'

        m = re.search(app_pattern, front_end)
        if not m:
            raise InvalidFrontendPage("app .js file not found")

        app_script_url = m.group(1)
        app_script = await request_get(app_script_url, func=return_text)

        m = re.findall(RE_CHUNK_URL, app_script)
        if not m:
            raise InvalidScript("no chunks found")

        chunk_url = m[0].replace("..", f"{self.__cdn}/all/mk/_app/immutable/")
        self.__chunk = await request_get(chunk_url, func=lambda r: r.text())

        return True


    async def load_config(self) -> AllAnimeCryptoConfig:
        if not await self._load_chunk():
            return self.__cfg

        cfg = AllAnimeCryptoConfig()
        array, array_func_name = self._load_array()

        mask = self._get_mask(array, array_func_name)
        build_id = self._get_build_id(array)

        cfg = self._get_base_config(array)

        cfg.mask = mask
        cfg.build_id = build_id
        cfg.epoch = current_epoch()
        cfg.lane = CONTENT_LANE

        self.__cfg = cfg
        return cfg


    async def get_aa_crypto(self, sign_key: bytes, cfg: AllAnimeCryptoConfig, host: str) -> dict:
        if host == "mkissa.to":
            key_group = "mkissa"
        else:
            key_group = "mirror"

        aa_boot_values_all = {
            "lane":     cfg.lane,
            "buildId":  cfg.build_id,
            "epoch":    str(cfg.epoch),
            "host":     host,
            "group":    key_group,
        }
        aa_boot_values = []
        for p in cfg.parts:
            aa_boot_values.append(aa_boot_values_all[p])

        aa_boot_key = self.sign(f'{cfg.boot_prefix}{cfg.build_id}', sign_key)
        aa_boot = self.sign(cfg.join.join(aa_boot_values), aa_boot_key)

        url = "https://api.mkissa.net/client-crypto/v1/bootstrap"
        headers = {
            "Origin": f"https://{host}",
            "Referer": f"https://{host}/",
            "x-aa-boot": aa_boot.hex(),
            "x-build-id": cfg.build_id,
        }

        params = {
            "buildId": cfg.build_id,
            "k": cfg.lane,
        }

        resp = await request_get(url, headers=headers, params=params, func=return_json)
        return resp

class AllAnime:
    headers = {
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0",
        "referer": "https://allanime.day/",
    }

    __crypto_key = b""
    __crypto: AllAnimeCrypto | None = None
    
    @classmethod
    async def generate_aareq(cls, qh: str, host: str) -> tuple[str, str]:
        if cls.__crypto: 
            crypto = cls.__crypto
        else:
            crypto = AllAnimeCrypto()
            cls.__crypto = crypto

        cfg = await crypto.load_config()

        build_id_hash = crypto.hash(cfg.build_id)
        sign_key = crypto.xor(build_id_hash, cfg.mask)

        aa_crypto = await crypto.get_aa_crypto(sign_key, cfg, host)
        part_b = aa_crypto.get('partB')
        if not part_b:
            raise InvalidResponse(aa_crypto)

        ts = int(time.time() * 1000) // 300_000 * 300_000
        json_blob = {
            "v":        1,
            "ts":       ts,
            "epoch":    cfg.epoch,
            "buildId":  cfg.build_id,
            "qh":       qh,
            "k":        cfg.lane,
        }

        nonce = crypto.derive_nonce(cfg.epoch, cfg.build_id, qh, ts, cfg.lane)
        cls.__crypto_key = crypto.derive_key(sign_key, part_b)
        json_blob_string = json.dumps(json_blob, separators=(',',':'))

        aes = AES.new(cls.__crypto_key, AES.MODE_GCM, nonce=nonce)
        cipher, tag = aes.encrypt_and_digest(json_blob_string.encode())

        aa_req = base64.b64encode(b"\x01" + nonce + cipher + tag).decode()
        return aa_req, cfg.build_id


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
