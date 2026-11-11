#!/usr/bin/env python3
"""Builds the quest Lua tables of the mod from uesp_tree_out/quest_tree.json.

Normally called through gen_lua.py:

    python tools/gen_lua.py --tree uesp_tree_out/quest_tree.json
    python tools/gen_lua.py --tree uesp_tree_out/quest_tree.json --tree-sync-yaml   # also align the apworld data

What comes from the tree (source of truth for quest CONTENT):
  quest_completions.lua  journal ids + successful ending stages (`completion_stages`)
  quest_items.lua        progression items (`needs_item`)
  quest_rewards.lua      unique rewards (`rewards`, with their stage)

What still comes from data/*.yaml (IDENTITY, shared with the apworld, which must agree
with the Lua; the tree has no such information):
  - Archipelago ids (locations: quest_completions.yaml, items: quest_items.yaml,
    rewards: quest_rewards.yaml). An entry of the tree without an id is NOT emitted (a
    check the apworld does not know could never be sent): it is listed in the report,
    run tools/extract.py / gen_quest_items.py / gen_quest_rewards.py to create it.
  - the group of a quest (quest_completions.yaml, which includes the manual overrides of
    quest_groups_override.yaml); the tree line (UESP category) is only the fallback.
  - `fail` stages (quest_finals.yaml): UESP does not distinguish failure endings.
  - goals / locks / exclusive groups (unchanged, still read from their yaml).

Rules:
  - threshold = highest successful stage, the lower ones are alternative endings (same
    convention as quest_finals.yaml); a stage that is a known `fail` is never a success.
  - a journal listed on several UESP pages: stages are merged (union).
  - journal absent from the tree (or without any stage): fallback on quest_finals.yaml,
    unless --tree-strict.
  - items: an item of quest_items.yaml is kept if its record is a `needs_item` of the tree.
  - rewards: a reward of quest_rewards.yaml is kept if the tree lists the record in the
    `rewards` of a page containing its quest; the stage stays the YAML one.
  - (NEW) a reward of quest_rewards.yaml that the tree does not list is STILL kept,
    with its YAML stage. The tree misses rewards whose AddItem happens in a creature
    or object script (no DialogueInfo/Script with Journal): the YAML scan
    (gen_quest_rewards.py) is the only reliable signal for those.
  - the reward stage is ALWAYS the YAML one (where the ESM gives the item). It must never be
    raised to a completion stage: the mod only randomizes the reward if the quest stage is
    already >= `stage` when the item enters the inventory, otherwise it slips through.
"""
import pathlib
import sys
import json

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_lua  # noqa: E402
import gen_data_from_tree  # noqa: E402
from quest_tree import is_canonical  # noqa: E402

VANILLA_LINES = {
    'main_quest': 'main', 'daedric': 'daedric', 'fighters_guild': 'fighters_guild',
    'house_hlaalu': 'hlaalu', 'house_redoran': 'redoran', 'house_telvanni': 'telvanni',
    'imperial_cult': 'imperial_cult', 'imperial_legion': 'imperial_legion',
    'mages_guild': 'mages_guild', 'thieves_guild': 'thieves_guild',
    'tribunal_temple': 'temple', 'morag_tong': 'morag_tong', 'vampire': 'vampire',
}
TR_LINES = {
    'main_quest': 'tr_main', 'daedric': 'tr_daedric', 'fighters_guild': 'tr_fighters_guild',
    'house_hlaalu': 'tr_hlaalu', 'house_redoran': 'tr_redoran',
    'great_house_telvanni': 'tr_telvanni', 'house_indoril': 'tr_indoril',
    'imperial_cult': 'tr_imperial_cult', 'imperial_legion': 'tr_imperial_legion',
    'mages_guild': 'tr_mages_guild', 'thieves_guild': 'tr_thieves_guild',
    'tribunal_temple': 'tr_temple', 'morag_tong': 'tr_morag_tong',
    'ja_natta_syndicate': 'tr_ja_natta_syndicate', 'east_empire_company': 'tr_east_empire_company',
}


def group_of_line(origin, line):
    """Fallback group of a quest page (origin + UESP line), same names as quest_groups.py."""
    if origin == 'Morrowind':
        return VANILLA_LINES.get(line, 'misc')
    if origin == 'Tribunal':
        return 'tribunal_main' if line == 'main_quest' else 'tribunal_side'
    if origin == 'Bloodmoon':
        return {'main_quest': 'bloodmoon_main',
                'east_empire_company': 'east_empire_company'}.get(line, 'bloodmoon_side')
    return TR_LINES.get(line, 'tr_side')


def _ints(values):
    out = set()
    for v in values or []:
        try:
            out.add(int(v))
        except (TypeError, ValueError):
            pass
    return out


def flatten_tree(tree):
    """{journal id (lower): {stages, group, pages, needs, rewards}} + {record (lower): ...}"""
    journals = {}
    needs_records = set()
    page_rewards = []          # (journal ids of the page (lower), record (lower), stages)
    for origin, lines in tree.items():
        for line, pages in lines.items():
            for name, page in pages.items():
                ids = [str(j).lower() for j in page.get('ids') or []]
                for jid, stages in (page.get('completion_stages') or {}).items():
                    j = journals.setdefault(str(jid).lower(), {
                        'stages': set(), 'group': group_of_line(origin, line), 'pages': []})
                    j['stages'] |= _ints(stages)
                    j['pages'].append(f'{origin}:{name}')
                needs_records |= {str(n).lower() for n in page.get('needs_item') or []}
                for rec, stages in (page.get('rewards') or {}).items():
                    page_rewards.append((set(ids), str(rec).lower(), _ints(stages), f'{origin}:{name}'))
    return journals, needs_records, page_rewards


def _load(path):
    p = pathlib.Path(path)
    return (yaml.safe_load(p.read_text(encoding='utf-8')) or []) if p.exists() else []


def _build_canonical(tree, strict=False):
    """Rows of a canonical tree (tools/rebase_quest_tree.py schema).

    The tree already carries the group, the failing stages and the Archipelago
    ids of every journal, so there is no fallback to data/*.yaml: the tree is
    the base of the project.
    """
    comps, finals, items, rewards, names, problems = gen_data_from_tree.build(tree)
    rows = [{'quest': r['quest'], 'stage': int(r['stage']), 'stages': list(r['stages']),
             'fail': list(r['fail']), 'ids': list(r['ids']), 'group': r['group']}
            for r in finals if not r.get('fail_only') and int(r.get('stage') or 0) > 0]
    report = [
        f'== canonical tree: {len(rows)} quest completions, {len(items)} items, {len(rewards)} rewards',
        f'   journals with a location: {len(comps)}',
        f'   failure-only / no completion (no Lua check): {sum(1 for r in finals if r.get("fail_only"))}',
    ]
    if problems:
        report.append(f'   problems: {len(problems)}')
        report += [f'     {p}' for p in problems[:100]]
    return rows, items, rewards, report, ([], [])


def build(tree, data='data', strict=False):
    """Returns (completion rows, item rows, reward rows, report lines, (dropped_items, dropped_rewards))."""
    if is_canonical(tree):
        return _build_canonical(tree, strict)
    data = pathlib.Path(data)
    journals, needs_records, page_rewards = flatten_tree(tree)
    finals = {str(q['quest']).lower(): q for q in _load(data / 'quest_finals.yaml')}
    comps = {str(c['trigger']['quest']).lower(): c for c in _load(data / 'quest_completions.yaml')}
    report = []

    # ---- completions
    rows, from_tree, fallback, skipped, group_diff, conflicts, stage_diff = [], 0, [], [], [], [], []
    for qid in sorted(comps):
        c, f = comps[qid], finals.get(qid, {})
        if f.get('fail_only'):
            continue
        fail = _ints(f.get('fail'))
        group = c.get('group') or f.get('group')
        t = journals.get(qid)
        stages = set()
        if t:
            stages = t['stages'] - fail
            if t['stages'] & fail:
                conflicts.append(f"{qid}: tree stages {sorted(t['stages'] & fail)} are failure stages in quest_finals.yaml")
            if group and t['group'] != group:
                group_diff.append(f"{qid}: yaml={group} tree={t['group']}")
        if stages:
            from_tree += 1
            old = (_ints(f.get('stages')) | ({int(f['stage'])} if f.get('stage') else set())) - fail
            if f and old != stages:
                stage_diff.append(f'{qid}: quest_finals.yaml {sorted(old)} -> tree {sorted(stages)}')
        elif not strict and f:
            stages = _ints(f.get('stages')) - fail
            if not stages and int(f.get('stage') or 0) > 0:
                stages = {int(f['stage'])}
            if stages:
                fallback.append(qid)
        if not stages:
            skipped.append(qid)
            continue
        loc_ids = f.get('ids') or [c['id']]
        rows.append({'quest': qid, 'stage': max(stages), 'stages': sorted(stages),
                     'fail': sorted(fail), 'ids': loc_ids,
                     'group': group or (t['group'] if t else 'misc')})
    in_tree_no_id = sorted(set(journals) - set(comps))
    report.append(f'== quest completions: {len(rows)} emitted '
                  f'({from_tree} from the tree, {len(fallback)} from quest_finals.yaml fallback, '
                  f'{len(skipped)} without any completion stage)')
    report.append(f'   tree journals without Archipelago id (not emitted): {len(in_tree_no_id)}')
    report += [f'     {q}' for q in in_tree_no_id]
    report.append(f'   fallback on quest_finals.yaml: {len(fallback)}')
    report += [f'     {q}' for q in fallback]
    report.append(f'   no completion stage (no check): {len(skipped)}')
    report += [f'     {q}' for q in skipped]
    report.append(f'   tree stage that is a failure stage in quest_finals.yaml (dropped): {len(conflicts)}')
    report += [f'     {x}' for x in conflicts]
    report.append(f'   successful stages differ between quest_finals.yaml and the tree (tree used): {len(stage_diff)}')
    report += [f'     {x}' for x in stage_diff]
    report.append(f'   group differs between data/ (used) and the tree line: {len(group_diff)}')
    report += [f'     {x}' for x in group_diff]

    # ---- items
    items = _load(data / 'quest_items.yaml')
    kept = [i for i in items if str(i['give'][0]).lower() in needs_records]
    dropped = [i for i in items if i not in kept]
    yaml_records = {str(i['give'][0]).lower() for i in items}
    report.append(f'== quest items: {len(kept)}/{len(items)} kept (record is a needs_item of the tree)')
    report.append(f'   in yaml but not in the tree (dropped): {len(dropped)}')
    report += [f"     {i['id']} {i['goal']}: {i['give'][0]}" for i in dropped]
    missing = sorted(needs_records - yaml_records)
    report.append(f'   needs_item of the tree without id in quest_items.yaml: {len(missing)}')
    report += [f'     {r}' for r in missing]

    # ---- rewards
    rewards = _load(data / 'quest_rewards.yaml')
    index = {}
    for ids, rec, stages, page in page_rewards:
        index.setdefault(rec, []).append((ids, stages, page))
    kept_r, dropped_r, kept_from_yaml = [], [], []
    for r in rewards:
        q, rec = str(r['quest']).lower(), str(r['record']).lower()
        hit = next(((ids, st) for ids, st, _ in index.get(rec, []) if q in ids), None)
        if not hit:
            # The tree does not list this reward for its quest, but the YAML scan found it
            # (AddItem in a creature/object script): keep it as is.
            kept_from_yaml.append(r)
            kept_r.append(r)
            continue
        # NEVER raise the stage: the mod only randomizes a reward if the quest stage is
        # already >= `stage` when the item enters the inventory (player.lua, pollRewards).
        # The YAML stage is where the ESM gives the item; a higher stage (e.g. the
        # completion stage of the tree) would make the vanilla item slip through.
        kept_r.append(r)
    tree_pairs = {(q, rec) for rec, lst in index.items() for ids, _, _ in lst for q in ids}
    yaml_pairs = {(str(r['quest']).lower(), str(r['record']).lower()) for r in rewards}
    report.append(f'== quest rewards: {len(kept_r)}/{len(rewards)} kept '
                  f'({len(kept_r) - len(kept_from_yaml)} from the tree, '
                  f'{len(kept_from_yaml)} from YAML only)')
    if kept_from_yaml:
        report.append(f'   tree does not list but YAML has (kept from YAML): {len(kept_from_yaml)}')
        report += [f"     {r['loc_id']} {r['quest']}: {r['record']} (stage {r['stage']})"
                   for r in kept_from_yaml]
    report.append(f'   in yaml but not in the tree (dropped): {len(dropped_r)}')
    report += [f"     {r['loc_id']} {r['quest']}: {r['record']}" for r in dropped_r]
    new_pairs = sorted(tree_pairs - yaml_pairs)
    report.append(f'   tree (journal, reward) pairs without id in quest_rewards.yaml: {len(new_pairs)}')
    report += [f'     {q}: {rec}' for q, rec in new_pairs]
    return rows, kept, kept_r, report, (dropped, dropped_r)


def run(args):
    tree = json.loads(pathlib.Path(args.tree).read_text(encoding='utf-8'))
    rows, items, rewards, report, _ = build(tree, strict=args.tree_strict)
    note = f'-- Generated by tools/gen_lua.py --tree {pathlib.Path(args.tree).name}'
    gen_lua.emit_quest_completions(rows, args.qc_out, header=note)
    gen_lua.emit_quest_items(items, args.quest_items_out, header=note + ' (needs_item)')
    gen_lua.emit_quest_rewards(rewards, args.quest_rewards_out, args.quest_names, header=note + ' (rewards)')
    rp = pathlib.Path(args.tree_report)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text('\n'.join(report) + '\n', encoding='utf-8')
    print('\n'.join(l for l in report if l.startswith('==')))
    print(f'report -> {rp}')
    if args.tree_sync_yaml:
        if is_canonical(tree):
            gen_data_from_tree.write_all(tree, data='data')
            print('all data yaml synced from the canonical tree: '
                  'run python tools/install_apworld.py')
        else:
            _write_yaml('data/quest_items.yaml', items, 'quest items')
            _write_yaml('data/quest_rewards.yaml', rewards, 'quest rewards')
            print('yaml synced: run python tools/install_apworld.py')


def _write_yaml(path, rows, label):
    p = pathlib.Path(path)
    p.write_text(f'# {label}: aligned with quest_tree.json by tools/gen_lua.py --tree --tree-sync-yaml\n'
                 + yaml.safe_dump(rows, sort_keys=False, allow_unicode=True, width=10000),
                 encoding='utf-8')


if __name__ == '__main__':
    sys.exit('use: python tools/gen_lua.py --tree uesp_tree_out/quest_tree.json')
