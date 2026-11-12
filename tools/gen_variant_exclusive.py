#!/usr/bin/env python3
"""Adds to data/quest_exclusive.yaml the journal families that look like BRANCHES
of the same quest (suffix _a/_b/_c/_d or a/b/c/d appended to a base journal), for every
journal in data/quest_names.yaml (vanilla, Tribunal, Bloodmoon, Tamriel Rebuilt).

Numeric suffixes (foo1, foo2) are NOT grouped automatically: they are often chained
steps, not branches. They are printed for manual review.

  python tools/gen_variant_exclusive.py          # dry run
  python tools/gen_variant_exclusive.py --apply  # appends to quest_exclusive.yaml
Then: python tools/gen_lua.py && python tools/install_apworld.py
"""
import argparse, collections, pathlib, re, yaml

ap = argparse.ArgumentParser()
ap.add_argument('--data', default='data')
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()
data = pathlib.Path(args.data)

names = set(yaml.safe_load((data / 'quest_names.yaml').read_text(encoding='utf-8')) or {})
existing = yaml.safe_load((data / 'quest_exclusive.yaml').read_text(encoding='utf-8')) or []
already = {q for g in existing for q in g}

LETTER = re.compile(r'^(?P<stem>.+?)_?(?P<suf>[a-d])$')
fam = collections.defaultdict(set)
for n in names:
    m = LETTER.match(n)
    if not m:
        continue
    stem = m.group('stem')
    # the suffix must really be a variant: the stem journal exists, or at least
    # two lettered siblings exist (a/b)
    fam[stem].add(n)
groups = []
for stem, members in sorted(fam.items()):
    full = set(members)
    if stem in names:
        full.add(stem)
    # also accept stem + '_' form
    if len(full) < 2:
        continue
    # a lone lettered member next to nothing else is not a branch
    if len(members) == 1 and stem not in names:
        continue
    if full & already:
        continue
    groups.append(sorted(full))

digit = collections.defaultdict(set)
for n in names:
    m = re.match(r'^(.+?)_?(\d)$', n)
    if m:
        digit[m.group(1)].add(n)

print(f'{len(groups)} new lettered-variant groups')
for g in groups:
    print('  -', ', '.join(g))
if args.apply and groups:
    with open(data / 'quest_exclusive.yaml', 'a', encoding='utf-8') as f:
        f.write('\n# --- added by tools/gen_variant_exclusive.py (lettered variants: _a/_b/...) ---\n')
        for g in groups:
            f.write('- [' + ', '.join(g) + ']\n')
    print('appended to quest_exclusive.yaml')
