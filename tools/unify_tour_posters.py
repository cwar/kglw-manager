"""Give a whole tour one poster identity, varied by colorway per night.

Some tours have a poster for nearly every night; those already read as a
coherent run and are left alone. Others are mostly borrowed art with a handful
of one-off posters mixed in, which makes the run visually restart part-way
through. For those, the image the most shows already share - usually the tour
poster listing every date - becomes the base for the whole tour, and each night
gets a distinct colorway.

Only tours at or below UNIQUE_LIMIT unique-art are touched, so tours where the
band published genuine per-night variants are never overwritten.
"""
import hashlib, shutil, subprocess, sys
from collections import defaultdict
from pathlib import Path

from kglw_manager.config import config

ROOT = Path(config.get("collection_path"))
BACKUP_SOURCES = [ROOT / ".trash" / "posters_colorway_original",
                  ROOT / ".trash" / "posters_before_correction"]
BACKUP = ROOT / ".trash" / "posters_before_unify"
VID = {'.mp4','.mkv','.webm','.avi','.mov'}
W, H = 1000, 1500
BOLD_STEP = 137          # golden angle: consecutive nights land far apart
UNIQUE_LIMIT = 0.34      # skip tours where more than a third have their own art
MIN_SHOWS = 3
APPLY = "--apply" in sys.argv
ONLY = next((a for a in sys.argv[1:] if not a.startswith('--')), None)


def mean_saturation(src) -> float:
    """0 means greyscale, where hue rotation has no visible effect."""
    try:
        data = subprocess.run(
            ['ffmpeg','-nostdin','-v','error','-i',str(src),'-vf','scale=60:90',
             '-f','rawvideo','-pix_fmt','rgb24','-'],
            capture_output=True, timeout=60).stdout
        if not data:
            return 1.0
        total = count = 0
        for i in range(0, len(data) - 2, 3):
            hi = max(data[i], data[i+1], data[i+2]); lo = min(data[i], data[i+1], data[i+2])
            total += 0.0 if hi == 0 else (hi - lo) / hi
            count += 1
        return total / count if count else 1.0
    except Exception:
        return 1.0


def render(src, dst, hue):
    if hue and mean_saturation(src) < 0.05:
        tint = f",colorize=hue={hue}:saturation=0.55:mix=0.85"    # greyscale art
    elif hue:
        tint = f",hue=h={hue}:s=1.3"
    else:
        tint = ""
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.15{tint}[bg];"
          f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease{tint}[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
    r = subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(src),
        '-filter_complex', vf, '-frames:v','1','-q:v','2', str(dst)],
        capture_output=True, timeout=180)
    return r.returncode == 0 and dst.exists() and dst.stat().st_size > 0


def original_poster(tour_name, show):
    """The pre-colorway image for a show, so grouping sees true bases."""
    for backup in BACKUP_SOURCES:
        p = backup / tour_name / show.name / 'poster.jpg'
        if p.exists():
            return p
    p = show / 'poster.jpg'
    return p if p.exists() else None


unified = skipped_unique = skipped_small = shows_done = 0
for tour in sorted(p for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith('.')):
    if ONLY and tour.name != ONLY:
        continue
    shows = [s for s in sorted(tour.iterdir())
             if s.is_dir() and any(f.suffix.lower() in VID and not f.name.endswith('.part')
                                   for f in s.iterdir() if f.is_file())]
    if len(shows) < MIN_SHOWS:
        skipped_small += 1
        continue

    pinned = [s for s in shows if (s / '.poster_pinned').exists()]
    groups = defaultdict(list)
    sources = {}
    for s in shows:
        if s in pinned:
            continue                      # hand-chosen art is never restyled
        p = original_poster(tour.name, s)
        if not p:
            continue
        digest = hashlib.md5(p.read_bytes()).hexdigest()
        groups[digest].append(s)
        sources.setdefault(digest, p)
    if not groups:
        continue

    counted = sum(len(v) for v in groups.values()) + len(pinned)
    unique_share = (sum(1 for v in groups.values() if len(v) == 1)
                    + len(pinned)) / counted
    if unique_share > UNIQUE_LIMIT:
        skipped_unique += 1
        continue

    digest, members = max(groups.items(), key=lambda kv: len(kv[1]))
    base = sources[digest]
    print(f"\n{tour.name}  ({counted} shows, {len(groups)} bases, "
          f"{unique_share:.0%} unique{', ' + str(len(pinned)) + ' pinned' if pinned else ''}) "
          f"-> base shared by {len(members)}")

    for i, show in enumerate(shows):
        if show in pinned:
            print(f"    {show.name[:10]}  pinned - left as is")
            continue
        hue = (i * BOLD_STEP) % 360
        if not APPLY:
            print(f"    {show.name[:10]}  hue={hue:>3}")
            shows_done += 1
            continue
        target = show / 'poster.jpg'
        bdir = BACKUP / tour.name / show.name
        if target.exists():
            bdir.mkdir(parents=True, exist_ok=True)
            if not (bdir / 'poster.jpg').exists():
                shutil.copy2(target, bdir / 'poster.jpg')
        tmp = show / '.poster_unify.jpg'
        if render(base, tmp, hue):
            tmp.replace(target)
            shows_done += 1
            print(f"    {show.name[:10]}  hue={hue:>3}  ok")
        else:
            tmp.unlink(missing_ok=True)
            print(f"    {show.name[:10]}  hue={hue:>3}  FAILED")
    unified += 1

print(("\nAPPLIED" if APPLY else "\nDRY RUN") +
      f": unified {unified} tours ({shows_done} shows); "
      f"left {skipped_unique} tours alone for having their own art; "
      f"{skipped_small} tours below {MIN_SHOWS} shows")
