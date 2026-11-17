#!/usr/bin/env python3
"""Adds to data/quest_exclusive.yaml the journal families that look like BRANCHES
of the same quest, for every journal in data/quest_names.yaml (vanilla, Tribunal,
Bloodmoon, Tamriel Rebuilt):
  - lettered variants: suffix _a/_b/_c/_d or a/b/c/d appended to a base journal
  - numeric variants:  suffix 1/2/3... or _1/_2/_3... appended to a base journal

Caution: numeric suffixes are often chained steps (foo1 -> foo2 -> foo3), not
branches. They are written in their own section so they can be reviewed/pruned.
Use --no-digits to skip them.

  python tools/gen_variant_exclusive.py              # dry run
  python tools/gen_variant_exclusive.py --apply      # appends to quest_exclusive.yaml
  python tools/gen_variant_exclusive.py --no-digits  # lettered variants only
Then: python tools/gen_lua.py && python tools/install_apworld.py
"""
import argparse, collections, pathlib, re, yaml

ap = argparse.ArgumentParser()
ap.add_argument('--data', default='data')
ap.add_argument('--apply', action='store_true')
ap.add_argument('--no-digits', action='store_true',
                help='do not group numeric-suffix variants (foo1, foo2...)')
args = ap.parse_args()
data = pathlib.Path(args.data)

names = set(yaml.safe_load((data / 'quest_names.yaml').read_text(encoding='utf-8')) or {})
existing = yaml.safe_load((data / 'quest_exclusive.yaml').read_text(encoding='utf-8')) or []
already = {q for g in existing for q in g}

LETTER = re.compile(r'^(?P<stem>.+?)_?(?P<suf>[a-d])$')
DIGIT = re.compile(r'^(?P<stem>.+?)_?(?P<suf>\d+)$')


def build_groups(pattern, taken):
    """Group journals by stem; returns sorted lists of members, skipping any group
    that overlaps `taken` (already-known exclusive groups or groups found earlier)."""
    fam = collections.defaultdict(set)
    for n in names:
        m = pattern.match(n)
        if m:
            fam[m.group('stem')].add(n)
    groups = []
    for stem, members in sorted(fam.items()):
        full = set(members)
        # the stem journal itself counts as a member of the family
        if stem in names:
            full.add(stem)
        if len(full) < 2:
            continue
        # a lone suffixed member next to nothing else is not a branch
        if len(members) == 1 and stem not in names:
            continue
        if full & taken:
            continue
        groups.append(sorted(full))
    return groups


letter_groups = build_groups(LETTER, already)
taken = already | {q for g in letter_groups for q in g}
digit_groups = [] if args.no_digits else build_groups(DIGIT, taken)

print(f'{len(letter_groups)} new lettered-variant groups')
for g in letter_groups:
    print('  -', ', '.join(g))
if not args.no_digits:
    print(f'\n{len(digit_groups)} new numeric-variant groups (to review: may be chained steps)')
    for g in digit_groups:
        print('  -', ', '.join(g))

if args.apply and (letter_groups or digit_groups):
    with open(data / 'quest_exclusive.yaml', 'a', encoding='utf-8') as f:
        if letter_groups:
            f.write('\n# --- added by tools/gen_variant_exclusive.py (lettered variants: _a/_b/...) ---\n')
            for g in letter_groups:
                f.write('- [' + ', '.join(g) + ']\n')
        if digit_groups:
            f.write('\n# --- added by tools/gen_variant_exclusive.py (numeric variants: 1/2/3...) ---\n')
            for g in digit_groups:
                f.write('- [' + ', '.join(g) + ']\n')
    print('appended to quest_exclusive.yaml')
