import zlib
import base64
import os
import json


def get_user_id() -> int:
    return os.getuid() if os.name == "posix" else os.getlogin()


type Serializable = str | int | list | dict


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
