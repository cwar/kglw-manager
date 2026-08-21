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
