"""Give shows that share one tour poster distinct colorways, like the band's own variant series."""
import hashlib, shutil, subprocess, sys
from pathlib import Path
from collections import defaultdict

from kglw_manager.config import config
ROOT = Path(config.get("collection_path"))
BACKUP = ROOT / ".trash" / "posters_colorway_original"
VID = {'.mp4','.mkv','.webm','.avi','.mov'}
W, H = 1000, 1500
TOUR_FILTER = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else None
APPLY = "--apply" in sys.argv

def render(src, dst, hue, sat):
    """Normalize to 2:3 and rotate hue. Night one keeps the original colors."""
    hue_fg = f",hue=h={hue}:s={sat}" if hue else ""
    hue_bg = f",hue=h={hue}:s={sat}" if hue else ""
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.15{hue_bg}[bg];"
          f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease{hue_fg}[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
    r = subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(src),
        '-filter_complex', vf, '-frames:v','1','-q:v','2', str(dst)],
        capture_output=True, timeout=180)
    return r.returncode == 0 and dst.exists() and dst.stat().st_size > 0

total = 0
for tour in sorted(p for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith('.')):
    if TOUR_FILTER and tour.name != TOUR_FILTER:
        continue
    groups = defaultdict(list)
    for show in sorted(p for p in tour.iterdir() if p.is_dir()):
        if not any(f.suffix.lower() in VID and not f.name.endswith('.part')
                   for f in show.iterdir() if f.is_file()):
            continue
        p = show / 'poster.jpg'
        if p.exists():
            groups[hashlib.md5(p.read_bytes()).hexdigest()].append(show)

    for _, shows in groups.items():
        if len(shows) < 2:
            continue  # unique art keeps its own colors
        shows.sort(key=lambda s: s.name)          # chronological
        # Bold, psychedelic separation: step by a large angle and wrap, so
        # consecutive nights land far apart on the wheel rather than drifting.
        BOLD_STEP = 137          # golden angle - never repeats until the wheel is full
        for i, show in enumerate(shows):
            hue = (i * BOLD_STEP) % 360
            src = show / 'poster.jpg'
            label = f"{show.name[:10]} hue={hue:>3}"
            if not APPLY:
                print(f"  {label}  ({tour.name[:34]})")
                total += 1
                continue
            bdir = BACKUP / tour.name / show.name
            bdir.mkdir(parents=True, exist_ok=True)
            if not (bdir / 'poster.jpg').exists():
                shutil.copy2(src, bdir / 'poster.jpg')
            if hue == 0:
                total += 1
                continue                            # night one unchanged
            tmp = show / '.poster_cw.jpg'
            if render(bdir / 'poster.jpg', tmp, hue, 1.3):
                tmp.replace(src)
                print(f"  {label}  ✅")
                total += 1
            else:
                tmp.unlink(missing_ok=True)
                print(f"  {label}  ❌")

print(("APPLIED" if APPLY else "DRY RUN") + f": {total} shows in shared-poster groups")
