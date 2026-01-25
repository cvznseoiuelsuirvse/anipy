from enum import Enum


class Extractor:
    headers: dict[str, str]

    def __init__(self, embed_url: str) -> None:
        self.embed_url = embed_url

    async def extract(self) -> dict: ...


from .megacloud import Megacloud as Megacloud
from .megaplay import Megaplay as Megaplay


class Extractors(Enum):
    MEGACLOUD = Megacloud
    MEGAPLAY = Megaplay
