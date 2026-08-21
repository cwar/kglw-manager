# KGLW Manager

A collection management tool for King Gizzard & The Lizard Wizard concert
recordings: scans a local library, analyses video quality, finds better copies
on YouTube, and keeps everything named and organised for Plex.

## Features

- **Collection scanning** — walks a tour/show directory tree with two-tier
  caching (per-show and per-collection) so repeat scans are fast
- **Quality analysis** — ffprobe-backed resolution/duration/codec detection,
  cached by file signature
- **Upgrade discovery** — finds better sources, ranking the official KGLW
  channel above known high-quality uploaders above everything else
- **Curated links** — reads the community live-show spreadsheet for
  hand-picked recordings
- **kglw.net API** — pulls tours, setlists, show notes and poster art
- **Plex integration** — Plex-compatible naming, collections, metadata and
  poster upload
- **Interactive TUI** — browse by year/tour, search, and run upgrades
- **Discord notifications** — optional webhooks for new shows and upgrades

## Installation

Requires Python 3.9+, [uv](https://docs.astral.sh/uv/), and `ffmpeg`
(for `ffprobe`).

```bash
git clone https://github.com/<your-user>/kglw-manager.git
cd kglw-manager
uv sync
```

## Configuration

Settings live in `~/.kglw_manager/config.json` and can be edited from the
interactive Settings menu. Nothing sensitive is stored in the repo.

| Setting | Environment variable | Purpose |
|---|---|---|
| `collection_path` | `KGLW_COLLECTION_PATH` | Root of your concert library |
| `plex_url` | `KGLW_PLEX_URL` | Plex server URL |
| `plex_token` | `KGLW_PLEX_TOKEN` | Plex auth token |
| `plex_library_path` | — | How Plex sees the library root |
| `discord_webhook_url` | `KGLW_DISCORD_WEBHOOK_URL` | Optional notifications |
| `spreadsheet_path` | — | Local HTML export of the community spreadsheet |

Plex credentials resolve as **explicit argument → environment variable →
config file**, and the app fails with a clear message when none is set.

## Usage

```bash
uv run python kglw-manager.py interactive       # browse and manage
uv run python kglw-manager.py scan              # scan the collection
uv run python kglw-manager.py analyze-quality   # ffprobe every video (do this first)
uv run python kglw-manager.py find-upgrades --year 2024
uv run python kglw-manager.py stats
uv run python kglw-manager.py integrity         # check folder/file date agreement
```

> **Run `analyze-quality` before `find-upgrades`.** Collection scans are fast
> scans that skip ffprobe, so resolution is unknown until analysis has run.
> Upgrade detection deliberately refuses to guess: it only reports "low
> resolution" for files it has actually measured.

## Expected layout

```
<collection root>/
└── 2024 USA-Canada - Summer/
    └── 2024-08-27 - Philadelphia, PA, USA (The Dell Music Center)/
        ├── 2024-08-27 - Philadelphia, PA, USA (The Dell Music Center).mp4
        ├── poster.jpg
        └── .show_metadata.json
```

Tour directory names come from the kglw.net `tourname` field with filesystem
-unsafe characters replaced (`2024 USA/Canada - Summer` → `2024 USA-Canada - Summer`).

## YouTube access

YouTube serves a JavaScript "n challenge"; without a solver, yt-dlp is offered
only image formats and every download fails. All yt-dlp calls request
`ejs:github` remote components, which needs a JS runtime (`deno` or `node`)
available on the system. Keep yt-dlp current — an outdated build cannot parse
YouTube at all:

```bash
uv lock --upgrade-package yt-dlp && uv sync
```

## Tests

```bash
uv run python -m pytest tests/unit -q < /dev/null
```

566 unit tests. The stdin redirect matters: a few interactive tests reach a
real `input()` prompt.

## License

MIT
