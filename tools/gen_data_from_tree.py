#!/usr/bin/env python3
"""Generate the Archipelago data files from the canonical quest tree.

`data/quest_tree.json` is the source of truth (see tools/rebase_quest_tree.py).
This script writes the YAML files consumed by the apworld and by tools/gen_lua.py:

  data/quest_completions.yaml   one location per journal (successful or not)
  data/quest_finals.yaml        successful stages + failing stages (`fail`)
  data/quest_items.yaml         progression items (needs_item)
  data/quest_rewards.yaml       unique rewards

Readable quest names stay in the curated data/quest_names.yaml (tracked); they
are copied into the tree as `loc_names` and used for the generated locations.

Usage (from the repository root):

  python tools/gen_data_from_tree.py
  python tools/gen_data_from_tree.py --check      # validate only, exit 1 on error
"""
import argparse
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quest_tree import iter_pages, load_tree  # noqa: E402


def _ints(values):
    out = []
    for v in values or []:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            pass
    return sorted(set(out))


def _lower_map(value):
    return {str(k).lower(): v for k, v in (value or {}).items()}


def build(tree):
    """Return (completions, finals, items, rewards, names, problems)."""
    comps, finals, items, rewards = [], [], [], []
    names = {}
    item_rows, reward_rows = [], []
    journals = {}
    seen_items = set()
    seen_rewards = set()
    problems = []

    # ---- aggregate the pages ---------------------------------------------
    # A journal can be listed on several UESP pages (redirects, shared quest
    # pages): its stages are the union of every page, like tools/
    # gen_lua_from_tree.py always did.
    for _origin, _line, page_name, page in iter_pages(tree):
        # Location identity uses the Archipelago region, not the UESP lore
        # region (regions.py only knows the progression chain).
        ap_region = 'Seyda Neen'
        groups = _lower_map(page.get('groups'))
        fails = _lower_map(page.get('fail'))
        loc_ids = _lower_map(page.get('loc_ids'))
        loc_names = _lower_map(page.get('loc_names'))
        regions = _lower_map(page.get('regions'))
        stages_by_journal = _lower_map(page.get('completion_stages'))

        for jid in list(stages_by_journal) + list(fails) + list(loc_ids):
            j = str(jid).lower()
            rec = journals.setdefault(j, {
                'stages': set(), 'fail': set(), 'ids': [], 'name': None,
                'group': None, 'region': None,
            })
            rec['stages'] |= set(_ints(stages_by_journal.get(j)))
            rec['fail'] |= set(_ints(fails.get(j)))
            ids = [int(x) for x in loc_ids.get(j) or []]
            if ids and not rec['ids']:
                rec['ids'] = ids
            if not rec['name']:
                rec['name'] = str(loc_names.get(j) or page_name)
            if not rec['group']:
                rec['group'] = str(groups.get(j) or 'misc')
            if not rec['region']:
                rec['region'] = str(regions.get(j) or ap_region)

        for rec in page.get('needs_item') or []:
            rows = (page.get('needs_item_meta') or {}).get(str(rec))
            if isinstance(rows, dict):
                rows = [rows]
            if not rows:
                problems.append(f'item without metadata: {rec} ({page_name})')
                continue
            for meta in rows:
                if not meta.get('id'):
                    problems.append(f'item without Archipelago id: {rec} ({page_name})')
                    continue
                # A record shared by several goals has one row per goal (with
                # the same id but a different name): keep every row. Only drop
                # the exact same row attached to more than one page.
                key = (meta.get('id'), meta.get('name'))
                if key in seen_items:
                    continue
                seen_items.add(key)
                item_rows.append(dict(meta))

        for rec in (page.get('rewards') or {}):
            rows = (page.get('rewards_meta') or {}).get(str(rec))
            if isinstance(rows, dict):
                rows = [rows]
            if not rows:
                problems.append(f'reward without metadata: {rec} ({page_name})')
                continue
            for meta in rows:
                if not meta.get('item_id') or not meta.get('loc_id'):
                    problems.append(f'reward without Archipelago id: {rec} ({page_name})')
                    continue
                key = int(meta['loc_id'])
                if key in seen_rewards:
                    continue
                seen_rewards.add(key)
                reward_rows.append((dict(meta), ap_region))

    # ---- one completion / finals row per journal -------------------------
    for j in sorted(journals):
        rec = journals[j]
        ids = rec['ids']
        if not ids:
            # No Archipelago location: the mod can never send this check.
            continue
        fail = sorted(rec['fail'])
        success = sorted(rec['stages'] - rec['fail'])
        name = str(rec['name'] or j)
        group = str(rec['group'] or 'misc')
        region = str(rec['region'] or 'Seyda Neen')
        names[j] = name
        comps.append({
            'id': ids[0],
            'name': name,
            'category': 'quest_complete',
            'trigger': {'quest': j},
            'group': group,
            'region': region,
        })
        row = {
            'quest': j,
            'stage': max(success) if success else 0,
            'stages': success,
            'fail': fail,
            'ids': ids,
            'group': group,
        }
        if not success:
            row['fail_only'] = True
        finals.append(row)

    for row in item_rows:
        items.append(row)

    for row, ap_region in reward_rows:
        q = str(row.get('quest', '')).lower()
        row['quest'] = q
        row['quest_name'] = str(row.get('quest_name') or names.get(q) or q)
        row['region'] = str(row.get('region') or ap_region)
        row['group'] = str(row.get('group') or 'misc')
        rewards.append(row)

    comps.sort(key=lambda r: int(r['id']))
    finals.sort(key=lambda r: r['quest'])
    items.sort(key=lambda r: int(r['id']))
    rewards.sort(key=lambda r: int(r['loc_id']))
    return comps, finals, items, rewards, names, problems


def _dump(path, rows, header):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'# {header}\n' + yaml.safe_dump(rows, sort_keys=False, allow_unicode=True, width=10000),
        encoding='utf-8')


def write_all(tree, data='data'):
    data = pathlib.Path(data)
    comps, finals, items, rewards, names, problems = build(tree)
    _dump(data / 'quest_completions.yaml', comps,
          'Generated from data/quest_tree.json by tools/gen_data_from_tree.py')
    _dump(data / 'quest_finals.yaml', finals,
          'Generated from data/quest_tree.json by tools/gen_data_from_tree.py')
    _dump(data / 'quest_items.yaml', items,
          'Generated from data/quest_tree.json by tools/gen_data_from_tree.py')
    _dump(data / 'quest_rewards.yaml', rewards,
          'Generated from data/quest_tree.json by tools/gen_data_from_tree.py')
    return comps, finals, items, rewards, names, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', default='data/quest_tree.json')
    ap.add_argument('--data', default='data')
    ap.add_argument('--check', action='store_true', help='validate only, do not write')
    args = ap.parse_args()

    tree = load_tree(args.tree)
    comps, finals, items, rewards, names, problems = build(tree)
    print(f'completions: {len(comps)}')
    print(f'finals:      {len(finals)} ({sum(1 for r in finals if r.get("fail_only"))} failure-only)')
    print(f'items:       {len(items)}')
    print(f'rewards:     {len(rewards)}')
    print(f'names:       {len(names)}')
    if problems:
        print(f'problems:    {len(problems)}')
        for p in problems[:40]:
            print(f'  {p}')
    if args.check:
        return 1 if problems else 0
    write_all(tree, args.data)
    print(f'data written -> {args.data}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
