#!/usr/bin/env python3
"""Find every ESM dialogue/script that references a given item and print
its context: journal ids, item filters, and the NPC executing the
RemoveItem/AddItem/GetItemCount.

This is the tool to run when you suspect a false positive in
`needs_item` (e.g. an item attributed to a quest because a multi-journal
dialogue shares it, or because a *different* NPC than the quest giver
consumes it).

Usage:
  python tools/diagnose_item.py bk_a1_1_caiuspackage
  python tools/diagnose_item.py TR_m4_HH_GavrosStatue --esm-json build/morrowind.json build/tr_mainland.json
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_quest_items as gqi


def _actors_of(info):
    """Return the list of Speaker/Actor filters of a DialogueInfo record.

    The export format varies: filters can be a list of dicts with a
    'function' key ('Speaker', 'Actor', ...) or a list of [function, value]
    pairs. We return a list of strings (the NPC names / ids).
    """
    out = []
    for f in gqi._records_field(info, 'filters', 'conditions'):
        if isinstance(f, dict):
            fn = str(f.get('function', f.get('type', ''))).lower()
            if fn in ('speaker', 'actor') and f.get('id'):
                out.append(str(f['id']))
        elif isinstance(f, (list, tuple)) and len(f) >= 2:
            if str(f[0]).lower() in ('speaker', 'actor'):
                out.append(str(f[1]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('item')
    ap.add_argument('--esm-json', nargs='+', default=[
        'build/morrowind.json', 'build/tribunal.json', 'build/bloodmoon.json',
        'build/tr_mainland.json', 'build/tamriel_data.json'])
    ap.add_argument('--context', type=int, default=0,
                    help='number of lines of context around each match')
    args = ap.parse_args()
    target = args.item.lower()
    found_any = False

    for p in args.esm_json:
        try:
            data = json.load(open(p))
        except FileNotFoundError:
            continue
        for r in data:
            t = str(r.get('type', ''))
            if t not in ('DialogueInfo', 'Script'):
                continue
            text = (r.get('script_text') or r.get('text') or '')
            if target not in text.lower():
                continue
            found_any = True
            journals = gqi.journal_quests(text) | gqi.filter_journals(r)
            filters = gqi.filter_items(r)
            has_filter = any(target in f.lower() for f in filters)
            actors = _actors_of(r) if t == 'DialogueInfo' else []

            # Collect the actual matches with context.
            matches = []
            for label, pat in (('AddItem', gqi.PAT_ADD),
                               ('RemoveItem', gqi.PAT_REMOVE),
                               ('GetItemCount', gqi.PAT_COUNT)):
                for m in pat.finditer(text):
                    if target not in m.group(1).lower():
                        continue
                    matches.append((label, m.group(0), m.start()))

            print(f"=== {p} | {t} | id={r.get('id')} ===")
            print(f"    journals={sorted(journals)}")
            print(f"    actors={actors}")
            print(f"    item_filters={filters}")
            print(f"    has_filter_for_target={has_filter}")
            for label, text_match, _pos in matches:
                print(f"    {label}: {text_match}")
            if args.context > 0 and matches:
                for _label, _m, pos in matches:
                    start = max(0, pos - args.context * 80)
                    end = min(len(text), pos + args.context * 80)
                    snippet = text[start:end].replace('\n', ' | ')
                    print(f"    ...{snippet}...")
            print()

    if not found_any:
        print(f'No dialogue/script references {target!r}.')


if __name__ == '__main__':
    main()
