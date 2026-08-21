# Maintenance tools

One-shot scripts for repairing an existing collection. Each supports a dry run
by default and takes `--apply` to make changes. Originals are backed up under
`<collection>/.trash/` before anything is overwritten.

| Script | What it does |
|---|---|
| `correct_posters.py` | Replaces borrowed/shared posters with each show's own art from kglw.net. Bulk fill-in scripts historically reused one tour poster across many dates; kglw.net actually publishes unique art per show. |
| `normalize_posters.py` | Fits posters into Plex's 2:3 slot without cropping, removes duplicate `poster.jpeg`, and clears video-named thumbnails that outrank `poster.jpg`. |
| `poster_colorways.py` | For shows with no art of their own that share a borrowed poster, generates distinct colorways (golden-angle hue rotation) so a run of nights is distinguishable. Never touches unique artwork. |
| `push_posters_to_plex.py` | Uploads each show's local `poster.jpg` into Plex and locks it. Required — Plex keeps its own artwork selection until a poster is uploaded and locked. |

Run from the repo root, e.g.:

```bash
uv run python tools/correct_posters.py            # dry run
uv run python tools/correct_posters.py --apply
```

## Video / upgrade tools

| Script | What it does |
|---|---|
| `dedupe_show_videos.py` | Removes redundant copies left by past renaming passes (old `King Gizzard & The Lizard Wizard - …` name alongside the current one). Only touches byte-identical pairs and same-duration/lower-resolution pairs; anything whose durations differ is reported for a human, since those are different recordings. |
| `overnight_upgrade.py` | Unattended upgrade pass. Ranks candidates worst-quality-first, checks curated spreadsheet links, and replaces a show only when the replacement is strictly better (higher resolution and not materially shorter). Stops on a deadline, a download cap, or low disk. |

Both move superseded files to `<collection>/.trash/`, never delete.

### Pinning a poster

Drop an empty `.poster_pinned` file in a show directory and `correct_posters.py`
will leave that show's `poster.jpg` alone. Useful when:

* a multi-night event shares one poster covering a date range (the Field of
  Vision 2026 art is captioned "14-16 August 2026" and belongs on all three
  nights, but kglw.net only files it against night one), or
* kglw.net has an unrelated image filed as a show's poster-art.
