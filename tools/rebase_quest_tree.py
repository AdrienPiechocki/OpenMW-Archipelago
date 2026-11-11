#!/usr/bin/env python3
"""Rebase the project data on the UESP quest tree.

Reads the tree produced by tools/scrape_uesp_quest_tree.py and the ESM-derived
data/*.yaml files, then writes the canonical tree data/quest_tree.json:

  origin -> line -> page -> {
      ids, completion_stages, fail, region, regions, triggers,
      groups, loc_ids, loc_names,
      needs_item, needs_item_meta,
      rewards, rewards_meta,
  }

The canonical tree is the base for the whole project:

  * factions / groups  : `groups[journal]` (UESP faction line + prefix fallback
                         + data/quest_groups_override.yaml)
  * quest completions  : successful stages (`completion_stages`) and failing
                         stages (`fail`, from the ESM via data/quest_finals.yaml)
  * items              : progression items (`needs_item_meta`, with their
                         Archipelago ids) and unique rewards (`rewards_meta`)

Journals known by the ESM but absent from UESP are added under the
`_esm_only` line, so no check disappears when the project switches to the tree.

Usage (from the repository root):

  python tools/rebase_quest_tree.py                       # uesp_tree_out -> data/quest_tree.json
  python tools/rebase_quest_tree.py --from-raw            # ignore the existing canonical tree
  python tools/rebase_quest_tree.py --check               # report only, do not write

After it:

  python tools/gen_lua.py --tree data/quest_tree.json --tree-sync-yaml
  python tools/install_apworld.py
"""
import argparse
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quest_tree import (ESM_ONLY_LINE, ORIGIN_KEYS, is_canonical, journal_keys,
                        load_overrides_safe, load_tree, resolve_group, save_tree)


def _load_yaml(path, default):
    p = pathlib.Path(path)
    if not p.exists():
        return default
    return yaml.safe_load(p.read_text(encoding='utf-8')) or default


def _ints(values):
    out = []
    for v in values or []:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            pass
    return sorted(set(out))


def _finals_stages(row):
    stages = _ints(row.get('stages'))
    if not stages and int(row.get('stage') or 0) > 0:
        stages = [int(row['stage'])]
    return stages


def _origin_key(origin):
    return ORIGIN_KEYS.get(str(origin).lower(), 'Morrowind')


def _infer_origin(journal):
    q = journal.lower()
    if q.startswith(('tr_m', 'tr_necmq', 'pc_m')):
        return 'tamriel_rebuilt'
    if q.startswith(('bm_', 'co_')):
        return 'bloodmoon'
    return 'morrowind'


def _new_page(name, region='Seyda Neen'):
    return {
        'ids': [],
        'completion_stages': {},
        'fail': {},
        'region': region,
        'regions': {},
        'triggers': {},
        'groups': {},
        'loc_ids': {},
        'loc_names': {},
        'needs_item': [],
        'needs_item_meta': {},
        'rewards': {},
        'rewards_meta': {},
    }


def _ensure_page_fields(page):
    page.setdefault('ids', [])
    page.setdefault('completion_stages', {})
    page.setdefault('fail', {})
    page.setdefault('regions', {})
    page.setdefault('triggers', {})
    page.setdefault('groups', {})
    page.setdefault('loc_ids', {})
    page.setdefault('loc_names', {})
    page.setdefault('needs_item', [])
    page.setdefault('needs_item_meta', {})
    page.setdefault('rewards', {})
    page.setdefault('rewards_meta', {})


def rebase(tree, data='data', check=False):
    data = pathlib.Path(data)
    finals = {str(r['quest']).lower(): r
              for r in _load_yaml(data / 'quest_finals.yaml', [])}
    comps = {str((r.get('trigger') or {}).get('quest', '')).lower(): r
             for r in _load_yaml(data / 'quest_completions.yaml', [])}
    sources = {str(k).lower(): str(v) for k, v in
               _load_yaml(data / 'quest_sources.yaml', {}).items()}
    names = {str(k).lower(): str(v) for k, v in
             _load_yaml(data / 'quest_names.yaml', {}).items()}
    items = _load_yaml(data / 'quest_items.yaml', [])
    rewards = _load_yaml(data / 'quest_rewards.yaml', [])
    overrides = load_overrides_safe(data)

    items_by_record = {}
    for row in items:
        give = row.get('give') or []
        if not give:
            continue
        rec = str(give[0]).lower()
        # The same record can be a progression item of several goals
        # ("Construction Contract" for hlaalu / redoran / telvanni / main):
        # keep every row, the item table is keyed by name.
        items_by_record.setdefault(rec, []).append(row)

    rewards_by_pair = {}
    rewards_by_record = {}
    for row in rewards:
        q = str(row.get('quest', '')).lower()
        rec = str(row.get('record', '')).lower()
        if q and rec:
            rewards_by_pair.setdefault((q, rec), row)
            rewards_by_record.setdefault(rec, []).append(row)

    seen_journals = set()
    seen_reward_pairs = set()
    report = {
        'filled_stages': [],
        'missing_item_meta': [],
        'missing_reward_meta': [],
        'items_not_in_tree': [],
        'journals_without_id': [],
        'groups': {},
    }

    # ---- enrich the pages that UESP knows --------------------------------
    for origin, line, page_name, page in _iter_pages(tree):
        _ensure_page_fields(page)
        for journal in journal_keys(page):
            seen_journals.add(journal)
            row = finals.get(journal, {})
            stages = _ints((page.get('completion_stages') or {}).get(journal))
            if not stages and row:
                filled = _finals_stages(row)
                if filled:
                    page['completion_stages'][journal] = filled
                    report['filled_stages'].append((origin, page_name, journal, filled))
            fail = _ints(row.get('fail'))
            if fail:
                page['fail'][journal] = fail
            page['groups'][journal] = resolve_group(origin, line, journal, overrides)
            comp = comps.get(journal)
            # The Archipelago region is always "Seyda Neen" (regions.py is a
            # linear progression chain): the UESP `region` is a lore region and
            # must not leak into the location identity.
            ap_region = str(comp.get('region') or 'Seyda Neen') if comp else 'Seyda Neen'
            if comp:
                page['loc_ids'][journal] = [int(comp['id'])]
                page['loc_names'][journal] = str(comp.get('name') or page_name)
                page['regions'][journal] = ap_region
            elif row.get('ids'):
                page['loc_ids'][journal] = [int(x) for x in row['ids']]
                page['loc_names'].setdefault(journal, names.get(journal) or page_name)
                page['regions'].setdefault(journal, ap_region)
            else:
                page['loc_names'].setdefault(journal, names.get(journal) or page_name)
                page['regions'].setdefault(journal, ap_region)
                report['journals_without_id'].append(journal)

        for rec in page.get('needs_item') or []:
            rows = items_by_record.get(str(rec).lower())
            if rows:
                page['needs_item_meta'][str(rec)] = [dict(r) for r in rows]
            else:
                report['missing_item_meta'].append((origin, page_name, str(rec)))

        page_journals = journal_keys(page)
        for rec in (page.get('rewards') or {}):
            rec_l = str(rec).lower()
            rows = [rewards_by_pair[(j, rec_l)] for j in page_journals
                    if (j, rec_l) in rewards_by_pair]
            # A record can be shared by quests of another page: attach every
            # row of that record (gen_data_from_tree deduplicates by loc id).
            for row in rewards_by_record.get(rec_l, []):
                if row not in rows:
                    rows.append(row)
            if rows:
                page['rewards_meta'][str(rec)] = [dict(r) for r in rows]
                for row in rows:
                    seen_reward_pairs.add((str(row.get('quest', '')).lower(), rec_l))
            else:
                report['missing_reward_meta'].append((origin, page_name, str(rec)))

    # ---- add journals that the UESP tree does not contain ----------------
    for journal, row in finals.items():
        if journal in seen_journals:
            continue
        origin = _origin_key(sources.get(journal) or _infer_origin(journal))
        comp = comps.get(journal, {})
        page_name = str(comp.get('name') or names.get(journal) or journal)
        region = str(comp.get('region') or 'Seyda Neen')
        pages = tree.setdefault(origin, {}).setdefault(ESM_ONLY_LINE, {})
        page = pages.setdefault(page_name, _new_page(page_name, region))
        _ensure_page_fields(page)
        if journal not in [str(x).lower() for x in page['ids']]:
            page['ids'].append(journal)
        stages = _finals_stages(row)
        if stages:
            page['completion_stages'][journal] = stages
        fail = _ints(row.get('fail'))
        if fail:
            page['fail'][journal] = fail
        page['groups'][journal] = resolve_group(origin, ESM_ONLY_LINE, journal, overrides)
        if comp:
            page['loc_ids'][journal] = [int(comp['id'])]
            page['loc_names'][journal] = str(comp.get('name') or page_name)
            page['regions'][journal] = str(comp.get('region') or region)
        elif row.get('ids'):
            page['loc_ids'][journal] = [int(x) for x in row['ids']]
            page['loc_names'][journal] = names.get(journal) or page_name
            page['regions'][journal] = region
        else:
            page['loc_names'][journal] = names.get(journal) or page_name
            page['regions'][journal] = region
            report['journals_without_id'].append(journal)
        seen_journals.add(journal)

    # ---- attach rewards that the UESP tree does not list -----------------
    page_by_journal = {}
    for _origin, _line, _name, page in _iter_pages(tree):
        for journal in journal_keys(page):
            page_by_journal.setdefault(journal, page)
    for row in rewards:
        q = str(row.get('quest', '')).lower()
        rec = str(row.get('record', '')).lower()
        if (q, rec) in seen_reward_pairs:
            continue
        page = page_by_journal.get(q)
        if page is None:
            # The quest itself is unknown to UESP (rare): create an ESM-only page.
            origin = _origin_key(sources.get(q) or _infer_origin(q))
            comp = comps.get(q, {})
            page_name = str(comp.get('name') or names.get(q) or q)
            pages = tree.setdefault(origin, {}).setdefault(ESM_ONLY_LINE, {})
            page = pages.setdefault(page_name, _new_page(page_name))
            _ensure_page_fields(page)
            page['ids'].append(q)
            page['groups'][q] = resolve_group(origin, ESM_ONLY_LINE, q, overrides)
            page['loc_names'][q] = page_name
            page['regions'][q] = str(comp.get('region') or 'Seyda Neen')
            page_by_journal[q] = page
        record = str(row.get('record'))
        stages = page.setdefault('rewards', {}).setdefault(record, [])
        stage = int(row.get('stage') or 0)
        if stage and stage not in stages:
            stages.append(stage)
            stages.sort()
        meta = page.setdefault('rewards_meta', {})
        key = next((k for k in meta if k.lower() == rec), record)
        rows = meta.setdefault(key, [])
        if not any(int(r.get('loc_id') or 0) == int(row.get('loc_id') or 0) for r in rows):
            rows.append(dict(row))
        seen_reward_pairs.add((q, rec))

    # ---- report items that no page claims --------------------------------
    tree_records = set()
    for _origin, _line, _name, page in _iter_pages(tree):
        tree_records |= {str(r).lower() for r in page.get('needs_item') or []}
    report['items_not_in_tree'] = sorted(set(items_by_record) - tree_records)

    return tree, report


def _iter_pages(tree):
    from quest_tree import iter_pages
    return iter_pages(tree)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', default='uesp_tree_out/quest_tree.json',
                    help='UESP tree produced by tools/scrape_uesp_quest_tree.py')
    ap.add_argument('--base', default=None,
                    help='canonical tree to update (default: data/quest_tree.json if it exists)')
    ap.add_argument('--from-raw', action='store_true',
                    help='ignore the existing canonical tree and start from --tree')
    ap.add_argument('--data', default='data')
    ap.add_argument('--out', default='data/quest_tree.json')
    ap.add_argument('--check', action='store_true', help='report only, do not write')
    args = ap.parse_args()

    base = None if args.from_raw else args.base
    if base is None and not args.from_raw:
        candidate = pathlib.Path('data/quest_tree.json')
        if candidate.exists():
            base = str(candidate)
    source = base or args.tree
    tree = load_tree(source)
    canonical = is_canonical(tree)
    tree, report = rebase(tree, args.data, check=args.check)

    print(f'input:  {source} ({"canonical" if canonical else "UESP content only"})')
    print(f'origins: {", ".join(f"{o}: {sum(len(p) for p in l.values())}" for o, l in tree.items())}')
    print(f'journals: {len({j for _o, _l, _n, p in _iter_pages(tree) for j in journal_keys(p)})}')
    print(f'filled completion stages from quest_finals.yaml: {len(report["filled_stages"])}')
    print(f'journals without Archipelago id: {len(report["journals_without_id"])}')
    print(f'needs_item without item metadata: {len(report["missing_item_meta"])}')
    print(f'rewards without reward metadata: {len(report["missing_reward_meta"])}')
    print(f'items not claimed by any tree page: {len(report["items_not_in_tree"])}')
    for label, key in (('needs_item', 'missing_item_meta'),
                       ('rewards', 'missing_reward_meta'),
                       ('items not in tree', 'items_not_in_tree')):
        rows = report[key]
        if rows:
            print(f'  {label}:')
            for row in rows[:20]:
                print(f'    {row}')

    if args.check:
        bad = (report['missing_item_meta'] or report['missing_reward_meta']
               or report['items_not_in_tree'])
        return 1 if bad else 0

    save_tree(tree, args.out)
    print(f'canonical tree -> {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
