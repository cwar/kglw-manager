"""Remove redundant duplicate video files left behind by past renaming passes.

Shows can contain the same clip twice - once under the old
"King Gizzard & The Lizard Wizard - <date> ... - concert.mp4" name and once
under the current "<show dir name>.mp4" convention - which also produces two
entries per show in Plex.

Only unambiguous cases are touched:
  * byte-identical pairs            -> keep the current-convention name
  * same duration, different height -> keep the higher resolution
Pairs whose durations differ are left alone and reported, since those are
genuinely different recordings rather than duplicates.

Losers are moved to <collection>/.trash/duplicate_videos, never deleted.
"""
import hashlib, shutil, subprocess, sys
from pathlib import Path
from kglw_manager.config import config

ROOT = Path(config.get("collection_path"))
TRASH = ROOT / ".trash" / "duplicate_videos"
VID = {'.mp4','.mkv','.webm','.avi','.mov'}
APPLY = "--apply" in sys.argv
PREFER_LONGER = "--prefer-longer" in sys.argv

def sig(p, n=4*1024*1024):
    h = hashlib.md5(); size = p.stat().st_size
    with p.open('rb') as f:
        h.update(f.read(n))
        if size > 2*n:
            f.seek(-n, 2); h.update(f.read(n))
    return h.hexdigest(), size

def info(p):
    try:
        r = subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
            '-show_entries','format=duration:stream=height','-of','csv=p=0',
            str(p)], capture_output=True, text=True, timeout=60)
        parts = [x for x in r.stdout.split() if x]
        height = int(parts[0].split(',')[0]) if parts else 0
        dur = float(parts[-1].split(',')[-1]) if parts else 0.0
        return height, dur
    except Exception:
        return 0, 0.0

removed_identical = removed_lowres = removed_shorter = kept_ambiguous = 0
ambiguous = []
tradeoffs = []
for tour in sorted(p for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith('.')):
    for show in sorted(p for p in tour.iterdir() if p.is_dir()):
        vids = [f for f in show.iterdir()
                if f.is_file() and f.suffix.lower() in VID and not f.name.endswith('.part')]
        if len(vids) != 2:
            continue
        old = [v for v in vids if v.name.startswith('King Gizzard')]
        new = [v for v in vids if not v.name.startswith('King Gizzard')]
        if not (old and new):
            continue
        old, new = old[0], new[0]

        sa, za = sig(old); sb, zb = sig(new)
        if sa == sb and za == zb:
            loser, reason = old, "identical"
        else:
            ho, do = info(old); hn, dn = info(new)
            if abs(do - dn) <= 1.0 and ho != hn:
                loser = old if ho < hn else new
                reason = "lower resolution, same duration"
            elif PREFER_LONGER and abs(do - dn) > 1.0:
                # A longer recording is more of the show; keep it even when the
                # shorter copy is higher resolution, but flag the trade-off when
                # the resolution sacrificed is large.
                loser = old if do < dn else new
                keeper_h, loser_h = (hn, ho) if do < dn else (ho, hn)
                reason = "shorter duration"
                if loser_h >= keeper_h * 2 and loser_h > 0:
                    tradeoffs.append((show.name, f"kept {keeper_h}p/{max(do,dn)/60:.0f}m",
                                      f"dropped {loser_h}p/{min(do,dn)/60:.0f}m"))
            else:
                kept_ambiguous += 1
                ambiguous.append((show.name, f"{ho}p/{do/60:.0f}m", f"{hn}p/{dn/60:.0f}m"))
                continue

        if APPLY:
            dest = TRASH / tour.name / show.name
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(loser), str(dest / loser.name))
        if reason == "identical":
            removed_identical += 1
        elif reason == "shorter duration":
            removed_shorter += 1
        else:
            removed_lowres += 1

print(("APPLIED" if APPLY else "DRY RUN"))
print(f"  identical duplicates removed:        {removed_identical}")
print(f"  lower-resolution copies removed:     {removed_lowres}")
print(f"  shorter copies removed (longer wins): {removed_shorter}")
print(f"  left alone (durations differ):       {kept_ambiguous}")
if tradeoffs:
    print("\n  kept the longer copy at a notable resolution cost:")
    for name, kept, dropped in tradeoffs:
        print(f"    {name[:44]:44} {kept:>22}  {dropped:>22}")
if ambiguous:
    print("\n  needs a human decision:")
    for name, a, b in ambiguous[:25]:
        print(f"    {name[:44]:44} old={a:>12}  new={b:>12}")
