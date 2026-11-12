#!/usr/bin/env python3
"""Exclusive journal groups from quest_tree.json (tools gen_tree.py / UESP).

A UESP quest page lists ALL the journals of a quest, branch variants included
(`|ID=BM_Airship, BM_Airship_a, BM_Airship_c`). When a page has >= 2 journals that can
complete (non-empty completion_stages), at most one of them can in a playthrough: they are
an exclusive group (data/quest_exclusive.yaml), whatever their naming. This replaces the
name heuristic of gen_variant_exclusive.py, which only sees `_a/_b` suffixes.

  python tools/gen_exclusive_from_tree.py uesp_tree_out/quest_tree.json            # report
  python tools/gen_exclusive_from_tree.py uesp_tree_out/quest_tree.json --apply
Then: python tools/gen_lua.py && python tools/install_apworld.py

Review the report: a page that mixes a parent journal with its branches (e.g. a main
journal + `_a` / `_b`) is grouped as a whole, which is safe (never a dead check) but sends
the parent's check early; split it by hand in quest_exclusive.yaml if that matters.
"""
import argparse, json, pathlib, yaml

ap = argparse.ArgumentParser()
ap.add_argument('tree')
ap.add_argument('--data', default='data')
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()
data = pathlib.Path(args.data)

tree = json.loads(pathlib.Path(args.tree).read_text(encoding='utf-8'))
names = set(yaml.safe_load((data / 'quest_names.yaml').read_text(encoding='utf-8')) or {})
existing = yaml.safe_load((data / 'quest_exclusive.yaml').read_text(encoding='utf-8')) or []

# union-find over existing groups + new ones (a journal is in ONE group)
parent = {}
def find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x
def union(a, b):
    parent[find(a)] = find(b)

before = {}
for g in existing:
    for q in g:
        union(q, g[0])
before_groups = {frozenset(g) for g in existing}

new_pages = []
for origin, lines in tree.items():
    for line, quests in lines.items():
        for qname, q in quests.items():
            comp = q.get('completion_stages') or {}
            ids = [i.lower() for i in q.get('ids', []) if i.lower() in names]
            can = [i for i in ids if comp.get(i) or comp.get(i.upper())]
            if len(can) >= 2:
                new_pages.append((origin, line, qname, can))
                for i in can[1:]:
                    union(i, can[0])

groups = {}
for q in list(parent):
    groups.setdefault(find(q), set()).add(q)
final = [sorted(g) for g in groups.values() if len(g) >= 2]
added = [g for g in final if frozenset(g) not in before_groups]
print(f'{len(new_pages)} pages with >= 2 journals that can complete; '
      f'{len(added)} new / extended groups')
for g in sorted(added):
    print('  -', ', '.join(g))

if args.apply and added:
    # rewrite only the groups that changed: drop old groups absorbed by a new one
    absorbed = {frozenset(o) for o in existing for g in added if set(o) <= set(g)}
    txt = (data / 'quest_exclusive.yaml').read_text(encoding='utf-8').splitlines()
    keep = []
    for line in txt:
        s = line.strip()
        if s.startswith('- [') and s.endswith(']'):
            members = frozenset(x.strip() for x in s[3:-1].split(','))
            if members in absorbed:
                continue
        keep.append(line)
    keep.append('\n# --- added by tools/gen_exclusive_from_tree.py (UESP pages with several journals) ---')
    keep += ['- [' + ', '.join(g) + ']' for g in sorted(added)]
    (data / 'quest_exclusive.yaml').write_text('\n'.join(keep) + '\n', encoding='utf-8')
    print('quest_exclusive.yaml updated')
