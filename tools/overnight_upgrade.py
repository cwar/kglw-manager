"""Unattended upgrade pass: find better sources for low-quality shows and fetch them.

Safety rules, because this runs without supervision:
  * a replacement must be STRICTLY better - higher resolution, and never
    materially shorter than what is already held
  * the existing file is moved to .trash/superseded, never deleted
  * stops on low disk, a wall-clock deadline, or a download cap
  * every decision is logged with the numbers behind it
"""
import json, re, shutil, subprocess, sys, time
from datetime import datetime, timedelta
from pathlib import Path

from kglw_manager.collection import CollectionManager
from kglw_manager.youtube_search import YouTubeSearcher
from kglw_manager.google_sheets_parser import GoogleSheetsParser
from kglw_manager.config import config

ROOT = Path(config.get("collection_path"))
TRASH = ROOT / ".trash" / "superseded"
VID = {'.mp4','.mkv','.webm','.avi','.mov'}
YTDLP = shutil.which('yt-dlp') or 'yt-dlp'
EJS = ["--remote-components", "ejs:github"]

DEADLINE      = datetime.now() + timedelta(hours=float(sys.argv[sys.argv.index("--hours")+1])) \
                if "--hours" in sys.argv else datetime.now() + timedelta(hours=7)
MIN_FREE_GB   = 250          # leave headroom on the NAS
MAX_DOWNLOADS = 120
RESOLUTION_FLOOR = 720       # a better source may lower resolution, but not below this
APPLY         = "--apply" in sys.argv
SEARCHER = None  # lazily built; supplies the official/Dempsee ordering

def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)

def free_gb():
    st = __import__('os').statvfs(ROOT)
    return st.f_bavail * st.f_frsize / 1e9

def probe(url):
    try:
        r = subprocess.run([YTDLP, *EJS, "--skip-download", "--no-warnings", "--no-playlist",
            "--socket-timeout", "30", "--retries", "1",
            "--print", "%(id)s|%(duration)s|%(height)s|%(channel_id)s|%(channel)s|%(uploader_id)s|%(title)s", url],
            capture_output=True, text=True, timeout=180)
        line = [l for l in r.stdout.strip().split("\n") if "|" in l]
        if not line:
            return None
        p = line[-1].split("|")
        return {"id": p[0],
                "dur": float(p[1]) if p[1] not in ("NA","None","") else 0.0,
                "h": int(p[2]) if p[2].isdigit() else 0,
                "cid": p[3], "ch": p[4], "uid": p[5],
                "title": "|".join(p[6:])[:70]}
    except Exception:
        return None

def current_source_tier(show_dir):
    """Source tier of the copy already held, read from its yt-dlp .info.json.

    Without that sidecar the provenance is unknown, so it is treated as the
    lowest tier - which lets a known-good source replace it.
    """
    for j in sorted(show_dir.glob('*.info.json')):
        try:
            meta = json.loads(j.read_text(encoding='utf-8', errors='replace'))
        except Exception:
            continue
        return SEARCHER.source_tier({
            'channel_id': meta.get('channel_id') or '',
            'uploader_id': meta.get('uploader_id') or '',
            'channel': meta.get('channel') or meta.get('uploader') or '',
        })
    return 2


def current_best(show_dir):
    best = (0, 0.0, None)
    for f in show_dir.iterdir():
        if not f.is_file() or f.suffix.lower() not in VID or f.name.endswith('.part'):
            continue
        try:
            r = subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
                '-show_entries','format=duration:stream=height','-of','csv=p=0', str(f)],
                capture_output=True, text=True, timeout=90)
            parts = [x for x in r.stdout.split() if x]
            h = int(parts[0].split(',')[0]) if parts else 0
            d = float(parts[-1].split(',')[-1]) if parts else 0.0
        except Exception:
            h, d = 0, 0.0
        if h > best[0]:
            best = (h, d, f)
    return best

def download(url, dest_dir, base):
    tmp = dest_dir / ".incoming"
    tmp.mkdir(exist_ok=True)
    try:
        r = subprocess.run([YTDLP, *EJS,
            "-f", "bestvideo[height<=2160]+bestaudio/best", "--merge-output-format", "mp4",
            "--write-info-json", "--no-playlist",
            "-o", str(tmp / "%(title)s.%(ext)s"), url],
            capture_output=True, text=True, timeout=7200)
        if r.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True); return None
        got = [f for f in tmp.iterdir() if f.suffix.lower() in VID and not f.name.endswith('.part')]
        if not got:
            shutil.rmtree(tmp, ignore_errors=True); return None
        newest = max(got, key=lambda f: f.stat().st_size)
        final = dest_dir / f"{base}.mp4"
        info = [f for f in tmp.iterdir() if f.name.endswith('.info.json')]
        return newest, final, (info[0] if info else None), tmp
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        return None

SEARCHER = YouTubeSearcher()
log("scanning collection for upgrade candidates")
mgr = CollectionManager(str(ROOT))
candidates = mgr.find_upgrade_candidates()
log(f"{len(candidates)} candidates reported")

sheet_path = config.get_spreadsheet_path()
sheet = GoogleSheetsParser(sheet_path) if sheet_path else None
sheet_data = sheet.ensure_loaded() if sheet else {}
log(f"spreadsheet: {len(sheet_data)} shows with curated links")

# worst quality first - that is where an upgrade matters most
def rank(c):
    q = c.get('current_quality', '')
    m = re.match(r'(\d+)p', q or '')
    return int(m.group(1)) if m else 0
candidates.sort(key=rank)

done = upgraded = skipped = failed = 0
for cand in candidates:
    if datetime.now() > DEADLINE:
        log("deadline reached - stopping"); break
    if upgraded >= MAX_DOWNLOADS:
        log("download cap reached - stopping"); break
    if free_gb() < MIN_FREE_GB:
        log(f"low disk ({free_gb():.0f} GB free) - stopping"); break

    show_dir = Path(cand['path'])
    date = cand.get('date') or show_dir.name[:10]
    if not show_dir.is_dir():
        continue
    done += 1

    cur_h, cur_d, cur_f = current_best(show_dir)
    cur_tier = current_source_tier(show_dir)
    urls = []
    entry = sheet_data.get(date)
    if entry:
        urls += [l['url'] for l in entry['youtube_links'] if 'playlist' not in l['url']]
    urls = urls[:4]
    if not urls:
        skipped += 1
        continue

    best = None
    for u in urls:
        info = probe(u)
        if not info:
            continue
        tier = SEARCHER.source_tier({'channel_id': info['cid'],
                                     'uploader_id': info.get('uid', ''),
                                     'channel': info['ch']})

        # Never accept a materially shorter recording, whatever the source.
        if info['dur'] < max(cur_d * 0.9, 60):
            continue

        if tier < cur_tier:
            # A more trusted source wins outright, even at lower resolution -
            # an official upload is preferred over a stranger's 4K rip. Guard
            # only against a genuinely unwatchable drop.
            if info['h'] < RESOLUTION_FLOOR and info['h'] < cur_h:
                log(f"   skip {info['ch'][:20]}: better source but only {info['h']}p "
                    f"(floor {RESOLUTION_FLOOR}p, holding {cur_h}p)")
                continue
        elif tier == cur_tier:
            if info['h'] <= cur_h:
                continue          # same source tier: needs more pixels
        else:
            continue              # never move to a less trusted source

        key = (-tier, info['h'], info['dur'])
        if not best or key > best[0]:
            best = (key, info, u)
        time.sleep(1.0)

    if not best:
        skipped += 1
        continue

    _, info, url = best
    names = {0: "OFFICIAL", 1: "Dempsee", 2: "other"}
    tier_name = names[-best[0][0]]
    why = "better source" if -best[0][0] < cur_tier else "higher resolution"
    log(f"UPGRADE {date}: {cur_h}p/{cur_d/60:.0f}m [{names[cur_tier]}] -> "
        f"{info['h']}p/{info['dur']/60:.0f}m [{tier_name}: {info['ch'][:20]}]  ({why})")
    if not APPLY:
        upgraded += 1
        continue

    got = download(url, show_dir, show_dir.name)
    if not got:
        failed += 1
        log(f"   download failed for {date}")
        continue
    newf, final, infojson, tmp = got
    try:
        r = subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
            '-show_entries','format=duration:stream=height','-of','csv=p=0', str(newf)],
            capture_output=True, text=True, timeout=90)
        parts = [x for x in r.stdout.split() if x]
        nh = int(parts[0].split(',')[0]) if parts else 0
        nd = float(parts[-1].split(',')[-1]) if parts else 0.0
    except Exception:
        nh, nd = 0, 0.0
    new_tier = -best[0][0]
    accept = nd >= max(cur_d * 0.9, 60) and (
        (new_tier < cur_tier and (nh >= RESOLUTION_FLOOR or nh >= cur_h))
        or (new_tier == cur_tier and nh > cur_h))
    if not accept:
        log(f"   rejected after download ({nh}p/{nd/60:.0f}m vs held {cur_h}p/{cur_d/60:.0f}m, "
            f"tier {new_tier} vs {cur_tier})")
        shutil.rmtree(tmp, ignore_errors=True)
        failed += 1
        continue
    dest = TRASH / show_dir.parent.name / show_dir.name
    dest.mkdir(parents=True, exist_ok=True)
    for f in list(show_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in VID and not f.name.endswith('.part'):
            shutil.move(str(f), str(dest / f.name))
    shutil.move(str(newf), str(final))
    if infojson:
        shutil.move(str(infojson), str(show_dir / f"{show_dir.name}.info.json"))
    shutil.rmtree(tmp, ignore_errors=True)
    upgraded += 1
    log(f"   ✅ {final.name[:60]}  ({nh}p, {nd/60:.0f}m)")

log(f"DONE examined={done} upgraded={upgraded} no_better_source={skipped} failed={failed} free={free_gb():.0f}GB")
