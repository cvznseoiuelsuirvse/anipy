import asyncio
import aiohttp


class DiscordAPI:
    VERSION = "v9"
    BASE_URL = f"https://discord.com/api/{VERSION}/"

    def __init__(self, token: str) -> None:
        self.__token = token

    async def _req(self, method: str, route: str, *, json: dict | None = None, params: dict | None = None) -> tuple[int, dict]:
        headers = {"Authorization": self.__token}
        async with aiohttp.ClientSession() as session:
            async with session.request(method, f"{self.BASE_URL}/{route}", headers=headers, params=params, json=json) as resp:
                return resp.status, await resp.json()

    async def get_channel(self, channel_id: str) -> dict:
        code, resp = await self._req("GET", f"channels/{channel_id}")

        assert code == 200  # FIXME
        return resp

    async def modify_channel(self, channel_id: str, data: dict) -> dict:
        code, resp = await self._req("PATCH", f"channels/{channel_id}", json=data)

        assert code == 200  # FIXME
        return resp

    async def get_channel_messages_full(self, channel_id: str, pages: list[str]) -> list[dict]:
        messages: list[dict] = []
        route = f"channels/{channel_id}/messages"

        if not pages:
            resp = []
            while len(resp) == 100 or not resp:
                code, resp = await self._req(
                    "GET",
                    route,
                    params={"limit": 100, "before": messages[-1]["id"]} if messages else {"limit": 100},
                )
                assert code == 200  # FIXME
                messages.extend(resp)

        else:
            tasks = [self._req("GET", route, params={"limit": 100, "before": p} if p != "0" else {"limit": 100}) for p in pages]
            resps = await asyncio.gather(*tasks)

            for code, resp in resps:
                assert code == 200
                messages.extend(resp)

        return messages
