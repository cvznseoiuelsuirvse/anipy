from ..core.data import LocalDB
from ..core.util import resolve_to_mal
import asyncio
import re

db = LocalDB()

async def main():
    for d in db.pull():
        if d.status != 'watchlist':
            num_id = d.id.split('-')[-1]
            mal_url = await resolve_to_mal(d.title, d.other_title)
            if not mal_url:
                print(f"can't get mal url for {d.id}")

            else:
                m = re.search(r"/(\d+)/", mal_url)
                assert m
                print(f"{num_id:<7} {m.group(1):<7} {d.title}")

asyncio.run(main())
