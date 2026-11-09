#!/usr/bin/env python3
"""Test of the quest rewards generator (tools/gen_quest_rewards.py).

From the repository root:
    python3 tools/test_quest_rewards.py
"""
import pathlib
import sys
import tempfile

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_quest_rewards as g  # noqa: E402
import gen_lua  # noqa: E402

fails = 0


def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f'FAIL {name}: got {got!r}, want {want!r}')
    else:
        print(f'ok   {name}')


def info(text, **extra):
    r = {'type': 'DialogueInfo', 'script_text': text}
    r.update(extra)
    return r


def item(rid, t, name=None):
    return {'type': t, 'id': rid, 'name': name or rid}


COMPLETIONS = {
    'mq_a': {'group': 'misc', 'region': 'Balmora', 'name': 'Quest A'},
    'tr_x': {'group': 'tr_side', 'region': 'Seyda Neen', 'name': 'TR X'},
}

records = [
    {'type': 'Dialogue', 'dialogue_type': 'Journal', 'id': 'mq_a'},
    {'type': 'Dialogue', 'dialogue_type': 'Journal', 'id': 'tr_x'},
    {'type': 'Dialogue', 'dialogue_type': 'Journal', 'id': 'nocheck'},
    item('ring_unique', 'clothing', 'Ring of Tests'),
    item('sword_loot', 'weapon', 'Common Sword'),
    item('key_needed', 'miscitem', 'Needed Key'),
    item('potion_x', 'alchemy', 'Potion'),
    item('shield_nocheck', 'armor', 'Shield'),
    item('amulet_tr', 'clothing', 'TR Amulet'),
    # reward unique of mq_a + gold + consumable (ignored) + loot item (not unique)
    info('Journal "mq_a", 50\nAddItem ring_unique 1\nAddItem gold_001 500\n'
         'AddItem potion_x 3\nAddItem sword_loot 1'),
    # key handed over by a quest: progression, never a reward
    info('Journal mq_a 60\nAddItem key_needed 1'),
    info('Journal mq_a 70\nRemoveItem key_needed 1'),
    # quest without a completion check
    info('Journal "nocheck", 10\nAddItem shield_nocheck 1'),
    # TR quest
    info('Journal tr_x 30\nAddItem amulet_tr 1'),
    # an NPC carries the sword: obtainable outside the quest
    {'type': 'Npc', 'id': 'npc1', 'inventory': [[1, 'sword_loot']]},
]

rewards, stats = g.scan(records, COMPLETIONS, set())
by_item = {r['record']: r for r in rewards}
check('unique reward kept', sorted(by_item), ['amulet_tr', 'ring_unique'])
check('stage of the reward', by_item['ring_unique']['stage'], 50)
check('group / region of the quest', (by_item['ring_unique']['group'], by_item['ring_unique']['region']),
      ('misc', 'Balmora'))
check('TR group', by_item['amulet_tr']['group'], 'tr_side')
check('progression ignored', stats['progression'], 1)
check('not unique ignored', stats['not_unique'], 1)
check('no completion ignored', stats['no_completion'], 1)

# Journal stages are parsed with and without quotes.
check('journal stages', g.journal_stages('Journal "A_b", 40\nJournal c 5'), [('a_b', 40), ('c', 5)])

# Stable ids and unique names.
first = g.assign(rewards, [])
check('ids in range', all(g.REWARD_ITEM_BASE <= e['item_id'] < g.REWARD_ITEM_LIMIT
                           and g.REWARD_LOC_BASE <= e['loc_id'] < g.REWARD_LOC_LIMIT for e in first), True)
second = g.assign(rewards + [{'quest': 'mq_a', 'record': 'ring_other', 'item_name': 'Ring of Tests',
                              'count': 1, 'stage': 10, 'group': 'misc', 'region': 'Balmora'}], first)
check('ids kept', [(e['item_id'], e['loc_id']) for e in second[:2]],
      [(e['item_id'], e['loc_id']) for e in first])
check('duplicate name disambiguated', second[2]['name'], 'Reward: Ring of Tests (mq_a)')
check('names unique', len({e['name'] for e in second}), len(second))

# A quest reclassification must refresh the reward group while keeping the
# stable ids / name (otherwise the reward location stays enabled even though
# the quest check is disabled).
reclassified = [dict(r) for r in rewards]
for r in reclassified:
    if r['quest'] == 'tr_x':
        r['group'] = 'tr_east_empire_company'
third = g.assign(reclassified, first)
old_tr = next(e for e in first if e['quest'] == 'tr_x')
new_tr = next(e for e in third if e['quest'] == 'tr_x')
check('reclassification updates group', new_tr['group'], 'tr_east_empire_company')
check('reclassification keeps ids', (new_tr['item_id'], new_tr['loc_id']),
      (old_tr['item_id'], old_tr['loc_id']))
check('reclassification keeps name', new_tr['name'], old_tr['name'])

# YAML dump -> reload -> Lua generation.
with tempfile.TemporaryDirectory() as tmp:
    ypath = pathlib.Path(tmp) / 'quest_rewards.yaml'
    ypath.write_text(g.dump(second), encoding='utf-8')
    loaded = yaml.safe_load(ypath.read_text(encoding='utf-8'))
    check('yaml roundtrip', loaded, second)
    lpath = pathlib.Path(tmp) / 'quest_rewards.lua'
    gen_lua.gen_quest_rewards(str(ypath), str(lpath))
    lua = lpath.read_text()
    check('lua entry', "record = 'ring_unique', count = 1, quest = 'mq_a', stage = 50, group = 'misc'" in lua, True)

check('empty yaml dump', yaml.safe_load(g.dump([])), [])

print('\nFAILS:', fails)
sys.exit(1 if fails else 0)
