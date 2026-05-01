import asyncio
import aiohttp
import os
import re
import shutil
import time
import subprocess
import tempfile
import base64

from typing import Awaitable, Callable

from ..core.types import EpisodeSources
from ..core.exceptions import InvalidResponse, InvalidStatusCode
from ..core.util import get_temp_dir

from .progressbar import ProgressBar
import random


def gen_string(len: int) -> str:
    vals = [random.randint(0, 0xff) for _ in range(len)]
    return "".join(map(lambda i: i.to_bytes(1, "little").hex(), vals))


async def make_request[T](
        session: aiohttp.ClientSession,
        method: str, 
        url: str, 
        headers: dict, 
        handler: Callable[[aiohttp.ClientResponse], Awaitable[T]],
    ) -> T:
    async with session.request(method.upper(), url, headers=headers) as resp:
        if resp.status not in [200, 520]:
            raise InvalidStatusCode(resp.status, resp.url)

        try:
            data = await handler(resp)

        except Exception as e:
            raise InvalidResponse(resp.url, e)
            
        return data

class HLSClient:
    def __init__(self, session: aiohttp.ClientSession, headers: dict) -> None:
        self.headers = headers
        self.session = session

    async def get_master_file(self, master_url: str) -> tuple[str, re.Match]:
        index_pattern = r"#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=\d+,RESOLUTION=(\d+)x(\d+),FRAME-RATE=[\d\.]+,CODECS=\"[\w\.,]+\"\n(.+?)\n"
        master_response = await make_request(self.session, "get", master_url, self.headers, lambda i: i.text())

        vids = re.finditer(index_pattern, master_response)
        if not vids:
            raise InvalidResponse("no index files found")

        sort_by_res = lambda vid: int(vid.group(1)) * int(vid.group(2))
        vid = sorted(vids, key=sort_by_res)[-1]
        return master_response, vid

    async def extract_segments(self, master_url: str) -> list[str]:
        segments_pattern = r"EXTINF:[\d\.]+,\n([^\n]+)"
        segment_urls = []

        base_url = master_url.rsplit("/", 1)[0]

        _, vid = await self.get_master_file(master_url)
        filename = vid.group(3)

        if filename.startswith("https://"):
            index_url = filename
        else:
            index_url = f"{base_url}/{filename}"

        index_file_content = await make_request(self.session, "get", index_url, self.headers, lambda e: e.text())

        for m in re.finditer(segments_pattern, index_file_content):
            segment = m.group(1)

            if segment.startswith("https://"):
                segment_urls.append(segment)
            else:
                segment_urls.append(f"{base_url}/{segment}")

        return segment_urls

class VideoDownloader:
    def __init__(self, session: aiohttp.ClientSession, headers: dict) -> None:
        self.headers = headers
        self.session = session

    def cleanup(self) -> None:
        dir = get_temp_dir()
        for i in os.listdir(dir):
            if re.match(r"seg\d+|index_|master_", i):
                os.remove(os.path.join(dir, i))

    async def _write_segment(self, id: str, url: str, out_dir: str, pb: ProgressBar) -> None:
        pattern = r"seg-(\d+)"
        url_filename = url.rsplit('/', maxsplit=1)[1]

        if url_filename.startswith("c2VnL"):
            url_filename = base64.b64decode(url_filename).decode()

        m = re.search(pattern, url_filename)
        if not m:
            print(url_filename)
            assert m

        filename = f"{id}_seg{m.group(1)}"
        path = os.path.join(out_dir, filename)

        async def _write(resp: aiohttp.ClientResponse):
            with open(path, "wb") as f:
                async for chunk in resp.content.iter_any():
                    f.write(chunk)

        await make_request(self.session, "get", url, self.headers, _write)

        pb.update()

    async def download(self, url: str, output_file: str) -> None:
        hls = HLSClient(self.session, self.headers)
        segments = await hls.extract_segments(url)

        progress = ProgressBar(len(segments), os.path.basename(output_file))

        t = int(time.time() * 1000000)
        val = (t & 0xffffff) + (t >> 32)
        id = hex(val)

        out_dir = get_temp_dir()
        
        tasks = [self._write_segment(id, seg, out_dir, progress) for seg in segments]
        await asyncio.gather(*tasks)

        _, playlist_file = tempfile.mkstemp(dir=out_dir)

        segments = []
        for file in os.listdir(out_dir):
            seg = re.match(rf"({id}_seg\d+)", file)
            if seg:
                abs_path = os.path.join(out_dir, seg.group(1))
                segments.append(abs_path)

        segments = sorted(segments, key=lambda i: int(i.split("seg")[1]))

        with open(playlist_file, "wb") as f:
            for seg in segments:
                with open(seg, "rb") as fseg:
                    f.write(fseg.read())

                os.remove(seg)

        cmd = ["ffmpeg", "-i", playlist_file, "-c:v", "copy", "-c:a", "copy", output_file]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

        os.remove(playlist_file)
        self.cleanup()


class Player:
    def __init__(self, headers: dict) -> None:
        self.player_bin = "mpv"
        self.headers = headers

    async def __aenter__(self):
        self.__connector = aiohttp.TCPConnector(limit=10)
        self.__session = aiohttp.ClientSession(connector=self.__connector)

        return self

    async def __aexit__(self, *_):
        await self.__connector.close()
        await self.__session.close()

    def _play(self, video_file: str, sub_file: str | None) -> None:
        if not shutil.which(self.player_bin):
            raise SystemError(f"'{self.player_bin}' executable not found")

        args = [self.player_bin]

        if sub_file:
            args.append(f"--sub-file={sub_file}")

        user_agent = self.headers.pop("user-agent", "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0")
        args.append(f"--user-agent={user_agent}")
        header_fields = ",".join(f"{k}: {v}" for k, v in self.headers.items())
        args.append(f"--http-header-fields={header_fields}")

        args.append(video_file)
        proc = subprocess.run(args, capture_output=True)
        if proc.returncode != 0:
            raise SystemError(proc.stdout.decode())

    async def download_file(self, ep_sources: EpisodeSources, output_dir: str) -> None:
        filename_base = gen_string(10)
        filename_base = filename_base.replace("'", "\\'")

        master_url = ep_sources.source

        if not shutil.which("ffmpeg"):
            raise SystemError(f"ffmpeg not found")

        video_file = os.path.join(output_dir, f"{filename_base}.mp4")
        downloader = VideoDownloader(self.__session, self.headers)
        await downloader.download(master_url, video_file)


    async def play_file(self, ep_sources: EpisodeSources) -> None:
        master_file = ep_sources.source
        sub_file = next((track["file"] for track in ep_sources.tracks if "default" in track), None)

        self._play(master_file, sub_file)
