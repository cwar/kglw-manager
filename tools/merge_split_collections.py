"""Merge tour collections that exist twice under slash and dash spellings.

kglw.net names tours like "2024 USA/Canada - Summer" but a directory cannot
contain "/", so it is stored as "2024 USA-Canada - Summer". Code that derived
a collection name from the directory created a second collection for the same
tour, splitting its shows between the two.

The slash form matches the API and is kept; members of the dash form are moved
across and the emptied collection is removed.
"""
import sys
from collections import defaultdict
from kglw_manager.plex_manager import PlexManager

APPLY = "--apply" in sys.argv
pm = PlexManager()

groups = defaultdict(list)
for c in pm.library.collections():
    c.reload()
    groups[c.title.replace('/', '-').strip().lower()].append(c)

merged = moved = 0
for key, colls in sorted(groups.items()):
    if len(colls) < 2:
        continue
    # keep the API spelling (contains "/"); fall back to whichever holds most
    keep = next((c for c in colls if '/' in c.title), None)
    if keep is None:
        keep = max(colls, key=lambda c: c.childCount)
    losers = [c for c in colls if c is not keep]
    print(f"\n{keep.title}  (keeping, {keep.childCount} items)")
    for loser in losers:
        print(f"   merging '{loser.title}' ({loser.childCount} items)")
        if not APPLY:
            moved += loser.childCount
            continue
        for it in list(loser.items()):
            try:
                it.addCollection(keep.title)
                it.removeCollection(loser.title)
                moved += 1
            except Exception as e:
                print(f"      error on {it.title[:40]}: {str(e)[:60]}")
        loser.reload()
        if loser.childCount == 0:
            loser.delete()
            merged += 1
            print(f"   removed empty '{loser.title}'")
        else:
            print(f"   '{loser.title}' still has {loser.childCount} - left in place")

print(("APPLIED" if APPLY else "DRY RUN") + f": moved {moved} items, removed {merged} duplicate collections")
