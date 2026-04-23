import os
import time
import asyncio
import webbrowser

from typing import Callable, Iterable, overload

from ..core.types import LockFileKeys, DataList, SearchList, DataObject, SearchObject, EpisodeSources, EpisodeInfo
from ..core.exceptions import BadHost, BadResponse, ProviderRequestFailed
from ..core.data import Data, Config, lock_file_update, lock_file_get_content
from ..core.util import resolve_to_mal
from ..providers import Provider
from .builder import CLIApp, ErrorTypes


from .player import Player

data = Data()
cfg = Config()
provider = Provider(cfg.provider.cls)
ctx: DataList | SearchList

TERM_WIDTH = lambda: os.get_terminal_size().columns


def get_longest_values(objs: Iterable) -> dict[str, int]:
    r = {}

    for item in objs:
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
        for i, object in enumerate(ctx):
            line = f"  {str(i):<{longest_index}}  {str(object.episode_count):>{longest_ep_count}} {object.title}"

            if call_validate(validate, i, object):
                if object.id == "school-days-8757":
                    line = f"\033[7m{line}\033[0m"
                ret.append(line)

    else:
        for i, object in enumerate(ctx):
            if object.highlighted:
                line = f"* {str(i):<{longest_index}}  {object.title}"
            elif object.continue_from > 1:
                line = f"> {str(i):<{longest_index}}  {object.title} {object.continue_from}/{object.episode_count}"
            else:
                line = f"  {str(i):<{longest_index}}  {object.title}"

            if call_validate(validate, i, object):
                if object.id == "school-days-8757":
                    line = f"\033[7m{line}\033[0m"
                ret.append(line)

    return "\n".join(ret)


async def get_episode(*, id: int, episode: int) -> tuple[EpisodeInfo, EpisodeSources] | None:
    object = ctx[id]
    if episode not in range(1, object.episode_count + 1):
        return cli.raise_err(ErrorTypes.INVALID_ARGS, "episode must be withing available episodes")

    anime_info = await provider.get_anime_info(object.id)

    episode_info = anime_info.episodes[episode - 1]
    episode_id = episode_info.id

    episode_sources = await provider.get_episode_sources(episode_id)

    return episode_info, episode_sources

async def update_watchlist(force: bool) -> None:
    async def uw(obj: DataObject):
        obj_new = await provider.get_anime_info(obj.id)

        for k, v in obj_new.json().items():
            if not k.startswith("_") and hasattr(obj, k):
                if isinstance(v, list):
                    v = ",".join(v)

                setattr(obj, k, v)

        await data.update(obj)

    wl_last_updated = lock_file_get_content().get(LockFileKeys.WATCHLIST_LAST_REFRESH, 0)

    if force or int(time.time()) - wl_last_updated >= 86400:
        tasks = [uw(obj) for obj in data.watchlist if obj.airing_status == "currently"]
        try:
            await asyncio.gather(*tasks)

        except ProviderRequestFailed:
            return cli.raise_err(ErrorTypes.INVALID_RESULT, "failed to update watchlist")

        finally:
            lock_file_update(LockFileKeys.WATCHLIST_LAST_REFRESH, int(time.time()))


def show_banner() -> None:
    if cfg.banner:
        print()

    for b in cfg.banner:
        print(f"\033[1m{b}\033[0m")
        match b:
            case "continue watching":
                print(format_ctx_list(ctx, lambda _, object: True if object.continue_from > 1 else False))

            case "highlighted":
                print(format_ctx_list(ctx, lambda _, object: True if object.highlighted else False))

            case "status":
                watchlist_size = len(data.watchlist)
                completed_size = len(data.completed)
                print(f"watchlist: {watchlist_size}  completed: {completed_size}")

        print()


cli = CLIApp()


@cli.on(["s"])
async def search(title: str):
    """search for an anime"""
    global ctx

    try:
        resp = await provider.search(title)

    except ProviderRequestFailed:
        return cli.raise_err(ErrorTypes.INVALID_RESULT, "failed to get search results")

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
async def mal(id: int):
    """find exact anime page on MAL"""
    if id not in range(0, len(ctx)):
        return cli.raise_err(ErrorTypes.INVALID_ARGS, "index must be within context")

    anime = ctx[id]
    url = await resolve_to_mal(anime.title, anime.other_title)
    if url is None:
        return cli.raise_err(ErrorTypes.INVALID_RESULT, f"Failed to find MAL page for {anime.title}")

    webbrowser.open(url)


@cli.on(["wl"])
def watchlist():
    """show watchlist"""
    global ctx
    ctx = data.watchlist
    cli.prompt = cfg.prompt.format(ctx.name)

    if ctx:
        print(format_ctx_list(ctx))


@cli.on(["wl-add"], {"id": lambda id: id in range(0, len(ctx))})
async def watchlist_add(id: int):
    """add anime to watchlist"""
    if not isinstance(ctx, SearchList):
        return cli.raise_err(ErrorTypes.INVALID_CONTEXT, "context must be Search type")

    object_info = await provider.get_anime_info(ctx[id].id)
    object_info_json = object_info.json()

    object_info_json.pop("episodes")
    object_info_json["added_at"] = int(time.time())
    object_info_json["genres"] = ",".join(object_info.genres)
    object_info_json["status"] = "watchlist"

    await data.add(DataObject(object_info_json))


@cli.on(["wl-rm"], {"id": lambda id: id in range(0, len(ctx))})
async def watchlist_remove(id: int):
    """remove anime from watchlist"""
    if not isinstance(ctx, DataList):
        return cli.raise_err(ErrorTypes.INVALID_CONTEXT, "context must be Data type")

    await data.remove(ctx[id])


@cli.on(["comp"], {"part": lambda part: part in ["head", "tail", "all"]})
async def completed(part: str | None = None, n: int | None = None):
    """show completed list. part: head/tail/all. n: number of rows to show. if not arguments specified it will show last 10 rows"""
    global ctx
    ctx = data.completed
    cli.prompt = cfg.prompt.format(ctx.name)

    if ctx:
        ctx_len = len(ctx)
        n = n or 10

        if part == "all":
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


@cli.on(validate={"id": lambda id: id in range(0, len(ctx))})
async def highlight(id: int):
    """highlight anime in watchlist"""

    object = data.watchlist[id]
    object.highlighted = True
    await data.update(object)


@cli.on(validate={"id": lambda id: id in range(0, len(ctx))})
async def dehighlight(id: int):
    """dehighlight anime in watchlist"""

    object = data.watchlist[id]
    object.highlighted = False
    await data.update(object)


@cli.on(["d"], {"id": lambda id: id in range(0, len(ctx))})
async def download(id: int, episode: int):
    """download an episode"""
    episode_ = await get_episode(id=id, episode=episode)
    if not episode_:
        cli.raise_err(ErrorTypes.REQUEST_ERROR, "failed to get episode")
        return

    episode_info, episode_sources = episode_

    try:
        async with Player(provider.headers) as player:
            await player.download_file(episode_info, episode_sources, os.getcwd())

    except (BadResponse, BadHost, SystemError) as ex:
        return cli.raise_err(ErrorTypes.INVALID_RESULT, str(ex))


@cli.on(["p", "play"], {"id": lambda id: id in range(0, len(ctx))})
async def play(id: int, episode: int):
    """play specified episode. this command won't increment continue_from, dehighlight, and move to completed (if last episode was played)"""
    episode_ = await get_episode(id=id, episode=episode)
    if not episode_:
        cli.raise_err(ErrorTypes.REQUEST_ERROR, "failed to get episode")
        return

    episode_info, episode_sources = episode_

    try:
        async with Player(cfg.extractor.value.headers) as player:
            await player.play_file(episode_info, episode_sources)

    except (BadResponse, BadHost, SystemError) as ex:
        return cli.raise_err(ErrorTypes.INVALID_RESULT, str(ex))


@cli.on(["p-next", "play-next"], {"id": lambda id: id in range(0, len(ctx))})
async def play_next(id: int):
    """play next episode"""
    if not isinstance(ctx, DataList):
        return cli.raise_err(ErrorTypes.INVALID_CONTEXT)

    object = ctx[id]
    episode = object.continue_from
    episode_ = await get_episode(id=id, episode=episode)
    if not episode_:
        return

    episode_info, episode_sources = episode_

    try:
        async with Player(cfg.extractor.value.headers) as player:
            await player.play_file(episode_info, episode_sources)

    except (BadResponse, BadHost) as ex:
        return cli.raise_err(ErrorTypes.INVALID_RESULT, str(ex))

    else:
        if object.status == "watchlist":
            if object.highlighted:
                object.highlighted = False

            if episode < object.episode_count:
                object.continue_from = episode + 1

            else:
                object.finished_at = int(time.time())
                object.status = "completed"
                object.continue_from = 1

            await data.update(object)


@cli.on(["i"], {"id": lambda id: id in range(0, len(ctx))})
async def info(id: int, keys: list[str] | None = None):
    """show anime info"""
    object = ctx[id]

    def truncate_string(s: str, max_width: int, shift: int) -> str:
        new_str = ""

        for i, c in enumerate(s):
            if i > 0 and i % max_width == 0:
                new_str += "\n" + " " * shift

            new_str += c

        return new_str.strip()

    if isinstance(ctx, SearchList):
        object = await provider.get_anime_info(object.id)

    object_json = object.json()
    keys = keys or list(object_json.keys())
    longest_key = len(max(keys, key=lambda i: len(i)))

    for key in keys:
        value = object_json.get(key, -1)

        if value == -1:
            print(f"'{key}' key not found")
            continue

        if isinstance(value, str):
            value = truncate_string(value, TERM_WIDTH() // 2, longest_key + 3)

        match key:
            case "genres":
                value = ", ".join(value) if isinstance(value, list) else value.replace(",", ", ")

            case "episodes":
                longest_ep_num = get_longest_values(value).get("count", 0)
                value = "".join(f"\n    {ep.num:<{longest_ep_num}} {ep.title}" for ep in value)

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
    if err_message := cfg.update(key, value):
        cli.raise_err(ErrorTypes.INVALID_ARGS, err_message)


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


@cli.on(validate={"id": lambda id: id in range(0, len(ctx))})
async def reset(id: int):
    """reset an anime by putting it back to watchlist from completed (if completed), and setting continue_from to 1"""

    if isinstance(ctx, SearchList):
        return cli.raise_err(ErrorTypes.INVALID_CONTEXT)

    obj = ctx[id]
    obj.continue_from = 1
    obj.status = "watchlist"

    if obj.finished_at:
        obj.finished_at = 0
        obj.added_at = int(time.time())

    await data.update(obj)

@cli.on()
async def refresh():
    """refresh watchlist"""
    await update_watchlist(True)

async def main_():
    global ctx

    await data.load()

    ctx = data.watchlist
    cli.prompt = cfg.prompt.format(ctx.name)
    await update_watchlist(False)

    show_banner()
    await cli.run()


def main():
    asyncio.run(main_())
