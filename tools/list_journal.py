#!/usr/bin/env python3
"""Lists the journals matching a prefix, with their first entry (lowest stage).

  tes3conv Bloodmoon.esm bloodmoon.json
  python tools/list_journal.py bloodmoon.json co_ > co_journals.txt
"""
import json
import sys

path, prefix = sys.argv[1], sys.argv[2].lower()
journals, cur = {}, None
for r in json.load(open(path, encoding='utf-8')):
    t = r.get('type')
    if t == 'Dialogue':
        cur = r.get('id') if str(r.get('dialogue_type', '')).lower() == 'journal' else None
    elif t == 'DialogueInfo' and cur and cur.lower().startswith(prefix):
        stage = (r.get('data') or {}).get('disposition')
        if isinstance(stage, int):
            journals.setdefault(cur, []).append((stage, (r.get('text') or '').strip().replace('\n', ' ')))
for qid in sorted(journals, key=str.lower):
    stage, text = min(journals[qid], key=lambda x: x[0])
    print(f'{qid} (stage {stage}, {len(journals[qid])} entries): {text[:200]}')
