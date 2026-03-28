import asyncio
import aiohttp
import os
import re
import shutil
import subprocess
import tempfile

from typing import Awaitable, Callable

from ..core.types import EpisodeInfo, EpisodeSources
from ..core.exceptions import BadResponse, PlaylistError, BadHost
from ..core.util import get_temp_dir

from .progressbar import ProgressBar


class Player:
    def __init__(self, headers: dict) -> None:
        self.player_bin = "mpv"
        self.headers = headers

        self.__main_dir = get_temp_dir()
        self.__progress: ProgressBar

    async def __aenter__(self):
        self.__connector = aiohttp.TCPConnector(limit=10)
        self.__session = aiohttp.ClientSession(connector=self.__connector)

        return self

    async def __aexit__(self, *_):
        await self.__connector.close()
        await self.__session.close()

        # self.clean()

    async def _make_request[T](self, method: str, url: str, func: Callable[[aiohttp.ClientResponse], Awaitable[T]]) -> T:
        print(url)
        try:
            async with self.__session.request(method.upper(), url, headers=self.headers) as resp:
                if resp.status not in [200, 520]:
                    raise BadResponse(f"Response code: {resp.status} ({url})")

                return await func(resp)

        except aiohttp.ClientConnectorCertificateError:
            raise BadHost(url)

    async def _write_segment(self, id: str, url: str) -> None:
        pattern = r"seg-(\d+)"
        m = re.search(pattern, url)

        assert m
        seg_num = m.group(1)
        path = os.path.join(self.__main_dir, f"{id}_seg{seg_num}")

        async def _write(resp: aiohttp.ClientResponse):
            with open(path, "wb") as f:
                async for chunk in resp.content.iter_any():
                    f.write(chunk)

        await self._make_request("get", url, _write)

        self.__progress.update()

    async def _get_master_file(self, master_url: str) -> tuple[str, re.Match]:
        index_pattern = r"#EXT-X-STREAM-INF:PROGRAM-ID=\d+,BANDWIDTH=\d+,RESOLUTION=(\d+)x(\d+),FRAME-RATE=[\d\.]+,CODECS=\"[\w\.,]+\"\n(.+?)\n"
        master_response = await self._make_request("get", master_url, lambda i: i.text())

        vids = re.finditer(index_pattern, master_response)
        if not vids:
            raise PlaylistError("no index files found")

        sort_by_res = lambda vid: int(vid.group(1)) * int(vid.group(2))
        vid = sorted(vids, key=sort_by_res)[-1]
        return master_response, vid

    async def _extract_segments(self, master_url: str) -> list[str]:
        segments_pattern = r"EXTINF:[\d\.]+,\n(.*?(seg[\w\-\.]+))"
        segment_urls = []

        base_url = master_url.rsplit("/", 1)[0]

        _, vid = await self._get_master_file(master_url)
        filename = vid.group(3)

        index_url = f"{base_url}/{filename}"
        index_file_content = await self._make_request("get", index_url, lambda e: e.text())

        for m in re.finditer(segments_pattern, index_file_content):
            full_url = m.group(1)
            segment = m.group(2)

            if len(full_url) < 285:
                segment_urls.append(f"{base_url}/{segment}")

            else:
                segment_urls.append(full_url)

        return segment_urls

    async def _download(self, url: str, output_file: str, ep_info: EpisodeInfo) -> None:
        segments = await self._extract_segments(url)

        title = f"{ep_info.num} {ep_info.title}"
        self.__progress = ProgressBar(len(segments), title)

        tasks = [self._write_segment(ep_info.id, seg) for seg in segments]
        await asyncio.gather(*tasks)

        _, playlist_file = tempfile.mkstemp(dir=self.__main_dir)

        segments = []
        for file in os.listdir(self.__main_dir):
            seg = re.match(rf"({ep_info.id}_seg\d+)", file)
            if seg:
                abs_path = os.path.join(self.__main_dir, seg.group(1))
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
        # args.append("--http-proxy=http://127.0.0.1:8080")

        args.append(video_file)
        subprocess.run(args, stdout=subprocess.DEVNULL)

    def generate_filename(self, ep_info: EpisodeInfo) -> str:
        title = re.sub(r"\W", "", ep_info.title)
        return f"{title}_{ep_info.num}"

    async def download_file(self, ep_info: EpisodeInfo, ep_sources: EpisodeSources, output_dir: str) -> None:
        filename_base = self.generate_filename(ep_info)
        filename_base = filename_base.replace("'", "\\'")

        master_url = ep_sources.sources[0]["file"]

        if not shutil.which("ffmpeg"):
            raise SystemError(f"ffmpeg not found")

        video_file = os.path.join(output_dir, f"{filename_base}.mp4")
        await self._download(master_url, video_file, ep_info)


    async def play_file(self, ep_info: EpisodeInfo, ep_sources: EpisodeSources) -> None:
        print(f"{ep_info.num} {ep_info.title}")

        filename_base = self.generate_filename(ep_info)
        filename_base = filename_base.replace("'", "\\'")

        master_file = ep_sources.sources[0]["file"]
        sub_file = next((track["file"] for track in ep_sources.tracks if "default" in track), None)

        self._play(master_file, sub_file)

    def clean(self) -> None:
        for i in os.listdir(self.__main_dir):
            if re.match(r"seg\d+|index_|master_", i):
                os.remove(os.path.join(self.__main_dir, i))
