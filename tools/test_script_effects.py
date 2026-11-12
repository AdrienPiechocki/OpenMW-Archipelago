#!/usr/bin/env python3
"""python tools/test_script_effects.py"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from script_effects import parse_script, is_quest_item, _resolve_journal

# 1. each branch counts only for ITS journal
txt = '''
if ( choice == 1 )
    Player->RemoveItem "bk_note_a" 1
    Journal QUEST_A 20
elseif ( choice == 2 )
    Player->RemoveItem "bk_note_b" 1
    Journal QUEST_B 20
endif
'''
eff = {(k, i, j) for k, i, q, j in parse_script('t1', txt)}
assert ('needed', 'bk_note_a', 'QUEST_A') in eff, eff
assert ('needed', 'bk_note_b', 'QUEST_B') in eff, eff
assert ('needed', 'bk_note_a', 'QUEST_B') not in eff, eff

# 2. bare RemoveItem (NPC side) is ignored, Player-> is read
txt = 'RemoveItem "bk_npc_only" 1\nPlayer->RemoveItem "key_real" 1\nJournal Q1 10\n'
ids = {i for k, i, q, j in parse_script('t2', txt)}
assert ids == {'key_real'}, ids

# 3. GetItemCount comparison + reward
txt = 'if ( Player->GetItemCount "misc_x" >= 3 )\n Journal Q2 30\nendif\nPlayer->AddItem "ring_unique" 1\nJournal Q2 30\n'
eff = parse_script('t3', txt)
assert ('needed', 'misc_x', 3, 'Q2') in eff and ('reward', 'ring_unique', 1, 'Q2') in eff, eff

# 4. generic stock is not a quest item
for g in ('sc_divineintervention', 'misc_de_drum_02', 'ingred_diamond_01', 'p_restore_health_c'):
    assert not is_quest_item(g), g
for q in ('bk_note', 'key_oritius', 'ring_wind_unique', 'expensive_ring_aeta'):
    assert is_quest_item(q), q

# 5. journal sub-ids
known = {'TR_M3_AT_DEED'}
assert _resolve_journal('TR_M3_AT_DEED_C', known, {}) == 'TR_M3_AT_DEED'
print('ok')

# 6. "does NOT have" checks are not requirements
txt = 'if ( Player->GetItemCount "bk_x" < 1 )\n Journal Q9 10\nendif\n'
assert not [e for e in parse_script('t6', txt) if e[0] == 'needed'], 'absence check read as need'
print('ok 2')
