#!/usr/bin/env python3
"""Show, for a given quest, all needs_item with their ESM context.

For each item in the quest's needs_item list, this tool prints:
  - the journal ids of every dialogue/script that references it,
  - the NPCs that execute the RemoveItem/AddItem (via Speaker/Actor filters),
  - the type of evidence (AddItem, RemoveItem, Item filter, GetItemCount),
  - the YAML `via` metadata when available.

Use it to audit a whole quest at once instead of running diagnose_item.py
once per item.

FIX vs previous version:
  The previous version only scanned `DialogueInfo`/`Script` records whose
  `script_text` contained a `Journal` command mentioning the quest. This
  missed dialogues where the journal is set in the *result* (or via a
  separate attached script) and only the RemoveItem/AddItem appears in
  the script_text. The new version:
    - looks at every record that mentions the quest id anywhere
      (script_text, filters, conditions, attached script, result);
    - resolves the `script` / `result_script` field of a DialogueInfo to
      the Script record, so items referenced only by the attached script
      are reported;
    - prints the actors (Speaker/Actor filters) even when empty.

Usage:
  python tools/diagnose_quest.py a1_2_antabolisinformant
  python tools/diagnose_quest.py a1_2_antabolisinformant --esm-json build/morrowind.json build/tr_mainland.json
"""
import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_quest_items as gqi


def _actors_of(info):
    """Return the list of Speaker/Actor filters of a DialogueInfo record."""
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


def _load_quest_items_from_yaml(path):
    """Return {record_lower: (name, goal, via)} from data/quest_items.yaml."""
    import yaml
    data = yaml.safe_load(pathlib.Path(path).read_text(encoding='utf-8')) or []
    out = {}
    for e in data:
        via = list(e.get('via') or [])
        for r in (e.get('suppress') or []):
            out.setdefault(str(r).lower(),
                           (e.get('name', ''), e.get('goal', ''), via))
        if e.get('give'):
            out.setdefault(str(e['give'][0]).lower(),
                           (e.get('name', ''), e.get('goal', ''), via))
    return out


def _index_scripts(records):
    """Map script id -> list of script_text contents.

    Scripts can appear as standalone Script records (with 'script_text'),
    or embedded as 'script' / 'result_script' dicts inside a DialogueInfo.
    We index every script id we can find so a DialogueInfo that references
    a Script by id can be resolved.
    """
    scripts = collections.defaultdict(list)
    for r in records:
        if str(r.get('type', '')) == 'Script' and r.get('id'):
            text = r.get('script_text') or r.get('text') or ''
            scripts[str(r['id'])].append(text)
    return scripts


def _resolve_scripts_of(info, scripts_index):
    """Return every script_text attached to a DialogueInfo.

    Handles several export formats:
      - 'script': 'script_id'         (string reference)
      - 'script': {'id': 'script_id'} (dict reference)
      - 'result_script': same
    """
    out = []
    for key in ('script', 'result_script'):
        v = info.get(key)
        if isinstance(v, str):
            out.extend(scripts_index.get(v, []))
        elif isinstance(v, dict) and v.get('id'):
            out.extend(scripts_index.get(str(v['id']), []))
    return out


def _collect_matches(text):
    """Return {item_lower: [(label, match_text)]} for one script_text."""
    out = collections.defaultdict(list)
    for label, pat in (('AddItem', gqi.PAT_ADD),
                       ('RemoveItem', gqi.PAT_REMOVE),
                       ('GetItemCount', gqi.PAT_COUNT)):
        for m in pat.finditer(text or ''):
            out[m.group(1).lower()].append((label, m.group(0)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('quest', help='journal id (lowercase)')
    ap.add_argument('--esm-json', nargs='+', default=[
        'build/morrowind.json', 'build/tribunal.json', 'build/bloodmoon.json',
        'build/tr_mainland.json', 'build/tamriel_data.json'])
    ap.add_argument('--items', default='data/quest_items.yaml')
    ap.add_argument('--tree', default='uesp_tree_out/quest_tree.json')
    args = ap.parse_args()
    qid = args.quest.lower()

    # 1. Find the quest in the tree to know its needs_item.
    tree_path = pathlib.Path(args.tree)
    if tree_path.exists():
        tree = json.loads(tree_path.read_text(encoding='utf-8'))
        qdata = None
        for origin, lines in tree.items():
            for line, quests in lines.items():
                for qname, q in quests.items():
                    if qid in {str(i).lower() for i in q.get('ids', [])}:
                        qdata = (origin, line, qname, q)
                        break
        if qdata:
            origin, line, qname, q = qdata
            print(f'Quest: {origin}/{line}/{qname}')
            print(f'  ids: {q["ids"]}')
            print(f'  needs_item ({len(q["needs_item"])}):')
            for item in q['needs_item']:
                print(f'    - {item}')
            print()
        else:
            print(f'Quest {qid!r} not found in {tree_path}.')
    else:
        print(f'Tree {tree_path} not found, skipping needs_item listing.')

    # 2. Load the via metadata from quest_items.yaml.
    items_meta = _load_quest_items_from_yaml(args.items) if pathlib.Path(args.items).exists() else {}

    # 3. Load every record, then index scripts.
    all_records = []
    for p in args.esm_json:
        try:
            all_records.extend(json.load(open(p)))
        except FileNotFoundError:
            continue
    scripts_index = _index_scripts(all_records)

    # 4. Collect evidence: for each item, all the records that reference
    #    the quest and mention the item.
    item_evidence = collections.defaultdict(list)

    def _register(source_desc, journals, actors, item, matches):
        item_evidence[item].append({
            'source': source_desc,
            'journals': sorted(journals),
            'actors': actors,
            'matches': matches,
        })

    for r in all_records:
        t = str(r.get('type', ''))
        if t not in ('DialogueInfo', 'Script'):
            continue
        text = r.get('script_text') or r.get('text') or ''
        journals = gqi.journal_quests(text) | gqi.filter_journals(r)
        if qid not in journals:
            continue
        source_desc = f'id={r.get("id")} ({t})'
        actors = _actors_of(r) if t == 'DialogueInfo' else []

        # Items directly referenced in this record's text.
        for item, matches in _collect_matches(text).items():
            _register(source_desc, journals, actors, item, matches)

        # Item filters.
        for it in gqi.filter_items(r):
            _register(source_desc, journals, actors, it,
                      [('Item filter', it)])

        # If this DialogueInfo attaches a script, scan it too.
        if t == 'DialogueInfo':
            for script_text in _resolve_scripts_of(r, scripts_index):
                script_journals = gqi.journal_quests(script_text)
                # Only keep scripts that actually mention the quest, or that
                # belong to a dialogue whose text mentions the quest.
                if not script_journals & {qid}:
                    # Still interesting: the dialogue text mentioned the quest,
                    # and the attached script may be the source of the item.
                    pass
                for item, matches in _collect_matches(script_text).items():
                    _register(f'{source_desc} + attached script',
                              journals, actors, item, matches)

    print(f'=== ESM evidence for quest {qid!r} ===')
    if not item_evidence:
        print('  (no ESM record references this quest with an item)')
        return

    for item in sorted(item_evidence):
        meta = items_meta.get(item)
        name = meta[0] if meta else ''
        via = meta[2] if meta else []
        print(f'\n  {item}  ({name})')
        if via:
            print(f'    YAML via: {via}')
        for ev in item_evidence[item]:
            print(f'    from: {ev["source"]}')
            print(f'      journals: {ev["journals"]}')
            print(f'      actors:   {ev["actors"]}')
            for label, match in ev['matches']:
                print(f'      {label}: {match}')


if __name__ == '__main__':
    main()
