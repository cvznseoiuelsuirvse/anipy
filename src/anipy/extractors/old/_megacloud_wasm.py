import base64
import hashlib
import json
import re
import struct
import aiohttp
import PIL.Image

from io import BytesIO
from typing import Any, Awaitable, Callable
from numpy import array
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from wasmtime import Engine, Func, FuncType, Instance, Linker, Memory, Module, Store, ValType
from .._types.structs import Extractor


engine = Engine()
store = Store(engine)
wasminstance: Instance | None = None
wasmmemory: Memory | None = None

arr: list[Any] = [None] * 128
pointer = len(arr)
size: int
user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
base_url = "https://megacloud.blog"


data_url = "data:image/png;base64,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JDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAtwCFrnv+pEcAAQQQECJAoQsZJDEQQAABBHQLUOi65096BBBAAAEhAhS6kEESAwEEEEBAt8D/ATY93seMmImHAAAAAElFTkSuQmCC"


class Meta:
    content: str


class ImageData:
    height = 50
    width = 65
    data: list[int]


class Canvas:
    baseUrl: str


class LocalStorage:
    kversion: str
    kid: str

    def setItem(self, item, value):
        setattr(self, item, value)


class Navigator:
    webdriver = False
    userAgent = user_agent


class Location:
    href: str
    origin = base_url


class Performance:
    timeOrigin = 0


class Window:
    localStorage = LocalStorage()
    navigator = Navigator()
    location = Location()
    performance = Performance()
    document = {}
    crypto = {}
    msCrypto = {}
    browser_version = 1878522368
    origin = base_url
    pid: str
    xrax: str

    def navigate(self) -> bytes: ...
    def jwt_plugin(self, wasm: bytearray) -> None: ...


class Image:
    src: str
    height = 50
    width = 65
    complete = True


class NodeList:
    image = Image()
    length = 1


meta = Meta()
image_data = ImageData()
canvas = Canvas()
window = Window()
node_list = NodeList()


def get_memory_buffer() -> bytearray:
    return wasminstance.exports(store)["memory"].read(store)


def write_to_memory(data, offset: int) -> None:
    if isinstance(data, bytes | bytearray):
        wasmmemory.write(store, data, offset)

    else:
        raise ValueError(f"can't write '{type(data).__name__}' type")


def set_float64(offset: int, value: int) -> None:
    write_to_memory(struct.pack("<d", value), offset)


def set_int32(offset: int, value: int) -> None:
    write_to_memory(struct.pack("<i", value), offset)


async def make_request[T](url: str, headers: dict, params: dict, func: Callable[[aiohttp.ClientResponse], Awaitable[T]]) -> T:
    async with aiohttp.ClientSession() as client:
        async with client.get(url, headers=headers, params=params) as resp:
            return await func(resp)


async def get_pixel_arr(url: str) -> list[int]:
    data = await make_request(url, {}, {}, lambda i: i.read())
    image = PIL.Image.open(BytesIO(data))

    return array(image).flatten().tolist()


def is_null(obj):
    return obj is None


def get(index: int) -> Any:
    return arr[index]


def parse(text: str) -> int:
    global size

    buffer = bytearray()
    text_len = len(text)
    offset = export0(text_len, 1)

    for i, char in enumerate(text, 1):
        char_code = ord(char)

        if char_code > 127:
            break

        if char == text[-1]:
            size = i

        buffer.append(char_code)

    write_to_memory(buffer, offset)

    return offset


def shift(index: int) -> None:
    global pointer

    if index >= 132:
        arr[index] = pointer
        pointer = index


def shift_get(index: int):
    item = get(index)
    shift(index)

    return item


def decode_sub(index: int, offset: int) -> str:
    index &= 0xFFFFFFFF

    return get_memory_buffer()[index : index + offset].decode()


def add_to_stack(obj) -> int:
    global arr, pointer

    if pointer == len(arr):
        arr.append(len(arr) + 1)

    Qn = pointer
    pointer = get(Qn)
    arr[Qn] = obj

    return Qn


def args(QP, Qn, QT, func):
    Qx = {
        "a": QP,
        "b": Qn,
        "cnt": 1,
        "dtor": QT,
    }
    __wbindgen_export_2 = wasminstance.exports(store)["__wbindgen_export_2"]

    def wrapped(*Qw):
        Qx["cnt"] += 1
        try:
            return func(Qx["a"], Qx["b"], *Qw)
        finally:
            Qx["cnt"] -= 1
            if Qx["cnt"] == 0:
                __wbindgen_export_2.get(store, Qx["dtor"])(Qx["a"], Qx["b"])

                Qx["a"] = 0

    setattr(wrapped, "original", Qx)

    return wrapped


def export0(Qp, Qn) -> int:
    __wbindgen_export_0 = wasminstance.exports(store)["__wbindgen_export_0"]
    return __wbindgen_export_0(store, Qp, Qn) & 0xFFFFFFFF


def export3(Qp, Qn) -> int:
    __wbindgen_export_3 = wasminstance.exports(store)["__wbindgen_export_3"]
    return shift_get(__wbindgen_export_3(store, Qp, Qn))


def export4(Qy, QO, Qx):
    __wbindgen_export_4 = wasminstance.exports(store)["__wbindgen_export_4"]
    __wbindgen_export_4(store, Qy, QO, add_to_stack(Qx))


def export5(Qp, Qn):
    __wbindgen_export_4 = wasminstance.exports(store)["__wbindgen_export_5"]
    __wbindgen_export_4(store, Qp, Qn)


def write_png(decoded_png):
    global size

    png_len = len(decoded_png)
    size = png_len

    offset = export0(png_len, 1)
    write_to_memory(bytearray(decoded_png), offset)

    return offset


def load_wasm_imports() -> Linker:
    linker = Linker(engine)

    def add_import_func(type: FuncType, func, name: str | None = None):
        linker.define(store, "wbg", func.__name__ if not name else name, Func(store, type, func))

    TYPE0 = FuncType([ValType.i32(), ValType.i32()], [ValType.i32()])
    TYPE1 = FuncType([ValType.i32(), ValType.i32(), ValType.i32()], [ValType.i32()])
    TYPE2 = FuncType([ValType.i32(), ValType.i32()], [])
    TYPE3 = FuncType([ValType.i32()], [ValType.i32()])
    TYPE4 = FuncType([ValType.i32(), ValType.i32(), ValType.i32()], [])
    TYPE5 = FuncType([ValType.i32()], [])
    TYPE6 = FuncType([ValType.i32(), ValType.i32(), ValType.i32(), ValType.i32()], [])
    TYPE7 = FuncType([ValType.i32(), ValType.i32(), ValType.i32(), ValType.i32(), ValType.i32()], [])
    TYPE8 = FuncType([], [ValType.i32()])
    TYPE11 = FuncType([ValType.i32(), ValType.f64(), ValType.f64(), ValType.f64(), ValType.f64()], [])
    TYPE15 = FuncType([ValType.i32(), ValType.f64()], [])
    TYPE16 = FuncType([ValType.i32(), ValType.i32(), ValType.f64(), ValType.f64()], [])
    TYPE17 = FuncType([ValType.i32(), ValType.f64(), ValType.f64(), ValType.f64(), ValType.f64()], [ValType.i32()])
    TYPE18 = FuncType([ValType.i32(), ValType.i32(), ValType.i32(), ValType.f64(), ValType.f64()], [])
    TYPE19 = FuncType([ValType.i32()], [ValType.f64()])

    def __wbindgen_is_undefined(index):
        obj = get(index)
        return is_null(obj)

    add_import_func(TYPE3, __wbindgen_is_undefined)

    def __wbindgen_is_null(*_):
        return False

    add_import_func(TYPE3, __wbindgen_is_null)

    def __wbindgen_string_get(offset, index):
        string = get(index)
        val = parse(string)

        set_int32(offset + 4, size)
        set_int32(offset, val)

    add_import_func(TYPE2, __wbindgen_string_get)

    def __wbindgen_object_drop_ref(index):
        shift_get(index)

    add_import_func(TYPE5, __wbindgen_object_drop_ref)

    def __wbindgen_cb_drop(index):
        org = shift_get(index).original
        org["cnt"] -= 1

        if org["cnt"] == 1:
            org["a"] = 0
            return True

        return False

    add_import_func(TYPE3, __wbindgen_cb_drop)

    def __wbindgen_string_new(index, offset):
        string = decode_sub(index, offset)
        return add_to_stack(string)

    add_import_func(TYPE0, __wbindgen_string_new)

    def __wbindgen_boolean_get(index):
        boolean = get(index)
        return 1 if boolean else 0 if isinstance(boolean, bool) else 2

    add_import_func(TYPE3, __wbindgen_boolean_get)

    def __wbindgen_number_get(offset, index):
        number = get(index)

        set_float64(offset + 8, 0 if is_null(number) else number)
        set_int32(offset, 0 if is_null(number) else 1)

    add_import_func(TYPE2, __wbindgen_number_get)

    def __wbg_instanceof_CanvasRenderingContext2d_4ec30ddd3f29f8f9(_):
        return True

    add_import_func(TYPE3, __wbg_instanceof_CanvasRenderingContext2d_4ec30ddd3f29f8f9)

    def __wbg_setfillStyle_59f426135f52910f(*_):
        pass

    add_import_func(TYPE2, __wbg_setfillStyle_59f426135f52910f)

    def __wbg_setshadowBlur_229c56539d02f401(*_):
        pass

    add_import_func(TYPE15, __wbg_setshadowBlur_229c56539d02f401)

    def __wbg_setshadowColor_340d5290cdc4ae9d(*_):
        pass

    add_import_func(TYPE4, __wbg_setshadowColor_340d5290cdc4ae9d)

    def __wbg_setfont_16d6e31e06a420a5(*_):
        pass

    add_import_func(TYPE4, __wbg_setfont_16d6e31e06a420a5)

    def __wbg_settextBaseline_c3266d3bd4a6695c(*_):
        pass

    add_import_func(TYPE4, __wbg_settextBaseline_c3266d3bd4a6695c)

    def __wbg_drawImage_cb13768a1bdc04bd(*_):
        pass

    add_import_func(TYPE16, __wbg_drawImage_cb13768a1bdc04bd)

    def __wbg_getImageData_66269d289f37d3c7(*_):
        return add_to_stack(image_data)

    add_import_func(TYPE17, __wbg_getImageData_66269d289f37d3c7)

    def __wbg_rect_2fa1df87ef638738(*_):
        pass

    add_import_func(TYPE11, __wbg_rect_2fa1df87ef638738)

    def __wbg_fillRect_4dd28e628381d240(*_):
        pass

    add_import_func(TYPE11, __wbg_fillRect_4dd28e628381d240)

    def __wbg_fillText_07e5da9e41652f20(*_):
        pass

    add_import_func(TYPE18, __wbg_fillText_07e5da9e41652f20)

    def __wbg_setProperty_5144ddce66bbde41(*_):
        pass

    add_import_func(TYPE7, __wbg_setProperty_5144ddce66bbde41)

    def __wbg_createElement_03cf347ddad1c8c0(*_):
        return add_to_stack(canvas)

    add_import_func(TYPE1, __wbg_createElement_03cf347ddad1c8c0)

    def __wbg_querySelector_118a0639aa1f51cd(*_):
        return add_to_stack(meta)

    add_import_func(TYPE1, __wbg_querySelector_118a0639aa1f51cd)

    def __wbg_querySelectorAll_50c79cd4f7573825(*_):
        return add_to_stack(node_list)

    add_import_func(TYPE1, __wbg_querySelectorAll_50c79cd4f7573825)

    def __wbg_getAttribute_706ae88bd37410fa(offset, *_):
        attr = meta.content
        todo = 0 if is_null(attr) else parse(attr)

        set_int32(offset + 4, size)
        set_int32(offset, todo)

    add_import_func(TYPE6, __wbg_getAttribute_706ae88bd37410fa)

    def __wbg_target_6795373f170fd786(index):
        obj = get(index)
        return add_to_stack(obj)

    add_import_func(TYPE3, __wbg_target_6795373f170fd786)

    def __wbg_addEventListener_f984e99465a6a7f4():
        pass

    add_import_func(TYPE6, __wbg_addEventListener_f984e99465a6a7f4)

    def __wbg_instanceof_HtmlCanvasElement_1e81f71f630e46bc(_):
        return True

    add_import_func(TYPE3, __wbg_instanceof_HtmlCanvasElement_1e81f71f630e46bc)

    def __wbg_setwidth_233645b297bb3318(index, set):
        get(index).width = set & 0xFFFFFFFF

    add_import_func(TYPE2, __wbg_setwidth_233645b297bb3318)

    def __wbg_setheight_fcb491cf54e3527c(index, set):
        get(index).height = set & 0xFFFFFFFF

    add_import_func(TYPE2, __wbg_setheight_fcb491cf54e3527c)

    def __wbg_getContext_dfc91ab0837db1d1(index, *_):
        obj = get(index)
        return add_to_stack(obj)

    add_import_func(TYPE1, __wbg_getContext_dfc91ab0837db1d1)

    def __wbg_toDataURL_97b108dd1a4b7454(offset, _):
        data_url_ = parse(data_url)

        set_int32(offset + 4, size)
        set_int32(offset, data_url_)

    add_import_func(TYPE2, __wbg_toDataURL_97b108dd1a4b7454)

    def __wbg_style_ca229e3326b3c3fb(index):
        obj = get(index)
        return add_to_stack(obj)

    add_import_func(TYPE3, __wbg_style_ca229e3326b3c3fb)

    def __wbg_instanceof_HtmlImageElement_9c82d4e3651a8533(*_):
        return True

    add_import_func(TYPE3, __wbg_instanceof_HtmlImageElement_9c82d4e3651a8533)

    def __wbg_src_87a0e38af6229364(offset, index):
        image = get(index)
        src = parse(image.src)

        set_int32(offset + 4, size)
        set_int32(offset, src)

    add_import_func(TYPE2, __wbg_src_87a0e38af6229364)

    def __wbg_width_e1a38bdd483e1283(index):
        image = get(index)
        return image.width

    add_import_func(TYPE3, __wbg_width_e1a38bdd483e1283)

    def __wbg_height_e4cc2294187313c9(index):
        image = get(index)
        return image.height

    add_import_func(TYPE3, __wbg_height_e4cc2294187313c9)

    def __wbg_complete_1162c2697406af11(index):
        image = get(index)
        return image.complete

    add_import_func(TYPE3, __wbg_complete_1162c2697406af11)

    def __wbg_data_d34dc554f90b8652(offset, index):
        imagedata = get(index)
        data = write_png(imagedata.data)

        set_int32(offset + 4, size)
        set_int32(offset, data)

    add_import_func(TYPE2, __wbg_data_d34dc554f90b8652)

    def __wbg_origin_305402044aa148ce(offset, index):
        location = get(index)
        origin = parse(location.origin)

        set_int32(offset + 4, size)
        set_int32(offset, origin)

    add_import_func(TYPE2, __wbg_origin_305402044aa148ce)

    def __wbg_length_8a9352f7b7360c37(index):
        nodelist = get(index)
        return nodelist.length

    add_import_func(TYPE3, __wbg_length_8a9352f7b7360c37)

    def __wbg_get_c30ae0782d86747f(index, _):
        nodelist = get(index)
        return add_to_stack(nodelist.image)

    add_import_func(TYPE0, __wbg_get_c30ae0782d86747f)

    def __wbg_timeOrigin_f462952854d802ec(index):
        performance = get(index)
        return float(performance.timeOrigin)

    add_import_func(TYPE19, __wbg_timeOrigin_f462952854d802ec)

    def __wbg_instanceof_Window_cee7a886d55e7df5(*_):
        return True

    add_import_func(TYPE3, __wbg_instanceof_Window_cee7a886d55e7df5)

    def __wbg_document_eb7fd66bde3ee213(index):
        window = get(index)
        return add_to_stack(window.document)

    add_import_func(TYPE3, __wbg_document_eb7fd66bde3ee213)

    def __wbg_location_b17760ac7977a47a(index):
        window = get(index)
        return add_to_stack(window.location)

    add_import_func(TYPE3, __wbg_location_b17760ac7977a47a)

    def __wbg_localStorage_3d538af21ea07fcc(*_):
        return add_to_stack(window.localStorage)

    add_import_func(TYPE3, __wbg_localStorage_3d538af21ea07fcc)

    def __wbg_performance_4ca1873776fdb3d2(index):
        window = get(index)
        return add_to_stack(window.performance)

    add_import_func(TYPE3, __wbg_performance_4ca1873776fdb3d2)

    def __wbg_origin_e1f8acdeb3a39a2b(offset, index):
        window = get(index)
        origin = parse(window.origin)

        set_int32(offset + 4, size)
        set_int32(offset, origin)

    add_import_func(TYPE2, __wbg_origin_e1f8acdeb3a39a2b)

    def __wbg_get_8986951b1ee310e0(index, decode_index, decode_offset):
        window = get(index)
        attr = decode_sub(decode_index, decode_offset)

        data = getattr(window, attr)
        res = 0 if is_null(data) else add_to_stack(data)

        return res

    add_import_func(TYPE1, __wbg_get_8986951b1ee310e0)

    def __wbg_setTimeout_6ed7182ebad5d297(*_):
        return 7

    add_import_func(TYPE1, __wbg_setTimeout_6ed7182ebad5d297)

    def __wbindgen_is_object(index):
        obj = get(index)
        return obj is not None

    add_import_func(TYPE3, __wbindgen_is_object)

    def __wbg_crypto_1d1f22824a6a080c(index):
        window = get(index)
        return add_to_stack(window.crypto)

    add_import_func(TYPE3, __wbg_crypto_1d1f22824a6a080c)

    def __wbg_process_4a72847cc503995b(*_):
        return add_to_stack(None)

    add_import_func(TYPE3, __wbg_process_4a72847cc503995b)

    def __wbg_versions_f686565e586dd935(*_):
        return add_to_stack(None)

    add_import_func(TYPE3, __wbg_versions_f686565e586dd935)

    def __wbg_node_104a2ff8d6ea03a2(*_):
        return add_to_stack(None)

    add_import_func(TYPE3, __wbg_node_104a2ff8d6ea03a2)

    def __wbindgen_is_string(index):
        obj = get(index)
        return isinstance(obj, str)

    add_import_func(TYPE3, __wbindgen_is_string)

    def __wbg_require_cca90b1a94a0255b():
        pass

    add_import_func(TYPE8, __wbg_require_cca90b1a94a0255b)

    def __wbg_msCrypto_eb05e62b530a1508(index):
        window = get(index)
        return add_to_stack(window.msCrypto)

    add_import_func(TYPE3, __wbg_msCrypto_eb05e62b530a1508)

    def __wbg_randomFillSync_5c9c955aa56b6049():
        pass

    add_import_func(TYPE2, __wbg_randomFillSync_5c9c955aa56b6049)

    def __wbg_getRandomValues_3aa56aa6edec874c(*_):
        pass

    add_import_func(TYPE2, __wbg_getRandomValues_3aa56aa6edec874c)

    def __wbindgen_is_function(index):
        obj = get(index)
        return callable(obj)

    add_import_func(TYPE3, __wbindgen_is_function)

    def __wbg_self_05040bd9523805b9():
        return add_to_stack(window)

    add_import_func(TYPE8, __wbg_self_05040bd9523805b9)

    def __wbg_window_adc720039f2cb14f():
        return add_to_stack(window)

    add_import_func(TYPE8, __wbg_window_adc720039f2cb14f)

    def __wbg_globalThis_622105db80c1457d():
        return add_to_stack(window)

    add_import_func(TYPE8, __wbg_globalThis_622105db80c1457d)

    def __wbg_global_f56b013ed9bcf359():
        return add_to_stack(window)

    add_import_func(TYPE8, __wbg_global_f56b013ed9bcf359)

    def __wbg_newnoargs_cfecb3965268594c(*_):
        return 0

    add_import_func(TYPE0, __wbg_newnoargs_cfecb3965268594c)

    def __wbindgen_object_clone_ref(index):
        obj = get(index)
        return add_to_stack(obj)

    add_import_func(TYPE3, __wbindgen_object_clone_ref)

    def __wbg_eval_c824e170787ad184(index, offset):
        string = decode_sub(index, offset)

        try:
            if "window.pid" in string:
                pid = string.split("=")[1].replace("'", "").strip()
                window.pid = pid

                eval_result = pid

            else:
                eval_result = eval(string)

        except AttributeError:
            eval_result = None

        return add_to_stack(eval_result)

    add_import_func(TYPE0, __wbg_eval_c824e170787ad184)

    def __wbg_call_3f093dd26d5569f8(*_):
        return 0

    add_import_func(TYPE0, __wbg_call_3f093dd26d5569f8)

    def __wbg_call_67f2111acd2dfdb6():
        pass

    add_import_func(TYPE1, __wbg_call_67f2111acd2dfdb6)

    def __wbg_toString_6eb7c1f755c00453(_):
        return add_to_stack("[object Storage]")

    add_import_func(TYPE3, __wbg_toString_6eb7c1f755c00453)

    def __wbg_set_961700853a212a39(obj_index, key_index, value_index):
        try:
            setattr(get(obj_index), get(key_index), get(value_index))
            return True

        except AttributeError:
            return False

    add_import_func(TYPE1, __wbg_set_961700853a212a39)

    def __wbg_buffer_b914fb8b50ebbc3e(index):
        memory = get(index)
        return add_to_stack(memory.read(store))

    add_import_func(TYPE3, __wbg_buffer_b914fb8b50ebbc3e)

    def __wbg_toString_139023ab33acec36(index):
        obj = get(index)
        return add_to_stack(obj)

    add_import_func(TYPE3, __wbg_toString_139023ab33acec36)

    def __wbg_newwithbyteoffsetandlength_0de9ee56e9f6ee6e(index, offset, length):
        offset &= 0xFFFFFFFF
        length &= 0xFFFFFFFF

        buffer = get(index)
        slice = buffer[offset : offset + length]

        return add_to_stack(slice)

    add_import_func(TYPE1, __wbg_newwithbyteoffsetandlength_0de9ee56e9f6ee6e)

    def __wbg_new_b1f2d6842d615181(index):
        buffer = get(index)
        return add_to_stack(bytearray(buffer))

    add_import_func(TYPE3, __wbg_new_b1f2d6842d615181)

    def __wbg_newwithlength_0d03cef43b68a530(length):
        return add_to_stack(bytearray(length & 0xFFFFFFFF))

    add_import_func(TYPE3, __wbg_newwithlength_0d03cef43b68a530)

    def __wbg_buffer_67e624f5a0ab2319(index):
        buffer = get(index)
        return add_to_stack(buffer)

    add_import_func(TYPE3, __wbg_buffer_67e624f5a0ab2319)

    def __wbg_subarray_adc418253d76e2f1(index, start, end):
        start &= 0xFFFFFFFF
        end &= 0xFFFFFFFF

        buffer = get(index)
        return add_to_stack(bytearray(buffer[start:end]))

    add_import_func(TYPE1, __wbg_subarray_adc418253d76e2f1)

    def __wbg_length_21c4b0ae73cba59d(index):
        buffer = get(index)
        return len(buffer)

    add_import_func(TYPE3, __wbg_length_21c4b0ae73cba59d)

    def __wbg_set_7d988c98e6ced92d(index, index2, value):
        offset = value & 0xFFFFFFFF

        buffer = get(index)
        buffer2 = get(index2)

        buffer[offset : offset + len(buffer2)] = buffer2

    add_import_func(TYPE4, __wbg_set_7d988c98e6ced92d)

    def __wbindgen_throw():
        pass

    add_import_func(TYPE2, __wbindgen_throw)

    def __wbindgen_memory():
        return add_to_stack(wasminstance.exports(store)["memory"])

    add_import_func(TYPE8, __wbindgen_memory)

    def __wbindgen_closure_wrapper117(Qn, QT, *_):
        return add_to_stack(args(Qn, QT, 2, export3))

    add_import_func(TYPE1, __wbindgen_closure_wrapper117)

    def __wbindgen_closure_wrapper119(Qn, QT, *_):
        return add_to_stack(args(Qn, QT, 2, export4))

    add_import_func(TYPE1, __wbindgen_closure_wrapper119)

    def __wbindgen_closure_wrapper121(*_):
        return 0

    add_import_func(TYPE1, __wbindgen_closure_wrapper121)

    def __wbindgen_closure_wrapper123(*_):
        return 0

    add_import_func(TYPE1, __wbindgen_closure_wrapper123)

    return linker


def create_wasm_instance(wasmcontent: bytes, imports: Linker) -> Instance:
    module = Module(engine, wasmcontent)
    instance = imports.instantiate(store, module)
    return instance


async def load_wasm() -> bytearray:
    global wasminstance, wasmmemory

    url = "https://megacloud.blog/images/loading.png"
    headers = {"Host": "megacloud.blog"}
    params = {"v": "0.0.9"}

    b_resp = await make_request(url, headers, params, lambda i: i.read())
    imports = load_wasm_imports()
    instance = create_wasm_instance(b_resp, imports)

    wasminstance = instance
    wasmmemory = instance.exports(store)["memory"]

    return bytearray(b_resp)


async def run_wasm() -> bytes:
    wasm_bytes = await load_wasm()

    setattr(window, "bytes", wasm_bytes)

    wasminstance.exports(store)["groot"](store)
    window.jwt_plugin(wasm_bytes)
    return window.navigate()


async def get_meta(url) -> None:
    headers = {
        "User-Agent": user_agent,
        "Referer": "https://hianime.to/",
    }

    html_resp = await make_request(url, headers, {}, lambda i: i.text())
    pattern = r"name=\"j_crt\" content=\"([\w=]+)"

    if not (match := re.search(pattern, html_resp)):
        raise ValueError("no key found")

    meta.content = match.group(1)


def split_int32(value: int) -> list[int]:
    return [
        (0xFF000000 & value) >> 24,
        (0x00FF0000 & value) >> 16,
        (0x0000FF00 & value) >> 8,
        0x000000FF & value,
    ]


def apply_xor(value1, value2) -> list | None:
    try:
        for indx, item in enumerate(value1):
            value1[indx] = item ^ value2[indx % len(value2)]

    except Exception:
        return None


def derive_key_and_iv(password: bytes) -> tuple[bytes, bytes]:
    hashes = []
    digest = password

    for _ in range(3):
        hash = hashlib.md5(digest).digest()
        hashes.append(hash)
        digest = hash + password

    return hashes[0] + hashes[1], hashes[2]


def decrypt_sources(password: bytes, value: str) -> str:
    bs = AES.block_size
    encrypted = base64.b64decode(value)

    salt = encrypted[8:bs]
    data = encrypted[bs:]

    key, iv = derive_key_and_iv(password + salt)

    obj = AES.new(key, AES.MODE_CBC, iv)
    result = obj.decrypt(data)

    return unpad(result, AES.block_size).decode()


class Megacloud(Extractor):
    headers = {
        "User-Agent": user_agent,
        "Referer": "https://megacloud.club/",
        "Origin": "https://megacloud.club",
    }

    def __init__(self, embed_url: str) -> None:
        self.embed_url = embed_url

    async def _wasm_extract(self, id: str) -> dict:
        xrax = id
        src_url = f"{base_url}/embed-2/ajax/e-1/getSources"

        canvas.baseUrl = self.embed_url
        node_list.image.src = f"{base_url}/images/image.png?v=0.1.0"
        if not getattr(image_data, "data", None):
            image_data.data = await get_pixel_arr(node_list.image.src)

        window.location.href = self.embed_url
        window.xrax = xrax

        await get_meta(self.embed_url)
        q5 = await run_wasm()

        params = {
            "id": window.pid,
            "v": window.localStorage.kversion,
            "h": window.localStorage.kid,
            "b": window.browser_version,
        }

        resp = await make_request(src_url, self.headers, params, lambda i: i.json())

        if not resp["sources"]:
            raise ValueError("no sources found")

        q3 = int(window.localStorage.kversion)
        q1 = split_int32(q3)
        q5 = bytearray(q5)
        q8: bytearray

        if resp["t"] != 0:
            apply_xor(q5, q1)
            q8 = q5

        else:
            q8 = resp["k"]
            apply_xor(q8, q1)

        password = base64.b64encode(q8)
        sources = json.loads(decrypt_sources(password, resp["sources"]))

        resp["sources"] = sources
        resp["intro"] = resp["intro"]["start"], resp["intro"]["end"]
        resp["outro"] = resp["outro"]["start"], resp["outro"]["end"]

        return resp

    async def _old_extract(self, id: str) -> dict:
        keys_url = "https://raw.githubusercontent.com/superbillgalaxy/megacloud-keys/refs/heads/main/api.json"
        get_sources_url = f"{base_url}/embed-2/v2/e-1/getSources"

        res = await make_request(keys_url, {"ts-is": "insane"}, {}, lambda i: i.text())
        res = json.loads(res)
        key = res["megacloud"]

        resp = await make_request(get_sources_url, self.headers, {"id": id}, lambda i: i.json())
        sources = json.loads(decrypt_sources(key.encode(), resp["sources"]))

        resp["sources"] = sources
        resp["intro"] = resp["intro"]["start"], resp["intro"]["end"]
        resp["outro"] = resp["outro"]["start"], resp["outro"]["end"]

        return resp

    async def extract(self) -> dict:
        v1_pattern = r"embed-2/e-1/([A-z0-9]+)"
        v2_pattern = r"embed-2/v2/e-1/([A-z0-9]+)"

        if match := re.search(v1_pattern, self.embed_url):
            return await self._wasm_extract(match.group(1))

        elif match := re.search(v2_pattern, self.embed_url):
            return await self._old_extract(match.group(1))

        else:
            raise ValueError(f"no id found in {self.embed_url}")
