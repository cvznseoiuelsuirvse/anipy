from enum import StrEnum, Enum
from ..extractors import Megacloud, Megaplay


class LockFileKeys(StrEnum):
    DB_LAST_UPDATE = "db_last_updated"
    DB_PAGES = "db_pages"
    WATCHLIST_LAST_REFRESH = "watchlist_last_refresh"


class Extractors(Enum):
    MEGACLOUD = Megacloud
    MEGAPLAY = Megaplay


class Servers(StrEnum):
    RAPIDCLOUD = "1"
    STREAMTAPE = "3"
    VIDSTREAMING = "4"
    STREAMSB = "5"
    MEGAPLAY = "9"
