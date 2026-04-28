import aiohttp
import webbrowser
import json
import time
import os
import asyncio
import secrets
import re
import urllib.parse
from typing import Awaitable, Callable, TypedDict
from functools import wraps
from dataclasses import dataclass
from enum import StrEnum

from ..core.data import get_user_data_dir
from ..core.exceptions import BadResponse

BASE_API_URL = "https://api.myanimelist.net/v2"

def construct_url(url: str, params: dict[str, str]) -> str:
    for i, (k, v) in enumerate(params.items()):
        if i == 0:
            url += f"?{k}={v}"
        else:
            url += f"&{k}={v}"

    return url

async def make_request[T](
    method: str, 
    url: str, 
    *, 
    headers: dict | None = None, 
    params: dict | None = None, 
    data: dict | None = None, 
    func: Callable[[aiohttp.ClientResponse], Awaitable[T]]
) -> tuple[int, T]:
    async with aiohttp.ClientSession() as client:
        async with client.request(method, url, headers=headers, params=params, data=data) as resp:
            return resp.status, await func(resp)

class MALAnimeAlternativeTitles(TypedDict):
    synonyms: list[str]
    en: str
    jp: str


@dataclass
class MALSearchObject:
    id:                 str
    title:              str
    alternative_titles: MALAnimeAlternativeTitles

@dataclass
class MALAnimeInfo:
    id:             str
    title:          str
    other_title:    str


class MALListStatuses(StrEnum):
    WATCHING      = "watching"
    COMPLETED     = "completed"
    ON_HOLD       = "on_hold"
    DROPPED       = "dropped"
    PLAN_TO_WATCH = "plan_to_watch"

@dataclass 
class MALListItem(MALAnimeInfo):
    status: MALListStatuses


class MAL:
    def __init__(self) -> None:
        self.__client_id = os.getenv("ANIPY_MAL_CLIENT_ID")
        self.__client_secret = os.getenv("ANIPY_MAL_CLIENT_SECRET")

        if self.__client_id is None or self.__client_secret is None:
            raise SystemError("ANIPY_MAL_CLIENT_ID or ANIPY_MAL_CLIENT_SECRET not set")

        self.__token_file_path = os.path.join(get_user_data_dir(), "mal.json")
        self.__token: str | None = None

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

        status, resp = await make_request("POST", token_url, data=token_data, func=lambda r: r.json())
        if status != 200:
            raise BadResponse(status)

        if 'error' in resp:
            raise BadResponse(resp['error'], resp['hint'])

        self._save_token(resp)
        self.__token = resp['access_token']

        assert resp['token_type'] == "Bearer"

    @_check_token
    async def search(self, title: str) -> list[MALSearchObject]:
        url = BASE_API_URL + "/anime"
        params = {
            "q": urllib.parse.quote(title),
            "limit": 100,
            "fields": "alternative_titles"
        }
        headers = {"Authorization": f"Bearer {self.__token}"}

        status, resp = await make_request("GET", url, headers=headers, params=params, func=lambda r: r.json())
        if status != 200:
            raise BadResponse(status, resp)

        data = resp['data']

        l = []
        for d in data:
            node = d['node']
            l.append(MALSearchObject(
                node['id'], 
                node['title'], 
                node['alternative_titles'])
            )

        return l

    @_check_token
    async def get_anime(self, str: int) -> MALAnimeInfo: ...

    @_check_token
    async def list_add(self, id: str, ep_count: int, list_status: MALListStatuses) -> None:
        url = f'https://api.myanimelist.net/v2/anime/{id}/my_list_status'
        data = {
            "status": list_status,
            "num_watched_episodes": ep_count,
        }
        headers = {"Authorization": f"Bearer {self.__token}"}

        if list_status == MALListStatuses.COMPLETED:
            data['score'] = 10

        elif list_status == MALListStatuses.DROPPED:
            data['score'] = 1

        status, resp = await make_request("PUT", url, headers=headers, data=data, func=lambda r: r.json())
        if status != 200:
            raise BadResponse(status, resp)


    @_check_token
    async def list_remove(self, id: str) -> None:
        url = f'https://api.myanimelist.net/v2/anime/{id}/my_list_status'
        headers = {"Authorization": f"Bearer {self.__token}"}

        status, resp = await make_request("DELETE", url, headers=headers, func=lambda r: r.json())
        if status != 200:
            raise BadResponse(status, resp)


    @_check_token
    async def list_get(self, list_status: MALListStatuses | None = None, offset: int = 0) -> list[MALListItem]:
        url = 'https://api.myanimelist.net/v2/users/@me/animelist'
        params: dict = {
            "limit": 1000,
            "offset": offset,
        }

        if list_status is not None:
            params['status'] = list_status
            
        headers = {"Authorization": f"Bearer {self.__token}"}

        status, resp = await make_request("GET", url, headers=headers, params=params, func=lambda r: r.json())
        if status != 200:
            raise BadResponse(status, resp)

        data = resp['data']

        l = []
        for d in data:
            node = d['node']
            st = MALListStatuses(d['list_status']['status'])
            l.append(MALListItem(
                node['id'], 
                node['title'], 
                node['alternative_titles'].get('en', ""), 
                st)
             )

        return l

if __name__ == "__main__":
    async def main():
        a = MAL()
        await a.get_token()
        res = await a.search("rent a girlfriend")
        for l in res:
            print(l)

    asyncio.run(main())


