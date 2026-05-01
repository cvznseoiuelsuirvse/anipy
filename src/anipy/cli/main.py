import os
import time
import asyncio
import webbrowser

from typing import Callable, Iterable, Literal, overload

from ..core.types import LockFileKeys, DataList, SearchList, DataObject, SearchObject, EpisodeSources
from ..core.exceptions import InvalidResponse, InvalidStatusCode
from ..core.data import Data, Config, lock_file_update, lock_file_get_content
from ..core.util import is_similar, resolve_to_mal
from ..integrations.mal import MAL, MALListStatuses
from .builder import CLIApp, ErrorTypes


from .player import Player

cfg         = Config()
data        = Data(cfg)
provider    = lambda: cfg.provider.cls
mal         = MAL()
ctx: DataList | SearchList

TERM_WIDTH = lambda: os.get_terminal_size().columns


def get_longest_values(animes: Iterable) -> dict[str, int]:
    r = {}

    for item in animes:
        for k, v in vars(item).items():
            if not k.startswith("_") and not callable(v):
                length = len(str(v))
                r[k] = max(r.get(k, 0), length)

    return r

@overload
def format_ctx_list(ctx: DataList | SearchList) -> str: ...
@overload
def format_ctx_list(ctx: DataList, validate: Callable[[int, DataObject], bool]) -> str: ...
@overload
def format_ctx_list(ctx: SearchList, validate: Callable[[int, SearchObject], bool]) -> str: ...
def format_ctx_list(ctx: DataList | SearchList, validate: Callable[[int, DataObject], bool] | Callable[[int, SearchObject], bool] | None = None) -> str:
    longest_values = get_longest_values(ctx)
    longest_index = len(str(len(ctx) - 1))

    ret = []
    call_validate = lambda v, i, o: v is None or v(i, o)
    if isinstance(ctx, SearchList):
        longest_ep_count = longest_values["episode_count"]
        for i, anime in enumerate(ctx):
            line = f"  {str(i):<{longest_index}}  {str(anime.episode_count):>{longest_ep_count}} {anime.title}"

            if call_validate(validate, i, anime):
                ret.append(line)

    else:
        for i, anime in enumerate(ctx):
            if anime.highlighted:
                line = f"* {str(i):<{longest_index}}  {anime.title}"
            elif anime.continue_from > 1:
                line = f"> {str(i):<{longest_index}}  {anime.title} {anime.continue_from}/{anime.episode_count}"
            else:
                line = f"  {str(i):<{longest_index}}  {anime.title}"

            if call_validate(validate, i, anime):
                if anime.id == "school-days-8757":
                    line = f"\033[7m{line}\033[0m"
                ret.append(line)

    return "\n".join(ret)


async def get_episode(*, id: int, episode: int) -> EpisodeSources | None:
    anime = ctx[id]
    if episode not in range(1, anime.episode_count + 1):
        return cli.raise_err(ErrorTypes.INVALID_ARGS, "episode must be withing available episodes")

    if isinstance(anime, DataObject):
        try:
            external_id = await check_provider_external_id(anime)

        except ValueError as e:
            return cli.raise_err(ErrorTypes.INVALID_RESULT, e)
    else:
        external_id = anime.external_id

    episode_sources = await provider().get_episodes(external_id, episode)
    return episode_sources

async def update_watchlist(force: bool) -> None:
    async def uw(anime: DataObject):
        mal_id = await check_mal_external_id(anime)
        anime_new = await mal.get_anime(mal_id)

        for k, v in anime_new.json().items():
            if not k.startswith("_") and hasattr(anime, k):
                if isinstance(v, list):
                    v = ",".join(v)

                setattr(anime, k, v)

        data.update(anime)

    wl_last_updated = lock_file_get_content().get(LockFileKeys.WATCHLIST_LAST_REFRESH, 0)

    if force or int(time.time()) - wl_last_updated >= 86400:
        tasks = [uw(anime) for anime in data.watchlist if anime.airing_status == "airing"]
        try:
            await asyncio.gather(*tasks)

        except (InvalidStatusCode, InvalidResponse) as e:
            return cli.raise_err(ErrorTypes.INVALID_RESULT, f"failed to update watchlist: {e}")

        finally:
            lock_file_update(LockFileKeys.WATCHLIST_LAST_REFRESH, int(time.time()))


def show_banner() -> None:
    if cfg.banner:
        print()

    for b in cfg.banner:
        print(f"\033[1m{b}\033[0m")
        match b:
            case "continue watching":
                print(format_ctx_list(ctx, lambda _, anime: True if anime.continue_from > 1 else False))

            case "highlighted":
                print(format_ctx_list(ctx, lambda _, anime: True if anime.highlighted else False))

            case "status":
                watchlist_size = len(data.watchlist)
                completed_size = len(data.completed)
                print(f"watchlist: {watchlist_size}  completed: {completed_size}")

        print()

async def check_provider_external_id(anime: DataObject) -> str:
    if external_id := data.get_id(anime.id, cfg.provider): return external_id

    resp = await provider().search(anime.title)

    for a in resp:
        if a.title.lower() == anime.title.lower() or \
            anime.other_title.lower() == a.other_title.lower():

            data.add_id(anime.id, a.external_id, cfg.provider)
            return a.external_id

    raise ValueError("failed to get provider external_id")

async def get_mal_id(anime: SearchObject | DataObject) -> str | None:
    try:
        res = await mal.search(anime.other_title)

    except (InvalidResponse, InvalidStatusCode):
        pass

    else:
        for r in res:
            if anime.title.lower() == r.title.lower() or \
                anime.other_title.lower() == r.other_title.lower():
                return r.external_id

    id = await resolve_to_mal(anime.title, anime.other_title, return_id=True)
    if id:
        return id


async def check_mal_external_id(anime: DataObject) -> str:
    if mal_id := data.get_id(anime.id, "mal"): return mal_id

    mal_id = await get_mal_id(anime)
    if mal_id: return mal_id 

    raise ValueError(f'failed to get MAL external_id')


cli = CLIApp()


@cli.on(["s"])
async def search(title: str):
    """search for an anime"""
    global ctx

    try:
        resp = await provider().search(title)

    except (InvalidResponse, InvalidStatusCode) as e:
        return cli.raise_err(ErrorTypes.INVALID_RESULT, f"failed to get search results: {e}")

    ctx = SearchList(resp, title)
    cli.prompt = cfg.prompt.format(ctx.name)
    if resp:
        print(format_ctx_list(ctx))


@cli.on(validate={"id": lambda id: id in range(0, len(ctx))})
async def mal_search(id: int):
    """find anime on MAL"""
    title = ctx[id].title

    url = f"https://myanimelist.net/anime.php?q={title}&cat=anime"
    webbrowser.open(url)


@cli.on(validate={"id": lambda id: id in range(0, len(ctx))})
async def mal_page(id: int):
    """find exact anime page on MAL"""
    if id not in range(0, len(ctx)):
        return cli.raise_err(ErrorTypes.INVALID_ARGS, "index must be within context")

    anime = ctx[id]
    if isinstance(anime, DataObject):
        await check_mal_external_id(anime)
        mal_id = data.get_id(anime.id, "mal")

    else:
        mal_id = await resolve_to_mal(anime.title, anime.other_title, return_id=True)

    if mal_id is None:
        return cli.raise_err(ErrorTypes.INVALID_RESULT, f"Failed to find MAL page for {anime.title}")

    url = f"https://myanimelist.net/anime/{mal_id}"
    webbrowser.open(url)

@cli.on(["wl-add"], {"id": lambda id: id in range(0, len(ctx))})
async def watchlist_add(id: int):
    """add anime to watchlist"""
    if not isinstance(ctx, SearchList):
        return cli.raise_err(ErrorTypes.INVALID_CONTEXT, "context must be Search type")

    anime = ctx[id]
    anime_info = await provider().get_anime(anime.external_id)

    anime_info_json = anime_info.json()

    if anime_info.mal_id:
        anime_info_json.pop("mal_id")
    anime_info_json.pop("external_id")
    anime_info_json.pop("description")
    anime_info_json.pop("genres")

    anime_info_json["status"] = "watchlist"
    anime_info_json["added_at"] = int(time.time())

    do = DataObject(**anime_info_json)
    data.add(do, anime_info.external_id)

    try:
        if anime_info.mal_id:
            data.add_id(do.id, anime_info.mal_id, "mal")
            mal_id = anime_info.mal_id

        else:
            mal_id =  await check_mal_external_id(do)

        await mal.list_add(mal_id, 0, MALListStatuses.PLAN_TO_WATCH)

    except Exception as e:
        cli.raise_err(ErrorTypes.INVALID_RESULT, str(e), do.title)
        data.remove(do)


@cli.on(["wl-rm"], {"id": lambda id: id in range(0, len(ctx))})
async def watchlist_remove(id: int):
    """remove anime from watchlist"""
    if not isinstance(ctx, DataList):
        return cli.raise_err(ErrorTypes.INVALID_CONTEXT, "context must be Data type")

    anime = ctx[id]
    try:
        mal_id = await check_mal_external_id(anime)

    except ValueError as e:
        cli.raise_err(ErrorTypes.INVALID_RESULT, e, anime.title)
        return 

    data.remove(ctx[id])
    await mal.list_remove(mal_id)

@cli.on(["wl-drop"], {"id": lambda id: id in range(0, len(ctx))})
async def watchlist_drop(id: int):
    """drop anime"""
    if not isinstance(ctx, DataList):
        return cli.raise_err(ErrorTypes.INVALID_CONTEXT, "context must be Data type")

    anime = ctx[id]
    try:
        mal_id = await check_mal_external_id(anime)

    except ValueError as e:
        cli.raise_err(ErrorTypes.INVALID_RESULT, e, anime.title)
        return 

    anime.status = "dropped"
    anime.continue_from = 1
    anime.highlighted = False

    data.update(ctx[id])
    await mal.list_add(mal_id, anime.continue_from - 1, MALListStatuses.DROPPED)

def select_data_list(type: Literal["watchlist", "completed", "dropped"], part: str | None, n: int | None):
    global ctx

    if type == "watchlist":
        ctx = data.watchlist
    elif type == "completed":
        ctx = data.completed
    else:
        ctx = data.dropped

    cli.prompt = cfg.prompt.format(ctx.name)

    if ctx:
        ctx_len = len(ctx)
        n = n or 10

        if (type == "wl" and part is None) or part == "all":
            range_to_show = range(ctx_len)

        elif part == "head" and n:
            range_to_show = range(0, n)

        elif part == "tail" and n:
            if ctx_len - n > 0:
                range_to_show = range(ctx_len - n, ctx_len)
            else:
                return cli.raise_err(ErrorTypes.INVALID_ARGS, f"invalid number of rows to show: {n}")

        else:
            range_to_show = range(ctx_len - n, ctx_len)

        print(format_ctx_list(ctx, lambda i, _: True if i in range_to_show else False))

@cli.on(["wl"], {"part": lambda part: part in ("head", "tail", "all")})
def watchlist(part: str | None = None, n: int | None = None) -> None:
    select_data_list("watchlist", part, n)

@cli.on(["comp"], {"part": lambda part: part in ("head", "tail", "all")})
def completed(part: str | None = None, n: int | None = None) -> None:
    select_data_list("completed", part, n)

@cli.on(["drop"], {"part": lambda part: part in ("head", "tail", "all")})
def dropped(part: str | None = None, n: int | None = None) -> None:
    select_data_list("dropped", part, n)


@cli.on(validate={"id": lambda id: id in range(0, len(ctx))})
def highlight(id: int):
    """highlight anime in watchlist"""

    anime = data.watchlist[id]
    anime.highlighted = True
    data.update(anime)


@cli.on(validate={"id": lambda id: id in range(0, len(ctx))})
def dehighlight(id: int):
    """dehighlight anime in watchlist"""

    anime = data.watchlist[id]
    anime.highlighted = False
    data.update(anime)


@cli.on(["d"], {"id": lambda id: id in range(0, len(ctx))})
async def download(id: int, episode: int):
    """download an episode"""

    try:
        episode_sources = await get_episode(id=id, episode=episode)
        if not episode_sources:
            cli.raise_err(ErrorTypes.REQUEST_ERROR, "failed to get episode")
            return

        async with Player(provider().extractor_headers) as player:
            await player.download_file(episode_sources, os.getcwd())

    except (InvalidResponse, InvalidStatusCode, SystemError) as e:
        return cli.raise_err(ErrorTypes.INVALID_RESULT, e)


@cli.on(["p"], {"id": lambda id: id in range(0, len(ctx))})
async def play(id: int, episode: int):
    """play specified episode. this command won't increment continue_from, dehighlight, and move to completed (if last episode was played)"""

    anime = ctx[id]

    try:
        episode_sources = await get_episode(id=id, episode=episode)
        if not episode_sources:
            cli.raise_err(ErrorTypes.REQUEST_ERROR, "failed to get episode")
            return

        async with Player(provider().extractor_headers) as player:
            print(f"{anime.title}. Episode {episode}")
            await player.play_file(episode_sources)

    except (InvalidResponse, InvalidStatusCode, SystemError) as e:
        return cli.raise_err(ErrorTypes.INVALID_RESULT, e)


@cli.on(["p-next"], {"id": lambda id: id in range(0, len(ctx))})
async def play_next(id: int):
    """play next episode"""
    if not isinstance(ctx, DataList):
        return cli.raise_err(ErrorTypes.INVALID_CONTEXT)

    anime = ctx[id]
    episode = anime.continue_from

    try:
        mal_id = await check_mal_external_id(anime)

    except ValueError as e:
        cli.raise_err(ErrorTypes.INVALID_RESULT, e, anime.title)
        return 

    episode_sources = await get_episode(id=id, episode=episode)
    if not episode_sources:
        return

    try:
        async with Player(provider().extractor_headers) as player:
            print(f"{anime.title}. Episode {episode}")
            await player.play_file(episode_sources)

    except (InvalidResponse, InvalidStatusCode) as e:
        return cli.raise_err(ErrorTypes.INVALID_RESULT, e)

    else:
        if anime.status == "watchlist":
            if anime.highlighted:
                anime.highlighted = False

            if episode < anime.episode_count:
                anime.continue_from = episode + 1

                await mal.list_add(mal_id, anime.continue_from - 1, MALListStatuses.WATCHING)

            else:
                anime.finished_at = int(time.time())
                anime.status = "completed"
                anime.continue_from = 1

                await mal.list_add(mal_id, anime.episode_count, MALListStatuses.COMPLETED)

            data.update(anime)



@cli.on(["i"], {"id": lambda id: id in range(0, len(ctx))})
async def info(id: int, keys: list[str] | None = None):
    """show anime info"""
    anime = ctx[id]

    def truncate_string(s: str, max_width: int, shift: int) -> str:
        new_str = ""

        for i, c in enumerate(s):
            if i > 0 and i % max_width == 0:
                new_str += "\n" + " " * shift

            new_str += c

        return new_str.strip()

    if isinstance(anime, DataObject):
        try:
            mal_id = await check_mal_external_id(anime)
            anime_info = await mal.get_anime(mal_id)

        except ValueError as e:
            return cli.raise_err(ErrorTypes.INVALID_RESULT, e)
    else:
        mal_id = await get_mal_id(anime)
        if not mal_id:
            return cli.raise_err(ErrorTypes.INVALID_RESULT, "failed to get mal_id")

    anime_info = await mal.get_anime(mal_id)
    anime_json = anime_info.json()
    keys = keys or list(anime_json.keys())
    longest_key = len(max(keys, key=lambda i: len(i)))

    for key in keys:
        value = anime_json.get(key, -1)

        if value == -1:
            print(f"'{key}' key not found")
            continue

        if isinstance(value, str):
            value = truncate_string(value, TERM_WIDTH() // 2, longest_key + 3)

        match key:
            case "genres":
                value = ", ".join(value) if isinstance(value, list) else value.replace(",", ", ")

            case "added_at" | "finished_at":
                assert isinstance(value, int)
                if value > 1:
                    ts = time.strftime("%b %d %H:%M %Y", time.localtime(value))
                    value = ts

                else:
                    continue

            case "continue_from":
                continue

        print(f"  \033[1m{key:<{longest_key}}\033[0m {value}")


@cli.on()
def config_set(key: str, value: str):
    """set config value"""
    global ctx

    if err_message := cfg.update(key, value):
        cli.raise_err(ErrorTypes.INVALID_ARGS, err_message)

    if isinstance(ctx, SearchList) and key == "provider":
        ctx = data.watchlist
        cli.prompt = cfg.prompt.format(ctx.name)


@cli.on(validate={"key": lambda key: getattr(cfg, key, None) is not None})
def config_get(key: str):
    """get config value"""
    print(f"{key}:  {getattr(cfg, key)}")


@cli.on()
def config():
    """get all config info"""
    annotations = cfg._get_annotations()
    for k, v in annotations.items():
        print(f"  \033[1m{k:<9}\033[0m \033[3m{str(v):<17}\033[0m: {getattr(cfg, k)}")


@cli.on(
    ["comp-res"],
    {"id": lambda id: id in range(0, len(ctx))}
)
def completed_reset(id: int):
    """reset an anime by putting it back to watchlist from completed (if completed), and setting continue_from to 1"""

    if isinstance(ctx, SearchList):
        return cli.raise_err(ErrorTypes.INVALID_CONTEXT)

    anime = ctx[id]
    anime.continue_from = 1
    anime.status = "watchlist"

    if anime.finished_at:
        anime.finished_at = 0
        anime.added_at = int(time.time())

    data.update(anime)

@cli.on()
async def refresh():
    """refresh watchlist"""
    await update_watchlist(True)

async def main_():
    global ctx

    data.load()
    await mal.get_token()

    ctx = data.watchlist
    cli.prompt = cfg.prompt.format(ctx.name)
    await update_watchlist(False)

    show_banner()
    await cli.run()


def main():
    asyncio.run(main_())
