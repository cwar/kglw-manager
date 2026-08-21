"""Give each Plex tour collection a real poster instead of Plex's auto mosaic.

Plex builds collection art as a composite of member posters and regenerates it
whenever membership changes. Preference order:

  1. the tour's own poster - the image shared by several shows of that tour,
     which is how KGLW tour posters (listing every date) end up on disk
  2. otherwise a hero: the highest-resolution show poster from that tour,
     with a blurred fill behind it

Either way the tour name is captioned and the poster is locked so Plex keeps it.
"""
import hashlib, subprocess, sys
from collections import Counter
from pathlib import Path

from kglw_manager.plex_manager import PlexManager
from kglw_manager.config import config

ROOT = Path(config.get("collection_path"))
BACKUPS = [ROOT / ".trash" / "posters_colorway_original",
           ROOT / ".trash" / "posters_before_correction"]
OUT = ROOT / ".trash" / "collection_posters"
VID = {'.mp4','.mkv','.webm','.avi','.mov'}
W, H = 1000, 1500
APPLY = "--apply" in sys.argv
ONLY = next((a for a in sys.argv[1:] if not a.startswith('--')), None)

def esc(text):
    return text.replace('\\', '').replace(':', '\\:').replace("'", "")

def build(src, title, dst, mode):
    caption = (f"drawbox=x=0:y=h-150:w=iw:h=150:color=black@0.72:t=fill,"
               f"drawtext=text='{esc(title)}':fontcolor=white:fontsize=50:"
               f"x=(w-text_w)/2:y=h-102")
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.2[bg];"
          f"[0:v]scale={W}:{H-170}:force_original_aspect_ratio=decrease[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2-46,{caption}")
    r = subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(src),
        '-filter_complex', vf, '-frames:v','1','-q:v','2', str(dst)],
        capture_output=True, timeout=180)
    return r.returncode == 0 and dst.exists() and dst.stat().st_size > 0

def tour_poster(tour_dir):
    """The image several shows of this tour share is the tour's own poster."""
    counts = Counter(); first = {}
    for backup_root in BACKUPS:
        d = backup_root / tour_dir.name
        if not d.is_dir():
            continue
        for show in d.iterdir():
            p = show / 'poster.jpg'
            if not p.exists():
                continue
            h = hashlib.md5(p.read_bytes()).hexdigest()
            counts[h] += 1
            first.setdefault(h, p)
    if counts:
        h, n = counts.most_common(1)[0]
        if n >= 2:
            return first[h], f"tour poster (shared by {n} shows)"
    return None, None

def hero(tour_dir):
    best = (0, None)
    for show in tour_dir.iterdir():
        if not show.is_dir():
            continue
        p = show / 'poster.jpg'
        if not p.exists():
            continue
        try:
            r = subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
                '-show_entries','stream=height','-of','csv=p=0',str(p)],
                capture_output=True, text=True, timeout=60)
            h = int(r.stdout.strip().split(',')[0])
        except Exception:
            h = 0
        size = p.stat().st_size
        if (h, size) > (best[0], 0):
            best = (h, p)
    return best[1], "hero poster"

pm = PlexManager()
colls = {c.title: c for c in pm.library.collections()}
def norm(x): return x.replace('/', '-').strip().lower()
by_norm = {norm(t): c for t, c in colls.items()}

OUT.mkdir(parents=True, exist_ok=True)
used_tour = used_hero = skipped = failed = 0
for tour_dir in sorted(p for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith('.')):
    if ONLY and tour_dir.name != ONLY:
        continue
    if not any(s.is_dir() and any(f.suffix.lower() in VID and not f.name.endswith('.part')
               for f in s.iterdir() if f.is_file()) for s in tour_dir.iterdir()):
        continue
    coll = by_norm.get(norm(tour_dir.name))
    if not coll:
        print(f"  no collection for '{tour_dir.name[:44]}'")
        skipped += 1
        continue
    src, why = tour_poster(tour_dir)
    if not src:
        src, why = hero(tour_dir)
    if not src:
        skipped += 1
        continue
    dst = OUT / f"{tour_dir.name}.jpg"
    label = "tour" if why.startswith("tour") else "hero"
    if not APPLY:
        print(f"  [{label}] {tour_dir.name[:46]:46} <- {why}")
        used_tour += label == "tour"; used_hero += label == "hero"
        continue
    if not build(src, tour_dir.name, dst, label):
        failed += 1
        continue
    try:
        coll.uploadPoster(filepath=str(dst))
        coll.lockPoster()
        used_tour += label == "tour"; used_hero += label == "hero"
        print(f"  ✅ [{label}] {coll.title[:50]}")
    except Exception as e:
        failed += 1
        print(f"  ❌ {coll.title[:40]}: {str(e)[:60]}")

print(("APPLIED" if APPLY else "DRY RUN") +
      f": tour_poster={used_tour} hero={used_hero} skipped={skipped} failed={failed}")
