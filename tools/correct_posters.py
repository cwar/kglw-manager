"""Replace borrowed/shared posters with each show's own art from kglw.net."""
import hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
import requests

from kglw_manager.config import config
ROOT = Path(config.get("collection_path"))
BACKUP = ROOT / ".trash" / "posters_before_correction"
VID = {'.mp4','.mkv','.webm','.avi','.mov'}
W, H = 1000, 1500
APPLY = "--apply" in sys.argv
UA = {"User-Agent": "KGLW-Manager/2.1.0"}

posters = {r['showdate']: r['URL'] for r in requests.get('https://kglw.net/api/v2/uploads.json?limit=2000', headers=UA, timeout=45).json()['data']
           if r.get('upload_type') == 'poster-art' and r.get('showdate')}

def normalize(src, dst):
    vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.15[bg];"
          f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
    r = subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(src),
        '-filter_complex', vf, '-frames:v','1','-q:v','2', str(dst)],
        capture_output=True, timeout=180)
    return r.returncode == 0 and dst.exists() and dst.stat().st_size > 0

shows = []
for tour in sorted(p for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith('.')):
    for s in sorted(p for p in tour.iterdir() if p.is_dir()):
        if any(f.suffix.lower() in VID and not f.name.endswith('.part') for f in s.iterdir() if f.is_file()):
            shows.append((tour.name, s))

fixed = same = missing = failed = 0
for tour_name, show in shows:
    date = show.name[:10]
    url = posters.get(date)
    if not url:
        missing += 1
        continue
    if not APPLY:
        fixed += 1
        continue
    try:
        resp = requests.get(url, headers=UA, timeout=45)
        if resp.status_code != 200 or not resp.content:
            failed += 1
            print(f"  ❌ HTTP {resp.status_code} {date}", flush=True)
            time.sleep(1.0)
            continue
        raw = show / '.poster_raw'
        raw.write_bytes(resp.content)
        target = show / 'poster.jpg'
        # skip if the correct art is already what's in place
        if target.exists() and hashlib.md5(resp.content).hexdigest() == \
           hashlib.md5((show / '.poster_src_hash').read_bytes()).hexdigest() if (show/'.poster_src_hash').exists() else False:
            raw.unlink(missing_ok=True); same += 1; continue
        bdir = BACKUP / tour_name / show.name
        if target.exists():
            bdir.mkdir(parents=True, exist_ok=True)
            if not (bdir / 'poster.jpg').exists():
                shutil.copy2(target, bdir / 'poster.jpg')
        tmp = show / '.poster_new.jpg'
        if normalize(raw, tmp):
            tmp.replace(target)
            (show / '.poster_src_hash').write_bytes(resp.content[:4096])
            fixed += 1
            if fixed % 25 == 0:
                print(f"  ... {fixed} corrected", flush=True)
        else:
            tmp.unlink(missing_ok=True); failed += 1
        raw.unlink(missing_ok=True)
        time.sleep(0.6)   # be gentle with kglw.net
    except Exception as e:
        failed += 1
        print(f"  ❌ {date}: {str(e)[:60]}", flush=True)
        time.sleep(1.0)

print(("APPLIED" if APPLY else "DRY RUN") +
      f": corrected={fixed} unchanged={same} no_art_on_kglw={missing} failed={failed}")
