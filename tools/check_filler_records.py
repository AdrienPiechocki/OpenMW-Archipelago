#!/usr/bin/env python3
"""Checks that every record id given by the filler / traps of mod/scripts/ap/items.lua exists in the ESMs.

Usage (tes3conv JSON exports, like the other tools):
    python3 tools/check_filler_records.py morrowind.json [tribunal.json bloodmoon.json ...]
"""
import json, pathlib, re, sys

root = pathlib.Path(__file__).resolve().parent.parent
lua = (root / 'mod/scripts/ap/items.lua').read_text(encoding='utf-8')
wanted = {}
for m in re.finditer(r"\[(7701\d{3})\]\s*=\s*\{\s*'([^']+)'", lua):      # GIVE and SUMMONS tables
    wanted[m.group(2).lower()] = int(m.group(1))

known = set()
for path in sys.argv[1:]:
    for rec in json.load(open(path, encoding='utf-8')):
        if isinstance(rec, dict) and 'id' in rec:
            known.add(str(rec['id']).lower())
if not known:
    sys.exit(__doc__)
missing = {r: i for r, i in wanted.items() if r not in known}
for r, i in sorted(missing.items(), key=lambda x: x[1]):
    print(f'MISSING {r!r} (AP item {i})')
print(f'{len(wanted) - len(missing)}/{len(wanted)} record ids found')
sys.exit(1 if missing else 0)
