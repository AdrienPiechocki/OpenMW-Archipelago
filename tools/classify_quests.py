#!/usr/bin/env python3
"""Ajoute/met a jour le champ `group` dans data/quests.yaml,
data/quest_completions.yaml et data/quest_finals.yaml, et ecrit un rapport
data/quest_groups_report.txt (repartition par prefixe et par groupe).

Usage : python tools/classify_quests.py [--data data]
"""
import argparse
import collections
import pathlib
import re
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quest_groups import classify, load_overrides  # noqa: E402


def qid_of(row):
    if 'trigger' in row:
        return row['trigger']['quest']
    return row['quest']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default='data')
    args = ap.parse_args()
    data = pathlib.Path(args.data)
    overrides = load_overrides(data / 'quest_groups_override.yaml')

    by_quest = {}
    for name in ('quests.yaml', 'quest_completions.yaml', 'quest_finals.yaml'):
        p = data / name
        if not p.exists():
            continue
        rows = yaml.safe_load(p.read_text(encoding='utf-8')) or []
        for r in rows:
            g = classify(qid_of(r), overrides)
            r['group'] = g
            by_quest[str(qid_of(r)).lower()] = g
        p.write_text(yaml.safe_dump(rows, sort_keys=False, allow_unicode=True), encoding='utf-8')

    groups = collections.Counter(by_quest.values())
    prefixes = collections.defaultdict(collections.Counter)
    for q, g in by_quest.items():
        prefixes[g][re.split(r'[_\-]', q)[0]] += 1
    lines = ['Quetes par groupe :']
    for g, n in sorted(groups.items()):
        lines.append(f'  {g:16} {n:4}   prefixes: ' +
                     ', '.join(f'{p}({c})' for p, c in sorted(prefixes[g].items())))
    lines.append('')
    lines.append('Quetes classees misc (seules sources de checks) :')
    lines += [f'  {q}' for q, g in sorted(by_quest.items()) if g == 'misc']
    (data / 'quest_groups_report.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines[:len(groups) + 1]))


if __name__ == '__main__':
    main()
