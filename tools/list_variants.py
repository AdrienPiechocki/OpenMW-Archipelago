#!/usr/bin/env python3
"""Lists families of journals that look like variants / branches of the same quest
(bm_airship, bm_airshipa, bm_airshipc / bm_bearhunt1, bm_bearhunt2 ...), with the
first entry of each, to decide which ones are mutually exclusive.

  python tools/list_variants.py morrowind.json tribunal.json bloodmoon.json > variants.txt
Then put the exclusive sets in data/quest_exclusive.yaml.
"""
import collections
import json
import re
import sys

journals, cur = {}, None
for path in sys.argv[1:]:
    for r in json.load(open(path, encoding='utf-8')):
        t = r.get('type')
        if t == 'Dialogue':
            cur = r.get('id') if str(r.get('dialogue_type', '')).lower() == 'journal' else None
            if cur:
                journals.setdefault(cur.lower(), (cur, None, ''))
        elif t == 'DialogueInfo' and cur:
            stage = (r.get('data') or {}).get('disposition')
            qid, best, _ = journals[cur.lower()]
            if isinstance(stage, int) and (best is None or stage < best):
                journals[cur.lower()] = (qid, stage, (r.get('text') or '').strip().replace('\n', ' '))

def strip(key):
    return re.sub(r'(_?\d+[a-z]?|_?[a-z]|_?(quit|not))$', '', key) or key


stems = {strip(k) for k in journals}
fam = collections.defaultdict(list)
for key, (qid, _, text) in journals.items():
    # the base journal (bm_airship) joins its variants (bm_airshipa, bm_airshipc)
    fam[key if key in stems else strip(key)].append((key, text))
for stem in sorted(fam):
    if len(fam[stem]) > 1:
        print(f'## {stem}')
        for key, text in sorted(fam[stem]):
            print(f'  {key}: {text[:110]}')
