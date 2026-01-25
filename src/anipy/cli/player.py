import asyncio
import shlex
import aiohttp
import os
import re
import shutil
import subprocess
import tempfile
import http.server
import threading

from io import TextIOWrapper
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Any

from ..core.types import EpisodeInfo, EpisodeSources
from ..core.exceptions import BadResponse, PlaylistError, BadHost
from ..core.util import get_main_dir

from .progressbar import ProgressBar


def _remove_intro_outro_ffmpeg(output_file: str, intro: tuple[int, int], outro: tuple[int, int]) -> None:
    files = []

    intro_s, intro_e = intro
    outro_s, outro_e = outro

    _, filename = tempfile.mkstemp()
    file_list_txt = os.path.join(get_main_dir(), filename)

    concat_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", file_list_txt, "-c", "copy", output_file]
    cut_cmd = [
        "ffmpeg",
        "-ss",
        "",  # 2
        "-to",
        "",  # 4
        "-i",
        output_file,
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "",  # -1
    ]

    # cut pre-intro
    if intro_s:
        _, filename = tempfile.mkstemp(".mp4")
        files.append(filename)

        intro_s_fmted = timedelta(seconds=intro_s)

        cut_cmd[2] = "00:00:00"
        cut_cmd[4] = str(intro_s_fmted)
        cut_cmd[-1] = filename

        subprocess.run(
            cut_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )

    # cut post-intro
    _, filename = tempfile.mkstemp(".mp4")
    files.append(filename)

    intro_e_fmted = timedelta(seconds=intro_e)
    outro_s_fmted = "10:00:00"

    if outro_s:
        outro_s_fmted = timedelta(seconds=outro_s)

    cut_cmd[2] = str(intro_e_fmted)
    cut_cmd[4] = str(outro_s_fmted)
    cut_cmd[-1] = filename

    subprocess.run(
        cut_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    # cut post-outro
    if outro_e:
        _, filename = tempfile.mkstemp(".mp4")
        files.append(filename)

        outro_e_fmted = timedelta(seconds=outro_e)

        cut_cmd[2] = str(outro_e_fmted)
        cut_cmd[4] = str(outro_s_fmted)
        cut_cmd[-1] = filename

        subprocess.run(
            cut_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )

    with open(file_list_txt, "w") as f:
        for file in files:
            f.write(f"file {file}\n")

    subprocess.run(
        concat_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    for file in files:
        os.remove(file)

    os.remove(file_list_txt)


def _remove_intro_outro(content: str, output_file: TextIOWrapper, intro: tuple[int, int], outro: tuple[int, int]) -> None:
    """
    remove intro/outro segments from index file and write to a new file
    return new intro/outro time range (for sub shifting)
    """

    pattern = r"EXTINF:([\d\.]+),\s+([^\n]+)"
    to_remove = "#EXTINF:{},\n{}\n"

    intro_start, intro_end = intro
    outro_start, outro_end = outro

    total_duration = 0.0

    for seg in re.finditer(pattern, content):
        duration = seg.group(1)
        f_duration = float(duration)
        url = seg.group(2)

        if (intro_start < total_duration <= intro_end) or (outro_start < total_duration <= outro_end):
            content = content.replace(to_remove.format(duration, url), "")

        total_duration += f_duration

    output_file.write(content)


def _shift_subs(content: str, sub_file: TextIOWrapper, intro: tuple[float, float], outro: tuple[float, float]) -> None:
    content += "\n"
    pattern = r"(((?:\d{2}:)?\d{2}:\d{2}\.\d{3}) --> ((?:\d{2}:)?\d{2}:\d{2}\.\d{3})\n([\s\S]*?)\n\n)"
    to_replace = "{} --> {}\n{}\n\n"
    time_format: str

    intro_start, intro_end = intro
    outro_start, outro_end = outro

    intro_len_dt = timedelta(seconds=intro_end - intro_start)
    outro_len_dt = timedelta(seconds=outro_end - outro_start)

    def get_seconds(dt: datetime) -> float:
        return dt.hour * 3600 + dt.minute * 60 + dt.second + dt.microsecond / 1000000.0

    def get_string(dt: datetime) -> str:
        return dt.strftime(time_format)[:-3]

    for m in re.finditer(pattern, content):
        full_sub = m.group(1)
        start = m.group(2)
        end = m.group(3)
        text = m.group(4)

        time_format = "%H:%M:%S.%f" if len(start) == 2 * 3 + 3 + 3 else "%M:%S.%f"

        start_dt = datetime.strptime(start + "000", time_format)
        end_dt = datetime.strptime(end + "000", time_format)

        start_seconds = get_seconds(start_dt)

        if intro_start <= start_seconds and start_seconds <= intro_end or outro_start <= start_seconds and start_seconds <= outro_end:
            content = content.replace(full_sub, "")
            continue

        if intro_end <= start_seconds and start_seconds <= outro_start:
            start_dt -= intro_len_dt
            end_dt -= intro_len_dt

        elif outro_end <= start_seconds:
            start_dt -= outro_len_dt
            end_dt -= outro_len_dt

        start = get_string(start_dt)
        end = get_string(end_dt)

        content = content.replace(full_sub, to_replace.format(start, end, text))

    sub_file.write(content)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return


class Player:
    def __init__(self, player_bin: str, headers: dict) -> None:
        self.__player_bin = player_bin
        self.headers = headers

        self.__main_dir = get_main_dir()

        self.__progress: ProgressBar
        self.__socket = ("", 8842)
        self.__server: http.server.HTTPServer
        self.__server_thread = None

    async def __aenter__(self):
        self.__connector = aiohttp.TCPConnector(limit=10)
        self.__session = aiohttp.ClientSession(connector=self.__connector)

        return self

    async def __aexit__(self, *_):
        await self.__connector.close()
        await self.__session.close()

        # self.clean()

    async def _make_request[T](self, method: str, url: str, func: Callable[[aiohttp.ClientResponse], Awaitable[T]]) -> T:
        try:
            async with self.__session.request(method.upper(), url, headers=self.headers) as resp:
                if resp.status not in [200, 520]:
                    if self.__server_thread:
                        self.__server.shutdown()
                        self.__server.server_close()
                        self.__server_thread.join()

                    raise BadResponse(f"Response code: {resp.status} ({url})")

                return await func(resp)

        except aiohttp.ClientConnectorCertificateError:
            if self.__server_thread:
                self.__server.shutdown()
                self.__server.server_close()
                self.__server_thread.join()

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

    async def _modify_playlist(self, master_url: str, master_output_file: str, index_output_file: str, ep_sources: EpisodeSources, cut: bool) -> None:
        base_url = master_url.rsplit("/", 1)[0]
        master_file_content, vid = await self._get_master_file(master_url)
        filename = vid.group(3)

        index_url = f"{base_url}/{filename}"

        index_file_content = await self._make_request("get", index_url, lambda r: r.text())
        index_file_content = re.sub(r"#EXT-X-MEDIA-SEQUENCE:\d+", "#EXT-X-MEDIA-SEQUENCE:0", index_file_content)

        if cut:
            with open(index_output_file, "w") as f:
                _remove_intro_outro(index_file_content, f, ep_sources.intro, ep_sources.outro)

        master_file_content = master_file_content.replace(filename, os.path.basename(index_output_file))
        with open(master_output_file, "w") as f:
            f.write(master_file_content)

    def _play(self, video_file: str, sub_file: str, downloaded: bool) -> None:
        if not shutil.which(self.__player_bin):
            raise SystemError(f"'{self.__player_bin}' executable not found")

            # command = [self.__player_bin, video_file, f"--sub-file={sub_file}"]
            #
            # if self.__player_bin == "mpv":
            #     header_fields = ",".join(f"'{k}: {v}'" for k, v in self.headers.items())
            #     command.append(f"--http-header-fields={header_fields}")
            #
            # print(command)
            # if not downloaded:
            #     handler = lambda *args, **kwargs: Handler(*args, directory=self.__main_dir, **kwargs)
            #     self.__server = http.server.HTTPServer(self.__socket, handler)
            #     self.__server_thread = threading.Thread(target=self.__server.serve_forever)
            #     self.__server_thread.start()
            #
            #     subprocess.run(command)
            #     # proc = subprocess.run(command, capture_output=True)
            #     # if proc.returncode != 0:
            #     #     print(f"{self.__player_bin}: {proc.stdout.decode()}")
            #
            #     self.__server.shutdown()
            #     self.__server.server_close()
            #     self.__server_thread.join()
            #
            # else:
            #     subprocess.run(command, stdout=subprocess.DEVNULL)

        command = f"{self.__player_bin} {video_file}"

        if sub_file:
            command += f" --sub-file={sub_file}"

        if self.__player_bin == "mpv":
            header_fields = ",".join(f"'{k}: {v}'" for k, v in self.headers.items())
            command += f" --http-header-fields={header_fields}"

        if not downloaded:
            handler = lambda *args, **kwargs: Handler(*args, directory=self.__main_dir, **kwargs)
            self.__server = http.server.HTTPServer(self.__socket, handler)
            self.__server_thread = threading.Thread(target=self.__server.serve_forever)
            self.__server_thread.start()

            proc = subprocess.run(shlex.split(command), capture_output=True)
            if proc.returncode != 0:
                print(f"{self.__player_bin}: {proc.stdout.decode()}")

            self.__server.shutdown()
            self.__server.server_close()
            self.__server_thread.join()

        else:
            subprocess.run(shlex.split(command), stdout=subprocess.DEVNULL)

    def generate_filename(self, ep_info: EpisodeInfo) -> str:
        title = re.sub(r"\W", "", ep_info.title)
        return f"{title}_{ep_info.num}"

    async def get_file(self, ep_info: EpisodeInfo, ep_sources: EpisodeSources, *, play: bool, download: bool, cut: bool) -> None:
        filename_base = self.generate_filename(ep_info)
        filename_base = filename_base.replace("'", "\\'")

        intro = ep_sources.intro
        outro = ep_sources.outro

        master_url = ep_sources.sources[0]["file"]

        if download:
            if not shutil.which("ffmpeg"):
                raise SystemError(f"ffmpeg not found")

            video_file = os.path.join(self.__main_dir, f"{filename_base}.mp4")
            await self._download(master_url, video_file, ep_info)

            if cut:
                _remove_intro_outro_ffmpeg(video_file, intro, outro)

            file = video_file

        else:
            master_file = os.path.join(self.__main_dir, f"master_{filename_base}.m3u8")

            # if not os.path.exists(master_file):
            index_file = os.path.join(self.__main_dir, f"index_{filename_base}.m3u8")
            await self._modify_playlist(master_url, master_file, index_file, ep_sources, cut)

            file = f"http://localhost:{self.__socket[1]}/{os.path.basename(master_file)}"
            print(f"{ep_info.num} {ep_info.title}")

        sub_file_url = next((track["file"] for track in ep_sources.tracks if "default" in track))
        sub_file = os.path.join(self.__main_dir, f"{filename_base}.vtt")

        if download and cut:
            sub_file_content = await self._make_request("get", sub_file_url, lambda r: r.text())

            with open(sub_file, "w") as f:
                _shift_subs(sub_file_content, f, intro, outro)

            sub_file = sub_file

        else:
            sub_file = sub_file_url

        if play:
            self._play(file, sub_file, download)

    def clean(self) -> None:
        for i in os.listdir(self.__main_dir):
            if re.match(r"seg\d+|index_|master_", i):
                os.remove(os.path.join(self.__main_dir, i))
