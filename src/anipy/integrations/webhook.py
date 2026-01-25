import aiohttp
import json
from dataclasses import dataclass
from typing import IO, Literal, Callable, Awaitable
from enum import IntFlag


type _Response[_T] = tuple[int, _T]


async def make_request[T](
    method: str,
    url: str,
    *,
    params: dict | None,
    body: dict | None,
    func: Callable[[aiohttp.ClientResponse], Awaitable[T]],
) -> _Response[T]:
    args = {
        "params": params,
        "data": None,
        "json": None,
    }

    if body and "file" in body:
        data = aiohttp.FormData()

        file: "File" = body["file"]
        body.pop("file")
        data.add_field("file", file.content, filename=file.name)

        data.add_field("payload_json", json.dumps(body))

        args["data"] = data

    elif body:
        args["json"] = body

    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, **args) as resp:
            return resp.status, await func(resp)


# fmt: off
class WebhookFlags(IntFlag):
    CROSSPOSTED                             = 1
    IS_CROSSPOST                            = 1 << 1
    SUPPRESS_EMBEDS                         = 1 << 2
    SOURCE_MESSAGE_DELETED                  = 1 << 3
    URGENT                                  = 1 << 4
    HAS_THREAD                              = 1 << 5
    EPHEMERAL                               = 1 << 6
    LOADING                                 = 1 << 7
    FAILED_TO_MENTION_SOME_ROLES_IN_THREAD  = 1 << 8
    SUPPRESS_NOTIFICATIONS                  = 1 << 12
    IS_VOICE_MESSAGE                        = 1 << 13
    HAS_SNAPSHOT                            = 1 << 14
    IS_COMPONENTS_V2                        = 1 << 15
# fmt: on


class Payload:
    def json(self) -> dict:
        d = {}

        for key in dir(self):
            value = getattr(self, key)

            if key.startswith("_") or callable(value) or not value:
                continue

            if isinstance(value, Payload):
                value = value.json()

            elif isinstance(value, list):
                value = [v.json() for v in value]

            d[key] = value

        return d

    def load(self, data: dict) -> None:
        for k, v in data.items():
            setattr(self, k, v)


@dataclass
class EmbedField(Payload):
    name: str
    value: str


@dataclass
class EmbedImage(Payload):
    image: str
    width: int = 0
    height: int = 0


@dataclass
class Embed(Payload):
    title: str | None = None
    type: Literal["rich", "image", "video", "gifv", "article", "link", "poll_result"] = "rich"
    description: str | None = None
    url: str | None = None
    color: int = 0xFF0000
    image: EmbedImage | None = None
    fields: list[EmbedField] | None = None


@dataclass
class File:
    name: str
    content: IO[bytes]


@dataclass
class Body(Payload):
    content: str | None = None
    username: str | None = None
    avatar_url: str | None = None
    embeds: list[Embed] | None = None
    file: File | None = None
    flags: WebhookFlags = WebhookFlags(0)

    def __post_init__(self):
        if self.content is None and self.embeds is None and self.file is None:
            raise ValueError("At least one of following must be specified: content, file, embeds")


class Webhook:
    application_id: str
    avatar: str
    channel_id: str
    guild_id: str
    id: str
    name: str
    type: int
    token: str

    def __init__(self, url: str) -> None:
        self.url = url

    async def info(self) -> _Response[dict]:
        resp: _Response[dict] = await make_request(
            "GET",
            self.url,
            params=None,
            body=None,
            func=lambda r: r.json(),
        )

        for k, v in resp[1].items():
            setattr(self, k, v)

        return resp

    async def send(self, message: Body) -> _Response[dict]:
        data = message.json()
        return await make_request(
            "POST",
            self.url,
            params={"wait": "true"},
            body=data,
            func=lambda r: r.json(),
        )

    async def edit(self, message_id: str, message: Body) -> _Response[dict]:
        data = message.json()
        return await make_request(
            "PATCH",
            self.url + f"/messages/{message_id}",
            params=None,
            body=data,
            func=lambda r: r.json(),
        )

    async def delete(self, message_id: str) -> _Response[dict | str]:
        return await make_request(
            "DELETE",
            self.url + f"/messages/{message_id}",
            params=None,
            body=None,
            func=lambda r: r.json() if r.status != 204 else r.text(),
        )
