#!/usr/bin/env python3
"""Test of tools/gen_lua_from_tree.py (From the repository root: python3 tools/test_gen_lua_from_tree.py)."""
import pathlib
import sys
import tempfile

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_lua_from_tree as g  # noqa: E402

fails = 0


def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f'FAIL {name}: got {got!r}, want {want!r}')
    else:
        print(f'ok   {name}')


def page(ids, stages, needs=(), rewards=None):
    return {'ids': ids, 'completion_stages': stages, 'region': 'X', 'triggers': {},
            'needs_item': list(needs), 'rewards': rewards or {}}


TREE = {
    'Morrowind': {
        'fighters_guild': {
            'Quest A': page(['fg_a'], {'fg_a': [100, 110]}, needs=['Key_A'], rewards={'Ring_A': [100]}),
            'Quest B': page(['fg_b', 'fg_b2'], {'fg_b': [50], 'fg_b2': []}),
            'Junk': page(['optional'], {'optional': [10]}),
        },
        'main_quest': {'Quest C': page(['a1_c'], {'a1_c': [20, 30]})},
    },
    'Tamriel Rebuilt': {'house_indoril': {'Quest D': page(['tr_m3_hi_d'], {'tr_m3_hi_d': [100]})}},
}


def write(d, name, rows):
    (d / name).write_text(yaml.safe_dump(rows))


with tempfile.TemporaryDirectory() as tmp:
    d = pathlib.Path(tmp)
    comp = lambda q, i, grp: {'id': i, 'name': q, 'trigger': {'quest': q}, 'group': grp, 'region': 'R'}
    write(d, 'quest_completions.yaml', [comp('fg_a', 1, 'fighters_guild'), comp('fg_b', 2, 'fighters_guild'),
                                         comp('fg_b2', 3, 'fighters_guild'), comp('a1_c', 4, 'misc'),
                                         comp('tr_m3_hi_d', 5, 'tr_indoril'), comp('old_only', 6, 'misc')])
    write(d, 'quest_finals.yaml', [
        {'quest': 'fg_a', 'stage': 100, 'stages': [100, 110], 'fail': [110], 'ids': [1], 'group': 'fighters_guild'},
        {'quest': 'fg_b', 'stage': 50, 'stages': [50], 'fail': [], 'ids': [2], 'group': 'fighters_guild'},
        {'quest': 'fg_b2', 'stage': 70, 'stages': [70], 'fail': [], 'ids': [3], 'group': 'fighters_guild'},
        {'quest': 'a1_c', 'stage': 30, 'stages': [30], 'fail': [], 'ids': [4], 'group': 'misc'},
        {'quest': 'tr_m3_hi_d', 'stage': 100, 'stages': [100], 'fail': [], 'ids': [5], 'group': 'tr_indoril'},
        {'quest': 'old_only', 'stage': 5, 'stages': [5], 'fail': [], 'ids': [6], 'group': 'misc'},
    ])
    write(d, 'quest_items.yaml', [
        {'name': 'Key', 'id': 10, 'goal': 'fighters_guild', 'give': ['Key_A', 1], 'suppress': ['Key_A']},
        {'name': 'Gone', 'id': 11, 'goal': 'fighters_guild', 'give': ['Gone', 1], 'suppress': ['Gone']}])
    write(d, 'quest_rewards.yaml', [
        {'name': 'Reward: Ring', 'item_id': 20, 'loc_id': 30, 'record': 'ring_a', 'quest': 'fg_a',
         'quest_name': 'Quest A', 'stage': 1, 'group': 'fighters_guild'},
        {'name': 'Reward: Lost', 'item_id': 21, 'loc_id': 31, 'record': 'lost', 'quest': 'fg_a',
         'quest_name': 'Quest A', 'stage': 1, 'group': 'fighters_guild'}])

    rows, items, rewards, report, _ = g.build(TREE, data=d)
    by = {r['quest']: r for r in rows}
    # tree stages, minus failure stages known from quest_finals.yaml
    check('fail stage dropped', (by['fg_a']['stage'], by['fg_a']['stages'], by['fg_a']['fail']), (100, [100], [110]))
    check('threshold is highest stage', (by['a1_c']['stage'], by['a1_c']['stages']), (30, [20, 30]))
    check('empty tree stages -> finals fallback', by['fg_b2']['stage'], 70)
    check('journal absent from tree -> finals fallback', by['old_only']['stage'], 5)
    check('location ids kept', by['fg_b']['ids'], [2])
    check('yaml group wins over the tree line', by['a1_c']['group'], 'misc')
    check('junk id without Archipelago id not emitted', 'optional' in by, False)
    check('item kept / dropped', [i['id'] for i in items], [10])
    check('rewards kept, YAML stage never raised', [(r['loc_id'], r['stage']) for r in rewards], [(30, 1), (31, 1)])
    rows2, *_ = g.build(TREE, data=d, strict=True)
    check('strict: no fallback', sorted(r['quest'] for r in rows2), ['a1_c', 'fg_a', 'fg_b', 'tr_m3_hi_d'])
    check('fallback group from tree line', g.group_of_line('Tamriel Rebuilt', 'house_indoril'), 'tr_indoril')

sys.exit(1 if fails else 0)
