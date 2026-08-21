"""Normalize every show poster to Plex's 2:3 movie poster slot without cropping."""
import hashlib, shutil, subprocess, sys
from pathlib import Path

from kglw_manager.config import config
ROOT = Path(config.get("collection_path"))
BACKUP = ROOT / ".trash" / "posters_original"
VID = {'.mp4','.mkv','.webm','.avi','.mov'}
IMG = ('.jpg','.jpeg','.png','.webp')
W, H = 1000, 1500          # 2:3, matches Plex's movie poster slot
APPLY = "--apply" in sys.argv

def dims(p):
    try:
        r = subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
            '-show_entries','stream=width,height','-of','csv=p=0',str(p)],
            capture_output=True, text=True, timeout=30)
        w,h = r.stdout.strip().split(',')[:2]
        return int(w), int(h)
    except Exception:
        return None, None

def render(src, dst):
    """Fit the whole image inside 2:3; fill the remainder with a blurred copy."""
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.15[bg];"
          f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
    r = subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(src),
        '-filter_complex', vf, '-frames:v','1','-q:v','2', str(dst)],
        capture_output=True, text=True, timeout=180)
    return r.returncode == 0 and dst.exists() and dst.stat().st_size > 0

stats = dict(normalized=0, already_ok=0, deduped=0, unhijacked=0, from_frame=0, failed=0, no_art=0)
for tour in sorted(p for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith('.')):
    for show in sorted(p for p in tour.iterdir() if p.is_dir()):
        vids = [f for f in show.iterdir() if f.is_file() and f.suffix.lower() in VID and not f.name.endswith('.part')]
        if not vids:
            continue
        files = [f for f in show.iterdir() if f.is_file()]
        posters = [f for f in files if f.name.lower().startswith('poster.') and f.suffix.lower() in IMG]
        # images named after the video hijack Plex's poster slot (they're 16:9 thumbs)
        hijackers = [f for f in files if f.suffix.lower() in IMG
                     and not f.name.lower().startswith('poster.')
                     and any(f.stem == v.stem for v in vids)]

        bdir = BACKUP / tour.name / show.name
        def backup(f):
            if APPLY:
                bdir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, bdir / f.name)

        for h in hijackers:
            backup(h)
            if APPLY:
                h.unlink()
            stats['unhijacked'] += 1

        source = None
        if posters:
            # widest-resolution source wins; ties break on file size
            scored = []
            for p in posters:
                w, h = dims(p)
                scored.append(((w or 0) * (h or 0), p.stat().st_size, p))
            scored.sort(key=lambda t: (-t[0], -t[1]))
            source = scored[0][2]
            for _, _, extra in scored[1:]:
                backup(extra)
                if APPLY:
                    extra.unlink()
                stats['deduped'] += 1
        elif vids:
            # no art anywhere - build one from a frame a third of the way in
            if APPLY:
                tmp = show / '.frame.jpg'
                subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-ss','600',
                    '-i', str(vids[0]), '-frames:v','1', str(tmp)],
                    capture_output=True, timeout=180)
                if tmp.exists() and tmp.stat().st_size > 0:
                    source = tmp
                else:
                    stats['no_art'] += 1; continue
            else:
                stats['from_frame'] += 1; continue

        if source is None:
            stats['no_art'] += 1; continue

        w, h = dims(source)
        target = show / 'poster.jpg'
        if w and h and abs(w / h - W / H) < 0.005 and source.name == 'poster.jpg':
            stats['already_ok'] += 1
            continue
        if not APPLY:
            stats['normalized'] += 1
            continue

        backup(source)
        tmp_out = show / '.poster_new.jpg'
        if render(source, tmp_out):
            if source.name == '.frame.jpg':
                source.unlink(missing_ok=True); stats['from_frame'] += 1
            elif source != target:
                source.unlink(missing_ok=True)
            tmp_out.replace(target)
            stats['normalized'] += 1
        else:
            tmp_out.unlink(missing_ok=True)
            stats['failed'] += 1

print(("APPLIED" if APPLY else "DRY RUN") + " " + str(stats))
print(f"backup dir: {BACKUP}")
