"""Give every collection a consistent, chronological sort title.

Collections were sorting wrongly because only some had a "_" prefixed sort
title - the ones whose names contain a "/" had been skipped - and "_" sorts
after digits, so those jumped ahead of every other tour.

Sorting on the tour's first show date fixes both problems at once: it is
consistent across every collection, and it orders tours within a year by when
they actually happened rather than alphabetically.
"""
import re, sys
from kglw_manager.plex_manager import PlexManager

APPLY = "--apply" in sys.argv
DATE = re.compile(r'(\d{4})[ -](\d{2})[ -](\d{2})')

# Catch-all collections span the whole timeline, so a "first show date" would
# park them mid-list. They belong at the end.
CATCH_ALL = {'not part of a tour', 'other', 'live', 'unsorted'}

pm = PlexManager()
rows = []
for c in pm.library.collections():
    c.reload()
    dates = []
    for it in c.items():
        m = DATE.search(it.title or '')
        if m:
            dates.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
        elif getattr(it, 'originallyAvailableAt', None):
            dates.append(it.originallyAvailableAt.strftime('%Y-%m-%d'))
    if c.title.strip().lower() in CATCH_ALL:
        sort_key = f"zzzz {c.title}"
    elif dates:
        sort_key = min(dates)
    else:
        # collections holding nothing dateable belong at the end too
        sort_key = f"zzzz {c.title}"
    rows.append((c, sort_key))

rows.sort(key=lambda r: r[1])
print(f"{'sort key':14}{'collection':46}{'was'}")
changed = 0
for c, key in rows:
    was = c.titleSort or '(none)'
    mark = '' if was == key else '  <-- changing'
    print(f"{key:14}{c.title[:46]:46}{was[:26]}{mark}")
    if was != key:
        changed += 1
        if APPLY:
            try:
                c.editSortTitle(key)
                c.edit(**{'titleSort.locked': 1})
            except Exception as e:
                print(f"    error: {str(e)[:70]}")

print(("APPLIED" if APPLY else "DRY RUN") + f": {changed} collections needed a new sort title")
