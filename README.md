# anipy

A terminal-based anime tracker and player with MyAnimeList sync.

## Features

- Search and stream anime from multiple providers (AllManga, HiAnime, AnimeKai)
- Download episodes as `.mp4` files
- Watchlist management with watchlist, completed, and dropped lists
- MyAnimeList sync — progress, status, and scores update automatically
- Configurable banner showing highlighted anime and continue-watching entries
- Tab completion for commands

## Requirements

- Python 3.12+
- [mpv](https://mpv.io/) — for playback
- [ffmpeg](https://ffmpeg.org/) — for downloading episodes
- A MyAnimeList API app — client ID and secret

## Setup

**1. Install**

```sh
pip install -e .
```

Or with [uv](https://github.com/astral-sh/uv):

```sh
uv sync
```

**2. Set MAL credentials**

Create a MAL API app at https://myanimelist.net/apiconfig and export the credentials:

```sh
export ANIPY_MAL_CLIENT_ID=your_client_id
export ANIPY_MAL_CLIENT_SECRET=your_client_secret
```

**3. Run**

```sh
anipy
```

On first launch, a browser window will open for MAL OAuth. Paste the redirect URL when prompted.

## Commands

| Command | Aliases | Description |
|---|---|---|
| `search <title>` | `s` | Search for anime using the active provider |
| `watchlist [head\|tail\|all] [n]` | `wl` | Show watchlist |
| `completed [head\|tail\|all] [n]` | `comp` | Show completed list |
| `dropped [head\|tail\|all] [n]` | `drop` | Show dropped list |
| `wl-add <id>` | | Add search result to watchlist (syncs to MAL) |
| `wl-rm <id>` | | Remove from watchlist |
| `wl-drop <id>` | | Move to dropped |
| `play <id> <episode>` | `p` | Play a specific episode (does not update progress) |
| `play-next <id>` | `p-next` | Play next episode and update progress |
| `download <id> <episode>` | `d` | Download an episode to the current directory |
| `info <id> [keys]` | `i` | Show anime info from MAL |
| `highlight <id>` | | Mark anime as highlighted |
| `dehighlight <id>` | | Remove highlight |
| `completed-reset <id>` | `comp-res` | Move a completed anime back to watchlist |
| `mal-search <id>` | | Open MAL search in browser |
| `mal-page <id>` | | Open the exact MAL page for an anime |
| `config` | | Show current config |
| `config-get <key>` | | Get a config value |
| `config-set <key> <value>` | | Set a config value |
| `refresh` | | Force-refresh episode counts for airing anime |
| `help` / `h` | | Show all commands |
| `quit` / `q` | | Exit |

Multiple commands can be chained with `;` on one line.

## Configuration

Config is stored at `~/.config/anipy/settings.json`. Use `config-set` to change values at runtime.

| Key | Type | Default | Description |
|---|---|---|---|
| `provider` | string | `allmanga` | Active provider (`allmanga`, `hianime`, `animekai`) |
| `banner` | list | `["continue watching", "highlighted"]` | Sections shown on startup |
| `prompt` | string | `"{} > "` | Shell prompt format (`{}` = current context name) |

## Data

- Config: `~/.config/anipy/`
- Database and tokens: `~/.local/share/anipy/` (Linux/macOS) or `%APPDATA%\anipy\` (Windows)
