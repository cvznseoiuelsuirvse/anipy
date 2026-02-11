import time
import socket
import re
import aiohttp

from typing import Callable, Awaitable

from flask import Flask, Response, jsonify, render_template, request
from flask_cors import CORS

from ..core.util import resolve_to_mal

from ..providers.hianime import HiAnimeAPI
from ..core.data import Data
from ..core.types import DataObject

app = Flask(__name__, template_folder="templates", static_folder="static")
cors = CORS(app, resources={"/api/*": {"origins": "*"}})

data = Data()
data_loaded = False
api = HiAnimeAPI()

episodes = {
    "asdf": {
        "sources": None,
        "master": "",
        "segment": "",
    }
}


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    return ip


DELIM = "$"
IPADDR = get_local_ip()
PORT = 5001


async def make_request[T](url: str, headers: dict, params: dict, func: Callable[[aiohttp.ClientResponse], Awaitable[T]]) -> T:
    async with aiohttp.ClientSession() as client:
        async with client.get(url, headers=headers, params=params) as resp:
            return await func(resp)


async def watchlist_add(object: dict) -> None:
    obj_info = await api.get_anime_info(object["id"])

    object["url"] = obj_info.url
    object["year"] = obj_info.year
    object["added_at"] = int(time.time())
    object["description"] = obj_info.description
    object["genres"] = ",".join(obj_info.genres)
    object["status"] = "watchlist"

    new_obj = DataObject(object)
    await data.add(new_obj)


async def watchlist_remove(object: dict) -> None:
    obj = next((o for o in data.watchlist if o.id == object["id"]))
    await data.remove(obj)


async def watchlist_update(object: dict) -> None:
    for o in data.watchlist:
        if o.id == object["id"]:
            for k, v in vars(o).items():
                if not k.startswith("_") and object[k] != v:
                    setattr(o, k, object[k])

            await data.update(o)


@app.before_request
async def startup():
    global data_loaded
    if not data_loaded:
        await data.load()
        data_loaded = True


@app.route("/", methods=["GET"])
async def index():
    return render_template("watchlist.html")
    # return render_template("search.html")


@app.route("/search", methods=["GET"])
async def search():
    return render_template("search.html")


@app.route("/watchlist", methods=["GET"])
async def watchlist():
    return render_template("watchlist.html")


@app.route("/completed", methods=["GET"])
async def completed():
    return render_template("completed.html")


@app.route("/watch/<path:path>", methods=["GET"])
async def watch(path):
    print(request.referrer)
    return render_template("watch.html")


@app.route("/api/datalist", methods=["GET"])
async def datalist():
    filter = request.args["filter"]
    match filter:
        case "watchlist":
            return jsonify([o.json() for o in data.watchlist])

        case "completed":
            return jsonify([o.json() for o in data.completed])

        case _:
            return jsonify([])


@app.route("/api/datalist/modify", methods=["POST"])
async def datalist_modify():
    body = request.json
    assert body

    filter = body["filter"]
    action = body["action"]
    object = body["object"]

    try:
        if filter == "watchlist":
            match action:
                case "add":
                    await watchlist_add(object)

                case "remove":
                    await watchlist_remove(object)

                case "update":
                    await watchlist_update(object)

    except Exception as e:
        print(e)
        return Response(str(e), 500)

    return Response(status=200)


@app.route("/api/get_anime_info", methods=["GET"])
async def get_anime_info():
    anime_id = request.args["id"]
    info = await api.get_anime_info(anime_id)
    return jsonify(info.json())


@app.route("/api/get_episode_sources", methods=["GET"])
async def get_episode_sources():
    ep_id = request.args["id"]
    version = request.args["version"]
    unique_id = DELIM.join([ep_id, version])

    ep_sources = await api.get_episode_sources(ep_id, data.config.extractor, data.config.server)

    master_base_url = ep_sources.sources[0]["file"].rsplit("/", maxsplit=1)[0]
    episodes[unique_id] = {
        "master": master_base_url,
    }

    return jsonify(ep_sources)


@app.route("/api/sources/<ep_id>/<version>/master.m3u8", methods=["GET"])
async def master_m3u8(ep_id, version):
    unique_id = DELIM.join([ep_id, version])

    ep = episodes[unique_id]
    url = ep["master"] + "/master_m3u8"

    headers = data.config.extractor.value.headers
    resp = await make_request(url, headers, {}, lambda i: i.text())

    return Response(resp, 200)


@app.route("/api/sources/<ep_id>/<version>/index-<name>", methods=["GET"])
async def index_m3u8(ep_id, version, name):
    unique_id = DELIM.join([ep_id, version])

    ep = episodes[unique_id]
    master_url = ep["master"] + f"/index-{name}"

    headers = data.config.extractor.value.headers
    resp = await make_request(master_url, headers, {}, lambda i: i.text())

    segment_base_url = re.search(r"(https:\/\/[\w\.]+\/\w+\/\w+)", resp)
    if not segment_base_url:
        return Response("segment urls not found", 500)

    segment_base_url = segment_base_url.group(1)
    ep["segment"] = segment_base_url

    pattern = rf"{segment_base_url}/seg-(.+)"
    resp = re.sub(pattern, rf"http://{IPADDR}:{PORT}/api/sources/{ep_id}/{version}/seg-\1", resp)

    return Response(resp, 200)


@app.route("/api/sources/<ep_id>/<version>/seg-<segment>", methods=["GET"])
async def segment(ep_id, version, segment):
    unique_id = DELIM.join([ep_id, version])

    ep = episodes[unique_id]
    segment_url = ep["segment"] + f"/seg-{segment}"

    headers = data.config.extractor.value.headers
    resp = await make_request(segment_url, headers, {}, lambda i: i.read())

    return Response(resp, 200)


@app.route("/api/search", methods=["GET"])
async def api_search():
    query = request.args["query"]
    resp = await api.search(query)
    return jsonify([o.json() for o in resp])


@app.route("/api/get_mal_page", methods=["GET"])
async def get_mal_page():
    title = request.args["title"]
    other_title = request.args["other_title"]

    url = await resolve_to_mal(title, other_title)
    return jsonify({"url": url})


def main():
    app.run(debug=True, host=IPADDR, port=PORT)
