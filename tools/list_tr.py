#!/usr/bin/env python3
"""Inspect a Tamriel Rebuilt dump (tes3conv TR_Mainland.esm tr_mainland.json) to fill in
data/tr_categories.yaml and the TR entries of data/goals.yaml.

  python tools/list_tr.py tamriel_data.json tr_mainland.json --factions   # faction ids, names, rank lists
  python tools/list_tr.py tr_mainland.json --journals   # journals by faction token + group
"""
import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quest_groups import load_tr_categories, tr_group  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('esm_json', nargs='+', help='tamriel_data.json [tr_mainland.json]')
    ap.add_argument('--factions', action='store_true')
    ap.add_argument('--journals', action='store_true')
    ap.add_argument('--grep', default='', help='filter faction ids / names (case-insensitive)')
    args = ap.parse_args()
    records = []
    for path in args.esm_json:
        records += json.load(open(path, encoding='utf-8'))
    flt = args.grep.lower()

    if args.factions:
        print('faction id | name | ranks (index: name)  -> goals.yaml: faction = lowercase id, rank = leader index + 1')
        for r in records:
            if r.get('type') != 'Faction':
                continue
            fid, name = str(r.get('id', '')), str(r.get('name', ''))
            if flt and flt not in fid.lower() and flt not in name.lower():
                continue
            ranks = r.get('rank_names') or r.get('ranks') or []
            print(f'{fid.lower()} | {name} | {len(ranks)} ranks: ' +
                  ', '.join(f'{i + 1}:{n}' for i, n in enumerate(ranks)))

    if args.journals:
        cats = load_tr_categories()
        by_group = collections.defaultdict(list)
        for r in records:
            if r.get('type') == 'Dialogue' and str(r.get('dialogue_type', '')).lower() == 'journal' and r.get('id'):
                q = str(r['id'])
                by_group[tr_group(q, cats)].append(q)
        for g in sorted(by_group):
            print(f'== {g} ({len(by_group[g])})')
            for q in sorted(by_group[g], key=str.lower):
                print('  ', q)
        tok = collections.Counter(t for g, qs in by_group.items() if g == 'tr_side'
                                  for q in qs for t in q.lower().split('_')[2:4])
        print('\nMost common tokens left in tr_side (candidates for faction_tokens):')
        print(', '.join(f'{t}({n})' for t, n in tok.most_common(30)))


if __name__ == '__main__':
    main()
