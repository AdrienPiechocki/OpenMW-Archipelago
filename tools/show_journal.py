#!/usr/bin/env python3
"""Prints EVERY stage of the journals whose id starts with a prefix (stage, finish flag, text).

  python tools/show_journal.py build/tr_mainland.json tr_necmq_
"""
import json
import sys

path, prefix = sys.argv[1], sys.argv[2].lower()
cur, rows = None, {}
for r in json.load(open(path, encoding='utf-8')):
    t = r.get('type')
    if t == 'Dialogue':
        cur = r.get('id') if str(r.get('dialogue_type', '')).lower() == 'journal' else None
    elif t == 'DialogueInfo' and cur and cur.lower().startswith(prefix):
        st = (r.get('data') or {}).get('disposition')
        if isinstance(st, int):
            rows.setdefault(cur, []).append((st, bool(r.get('quest_finish')), (r.get('text') or '').strip().replace('\n', ' ')))
for q in sorted(rows, key=str.lower):
    print(f'== {q}')
    for st, fin, text in sorted(rows[q]):
        print(f'  {st:>4}{" FIN" if fin else "    "}  {text[:260]}')
