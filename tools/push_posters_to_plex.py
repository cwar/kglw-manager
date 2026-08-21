"""Upload each show's normalized local poster into Plex and lock it."""
import re, sys
from pathlib import Path
from kglw_manager.plex_manager import PlexManager

pm = PlexManager()
from kglw_manager.config import config
ROOT = Path(config.get("collection_path"))
DATE = re.compile(r'(\d{4})[ -](\d{2})[ -](\d{2})')

# index local posters by show date
by_date = {}
for tour in ROOT.iterdir():
    if not tour.is_dir() or tour.name.startswith('.'):
        continue
    for show in tour.iterdir():
        if not show.is_dir():
            continue
        p = show / 'poster.jpg'
        if p.exists() and DATE.match(show.name[:10].replace(' ', '-')):
            by_date.setdefault(show.name[:10], p)

items = pm.library.all()
print(f"plex items: {len(items)} | local posters indexed: {len(by_date)}", flush=True)
uploaded = skipped = failed = 0
for i, it in enumerate(items, 1):
    try:
        m = DATE.search(it.title or "")
        if not m:
            skipped += 1; continue
        date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        poster = by_date.get(date)
        if not poster:
            skipped += 1; continue
        it.uploadPoster(filepath=str(poster))
        it.lockPoster()
        uploaded += 1
        if uploaded % 25 == 0:
            print(f"  {uploaded} uploaded ... ({i}/{len(items)})", flush=True)
    except Exception as e:
        failed += 1
        print(f"  ERR {(it.title or '?')[:44]}: {str(e)[:70]}", flush=True)

print(f"\nuploaded+locked: {uploaded}\nno local poster/date: {skipped}\nfailed: {failed}")
