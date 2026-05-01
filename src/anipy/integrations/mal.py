import aiohttp
import webbrowser
import json
import time
import os
import asyncio
import secrets
import re
import urllib.parse
from functools import wraps
from dataclasses import dataclass
from enum import StrEnum

from ..core.data import get_user_data_dir
from ..core.exceptions import InvalidResponse, InvalidStatusCode
from ..core.types import AnimeInfo, SearchObject

BASE_API_URL = "https://api.myanimelist.net/v2"

def construct_url(url: str, params: dict[str, str]) -> str:
    for i, (k, v) in enumerate(params.items()):
        if i == 0:
            url += f"?{k}={v}"
        else:
            url += f"&{k}={v}"

    return url


class MALListStatuses(StrEnum):
    WATCHING      = "watching"
    COMPLETED     = "completed"
    ON_HOLD       = "on_hold"
    DROPPED       = "dropped"
    PLAN_TO_WATCH = "plan_to_watch"

@dataclass
class MALListStatus:
    status:                 MALListStatuses
    score:                  int
    num_episodes_watched:   int

@dataclass 
class MALAnimeInfo:
    info: AnimeInfo
    list_status: MALListStatus | None

def extract_base(node: dict) -> dict:
    description = node.get('synopsis', "None")
    description = re.sub(r"\s+", " ", description)

    start_season = node.get("start_season")
    if start_season:
        year = start_season['year']
    else:
        year = 0

    genres = [g["name"] for g in node["genres"]]
    status = node["status"]

    if status in ("currently_airing", "not_yet_aired"):
        status = "airing"

    else:
        status = "finished"

    media_type = node['media_type']
    if media_type == "tv":
        media_type = "TV"
    else:
        media_type = media_type.title()

    episode_count = node['num_episodes']
    episode_duration = node['average_episode_duration'] * 1000

    ret = {
        "mal_id":           node['id'],
        "external_id":      node['id'],
        "title":            node['alternative_titles'].get('en', node['title']), 
        "other_title":      node['title'], 
        "description":      description,
        "year":             year,
        "genres":           genres,
        "airing_status":    status,
        "type":             media_type,
        "episode_count":    episode_count,
        "episode_duration": episode_duration,
    }
    if node.get("my_list_status"):
        my_list_status = node['my_list_status']
        ret["my_list_status"] = {
            "status": my_list_status["status"],
            "score":  my_list_status["score"],
            "num_episodes_watched": my_list_status["num_episodes_watched"],
        }

    return ret



def info_dict_to_cls(node: dict) -> MALAnimeInfo:
    base = extract_base(node)

    if base.get('my_list_status'):
        st = MALListStatus(**base.pop("my_list_status"))

    else:
        st = None

    return MALAnimeInfo(**base, list_status=st)

class MAL:
    def __init__(self) -> None:
        self.__client_id = os.getenv("ANIPY_MAL_CLIENT_ID")
        self.__client_secret = os.getenv("ANIPY_MAL_CLIENT_SECRET")

        if self.__client_id is None or self.__client_secret is None:
            raise SystemError("ANIPY_MAL_CLIENT_ID or ANIPY_MAL_CLIENT_SECRET not set")

        self.__token_file_path = os.path.join(get_user_data_dir(), "mal.json")
        self.__token: str | None = None

    async def make_request(
        self,
        method: str, 
        url: str, 
        *, 
        params: dict | None = None, 
        data: dict | None = None, 
    ) -> dict:
        headers = {"Authorization": f"Bearer {self.__token}"}

        async with aiohttp.ClientSession() as client:
            async with client.request(method, url, headers=headers, params=params, data=data) as resp:
                j = await resp.json()
                if resp.status != 200:
                    raise InvalidStatusCode(resp.status, j)

                return j

    @staticmethod
    def _check_token(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if self.__token is None:
                raise ValueError("token is empty. call MAL.get_token() first")
            return func(self, *args, **kwargs)
        return wrapper

    def _save_token(self, d: dict) -> None:
        with open(self.__token_file_path, "w") as f:
            d['expires_at'] = int(time.time()) + d['expires_in']
            json.dump(d, f)

    async def get_token(self) -> None:
        if os.path.exists(self.__token_file_path):
            with open(self.__token_file_path, "r") as f:
                data = json.load(f)

                if int(time.time()) < data['expires_at']:
                    self.__token = data['access_token']
                    return

        auth_url =  "https://myanimelist.net/v1/oauth2/authorize"
        token_url = "https://myanimelist.net/v1/oauth2/token"

        challenge = secrets.token_hex(32)
        auth_params = {
            "response_type": "code",
            "client_id": self.__client_id,
            "state": secrets.token_hex(16),
            "code_challenge": challenge,
            "code_challenge_method": "plain",
        }

        auth_u = construct_url(auth_url, auth_params)
        webbrowser.open(auth_u)
        redirected_url = input("[MAL] redirected url: ")

        m = re.search(r"\?code=([a-f0-9]+)&", redirected_url)
        if not m:
            raise ValueError("redirected url doesn't contain code param")

        code = m.group(1)
        token_data = {
            "client_id": self.__client_id,
            "client_secret": self.__client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": challenge,
        }

        resp = await self.make_request("POST", token_url, data=token_data)

        if 'error' in resp:
            raise InvalidResponse(resp['error'], resp['hint'])

        self._save_token(resp)
        self.__token = resp['access_token']

        assert resp['token_type'] == "Bearer"


    @_check_token
    async def search(self, title: str) -> list[SearchObject]:
        url = BASE_API_URL + "/anime"
        params = {
            "q": urllib.parse.quote(title),
            "limit": 100,
            "fields": "alternative_titles,num_episodes,average_episode_duration,media_type"
        }

        resp = await self.make_request("GET", url, params=params)
        data = resp['data']

        l = []
        for d in data:
            node = d['node']
            l.append(
                SearchObject(
                    node['id'], 
                    node['alternative_titles']['en'],
                    node['title'], 
                    node['num_episodes'],
                    node['average_episode_duration'] * 1000,
                    "TV" if node['media_type'] == "tv" else node['media_type'].title(),
                )
            )

        return l

    @_check_token
    async def get_anime(self, id: str) -> AnimeInfo:
        url = f"{BASE_API_URL}/anime/{id}"
        params = {
            "fields": "alternative_titles,synopsis,genres,average_episode_duration,media_type,status,my_list_status,num_episodes,start_season"
        }

        resp = await self.make_request("GET", url, params=params)
        return info_dict_to_cls(resp).info


    @_check_token
    async def list_add(self, id: str, ep_count: int, list_status: MALListStatuses) -> None:
        url = f'{BASE_API_URL}/anime/{id}/my_list_status'
        data = {
            "status": list_status,
            "num_watched_episodes": ep_count,
        }
        if list_status == MALListStatuses.COMPLETED:
            data['score'] = 10

        elif list_status == MALListStatuses.DROPPED:
            data['score'] = 1

        await self.make_request("PUT", url, data=data)

    @_check_token
    async def list_remove(self, id: str) -> None:
        url = f'{BASE_API_URL}/anime/{id}/my_list_status'
        await self.make_request("DELETE", url)

    @_check_token
    async def list_get(self, list_status: MALListStatuses | None = None, offset: int = 0) -> list[MALAnimeInfo]:
        url = f'{BASE_API_URL}/users/@me/animelist'
        params: dict = {
            "limit": 1000,
            "offset": offset,
            "fields": "alternative_titles,synopsis,genres,average_episode_duration,media_type,status,my_list_status,num_episodes,start_season",
        }

        if list_status is not None:
            params['status'] = list_status

        resp = await self.make_request("GET", url, params=params)
        data = resp['data']

        l = []
        for d in data:
            l.append(info_dict_to_cls(d['node']))

        return l

if __name__ == "__main__":
    async def main():
        a = MAL()
        await a.get_token()
        res = await a.search("rent a girlfriend")
        for l in res:
            print(l)

    asyncio.run(main())


