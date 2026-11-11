#!/usr/bin/env python3
"""Test of tools/rebase_quest_tree.py and tools/gen_data_from_tree.py.

From the repository root: python3 tools/test_rebase_quest_tree.py
"""
import copy
import pathlib
import sys
import tempfile

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_data_from_tree as gen  # noqa: E402
from quest_tree import ESM_ONLY_LINE, iter_pages, journal_keys, resolve_group  # noqa: E402
import rebase_quest_tree as rebase  # noqa: E402

fails = 0


def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f'FAIL {name}: got {got!r}, want {want!r}')
    else:
        print(f'ok   {name}')


def page(ids, stages, region='X', needs=(), rewards=None):
    return {'ids': list(ids), 'completion_stages': stages, 'region': region,
            'triggers': {}, 'needs_item': list(needs), 'rewards': rewards or {}}


def write(d, name, rows):
    (d / name).write_text(yaml.safe_dump(rows), encoding='utf-8')


TREE = {
    'Morrowind': {
        'fighters_guild': {
            'Quest A': page(['fg_a'], {'fg_a': [100, 110]},
                            needs=['Key_A', 'Key_B'], rewards={'ring_a': [100]}),
            'Quest Shared 1': page(['fg_shared'], {'fg_shared': [30]}),
            'Quest Shared 2': page(['fg_shared'], {'fg_shared': [40]}),
        },
        'main_quest': {'Quest C': page(['a1_c'], {'a1_c': [20]})},
        'aldruhn': {'Town': page(['town_x'], {'town_x': [10]}, region='Aldruhn')},
    },
    'Tribunal': {'main_quest': {'Quest T': page(['tr_t'], {'tr_t': [50]})}},
}

with tempfile.TemporaryDirectory() as tmp:
    d = pathlib.Path(tmp)
    comp = lambda q, i, grp, region='R', name=None: {
        'id': i, 'name': name or q, 'category': 'quest_complete',
        'trigger': {'quest': q}, 'group': grp, 'region': region}
    write(d, 'quest_completions.yaml', [
        comp('fg_a', 1, 'fighters_guild', name='Quest A'),
        comp('fg_shared', 2, 'fighters_guild'),
        comp('a1_c', 3, 'main'),
        comp('town_x', 4, 'misc', 'Aldruhn'),
        comp('tr_t', 5, 'tribunal_main'),
        comp('old_only', 6, 'misc', name='Old Only'),
    ])
    write(d, 'quest_finals.yaml', [
        {'quest': 'fg_a', 'stage': 110, 'stages': [100, 110], 'fail': [110], 'ids': [1], 'group': 'fighters_guild'},
        {'quest': 'fg_shared', 'stage': 40, 'stages': [40], 'fail': [], 'ids': [2], 'group': 'fighters_guild'},
        {'quest': 'a1_c', 'stage': 20, 'stages': [20], 'fail': [], 'ids': [3], 'group': 'main'},
        {'quest': 'town_x', 'stage': 10, 'stages': [10], 'fail': [], 'ids': [4], 'group': 'misc'},
        {'quest': 'tr_t', 'stage': 50, 'stages': [50], 'fail': [], 'ids': [5], 'group': 'tribunal_main'},
        {'quest': 'old_only', 'stage': 0, 'stages': [], 'fail': [6], 'ids': [6], 'group': 'misc'},
    ])
    write(d, 'quest_sources.yaml', {})
    write(d, 'quest_names.yaml', {'fg_a': 'Quest A', 'old_only': 'Old Only'})
    write(d, 'quest_items.yaml', [
        {'name': 'Key A', 'id': 10, 'goal': 'fighters_guild', 'give': ['Key_A', 1]},
        {'name': 'Key A (main)', 'id': 10, 'goal': 'main_quest', 'give': ['Key_A', 1]},
        {'name': 'Key B', 'id': 11, 'goal': 'fighters_guild', 'give': ['Key_B', 1]},
    ])
    write(d, 'quest_rewards.yaml', [
        {'name': 'Reward: Ring', 'item_id': 20, 'loc_id': 30, 'record': 'ring_a',
         'quest': 'fg_a', 'quest_name': 'Quest A', 'stage': 100, 'group': 'fighters_guild'},
        {'name': 'Reward: Ring 2', 'item_id': 21, 'loc_id': 31, 'record': 'ring_a',
         'quest': 'fg_shared', 'quest_name': 'Quest Shared', 'stage': 40, 'group': 'fighters_guild'},
        {'name': 'Reward: Old', 'item_id': 22, 'loc_id': 32, 'record': 'old_reward',
         'quest': 'old_only', 'quest_name': 'Old Only', 'stage': 5, 'group': 'misc'},
    ])
    write(d, 'quest_groups_override.yaml', {'fg_a': 'non_quest'})

    tree = copy.deepcopy(TREE)
    tree, report = rebase.rebase(tree, data=d)

    pages = list(iter_pages(tree))
    check('_esm_only pages are iterated', any(line == ESM_ONLY_LINE for _o, line, _n, _p in pages), True)
    check('missing journal added under _esm_only',
          [j for _o, line, _n, p in pages if line == ESM_ONLY_LINE
           for j in journal_keys(p)], ['old_only'])

    by_page = {(line, name): p for _o, line, name, p in pages}
    a = by_page[('fighters_guild', 'Quest A')]
    check('override wins over the faction line', a['groups']['fg_a'], 'non_quest')
    check('failure stage attached', a['fail']['fg_a'], [110])
    check('successful stages kept', a['completion_stages']['fg_a'], [100, 110])
    check('item metadata attached', sorted(m['name'] for m in a['needs_item_meta']['Key_A']),
          ['Key A', 'Key A (main)'])
    check('reward metadata attached', sorted(r['loc_id'] for r in a['rewards_meta']['ring_a']), [30, 31])

    esm = by_page[(ESM_ONLY_LINE, 'Old Only')]
    check('ESM-only journal keeps its location', esm['loc_ids']['old_only'], [6])
    check('ESM-only journal has no success stage', esm['completion_stages'].get('old_only', []), [])
    check('ESM-only journal keeps its failure stage', esm['fail']['old_only'], [6])

    check('faction line group', by_page[('main_quest', 'Quest C')]['groups']['a1_c'], 'main')
    check('faction line group (Tribunal)', by_page[('main_quest', 'Quest T')]['groups']['tr_t'], 'tribunal_main')
    check('prefix fallback', resolve_group('Morrowind', 'aldruhn', 'fg_other'), 'fighters_guild')
    check('location line falls back to the journal prefix',
          by_page[('aldruhn', 'Town')]['groups']['town_x'], 'misc')

    comps, finals, items, rewards, names, problems = gen.build(tree)
    by_q = {r['quest']: r for r in finals}
    check('no generation problem', problems, [])
    check('journals merged across pages', (by_q['fg_shared']['stages'], by_q['fg_shared']['stage']),
          ([30, 40], 40))
    check('fail stage removed from success', (by_q['fg_a']['stages'], by_q['fg_a']['stage']), ([100], 100))
    check('failure-only journal kept', (by_q['old_only']['stage'], by_q.get('old_only', {}).get('fail_only')), (0, True))
    check('one completion per journal', len(comps), 6)
    check('item rows preserved (goal variants)', len(items), 3)
    check('shared reward rows preserved', [r['loc_id'] for r in rewards], [30, 31, 32])
    check('reward name fallback', next(r['quest_name'] for r in rewards if r['loc_id'] == 32), 'Old Only')
    check('readable name kept', names['fg_a'], 'Quest A')

    # Re-running the enrichment on its own output must not lose anything.
    again, report2 = rebase.rebase(copy.deepcopy(tree), data=d)
    check('idempotent: no missing metadata',
          (report2['missing_item_meta'], report2['missing_reward_meta'], report2['items_not_in_tree']),
          ([], [], []))
    check('idempotent: same journals', len(list(iter_pages(again))), len(pages))

sys.exit(1 if fails else 0)
