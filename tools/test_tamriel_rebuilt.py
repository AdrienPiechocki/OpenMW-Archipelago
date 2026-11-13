"""Tests of the Tamriel Rebuilt options and classification (no Archipelago needed).

From the repository root:
    python3 tools/test_tamriel_rebuilt.py
"""
import importlib.util
import pathlib
import sys
import tempfile
import types

fake = types.ModuleType('Options')
for name, default in (('Toggle', 0), ('Choice', 0), ('DefaultOnToggle', 1),
                      ('PerGameCommonOptions', None), ('Range', 0)):
    setattr(fake, name, type(name, (), {'default': default}))
sys.modules['Options'] = fake

root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('mw_options', root / 'apworld/morrowind_openmw/options.py')
opts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opts)
sys.path.insert(0, str(root / 'tools'))
import quest_groups as qg  # noqa: E402
import gen_quest_finals as gqf  # noqa: E402
import gen_lua as gl  # noqa: E402
import yaml  # noqa: E402


class Val:
    def __init__(self, v): self.value = v
class Key:
    def __init__(self, k): self.current_key = k


def make(main=True, house='none', guild='none', faction='none', daedric=False, **tr):
    o = types.SimpleNamespace(main_quest=Val(main), great_house=Key(house), guild=Key(guild),
                              faction=Key(faction), daedric_quests=Val(daedric))
    for k, v in tr.items():
        setattr(o, k, Val(v))
    return o


fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f'FAIL {name}: got {got!r}, want {want!r}')
    else:
        print(f'ok   {name}')


# ---- options -----------------------------------------------------------------
check('default: no TR group', opts.selected_tr_groups(make()), [])
check('default goals unchanged', opts.selected_goals(make()), ['main_quest'])
check('TR main + main_quest = goal', opts.selected_goals(make(tamriel_rebuilt_main_quest=True)),
      ['main_quest', 'tamriel_rebuilt_main'])
check('TR main + main_quest: group', opts.selected_tr_groups(make(tamriel_rebuilt_main_quest=True)), ['tr_main'])
check('TR main ignored without main_quest', opts.selected_goals(make(main=False, house='hlaalu', tamriel_rebuilt_main_quest=True)),
      ['hlaalu'])
check('TR main ignored without main_quest (group)',
      opts.selected_tr_groups(make(main=False, house='hlaalu', tamriel_rebuilt_main_quest=True)), [])
check('TR side only: free check, no goal', opts.selected_goals(make(tamriel_rebuilt_side_quests=True)), ['main_quest'])
check('TR side group', opts.selected_tr_groups(make(tamriel_rebuilt_side_quests=True)), ['tr_side'])
check('TR factions: chosen ones only',
      opts.selected_tr_groups(make(house='indoril', faction='ja_natta_syndicate', guild='mages_guild',
                                   tamriel_rebuilt_factions=True)),
      ['tr_indoril', 'tr_mages_guild', 'tr_ja_natta_syndicate'])
check('TR factions off: nothing', opts.selected_tr_groups(make(house='indoril')), [])
check('TR EEC faction enables the EEC questline',
      opts.selected_tr_groups(make(faction='east_empire_company', tamriel_rebuilt_factions=True)),
      ['tr_east_empire_company'])
check('TR EEC questline off without tamriel_rebuilt_factions',
      opts.selected_tr_groups(make(faction='east_empire_company')), [])
check('TR EEC questline off without the EEC goal',
      opts.selected_tr_groups(make(tamriel_rebuilt_factions=True)), [])
check('TR daedric needs daedric_quests', opts.selected_tr_groups(make(tamriel_rebuilt_daedric_quests=True)), [])
check('TR daedric with daedric_quests', opts.selected_tr_groups(make(daedric=True, tamriel_rebuilt_daedric_quests=True)),
      ['tr_daedric'])
check('lock group without TR option', opts.group_enabled(
    make(daedric=True, tamriel_rebuilt_daedric_quests=False), 'tr_daedric'), False)
check('lock group without daedric goal', opts.group_enabled(
    make(daedric=False, tamriel_rebuilt_daedric_quests=True), 'tr_daedric'), False)
check('TR daedric lock group enabled', opts.group_enabled(
    make(daedric=True, tamriel_rebuilt_daedric_quests=True), 'tr_daedric'), True)
check('lock without group always enabled', opts.group_enabled(make(), None), True)
check('expansion lock group enabled',
      opts.group_enabled(make(tribunal_main_quest=True), 'tribunal_main'), True)
check('indoril goal', opts.selected_goals(make(house='indoril')), ['main_quest', 'indoril'])
check('ja_natta goal', opts.selected_goals(make(faction='ja_natta_syndicate')), ['main_quest', 'ja_natta_syndicate'])
check('indoril option value', getattr(opts.GreatHouse, 'option_indoril', None), 4)
check('ja_natta option value', getattr(opts.Faction, 'option_ja_natta_syndicate', None), 6)

# ---- groups ------------------------------------------------------------------
check('goal of tr_main', opts.goal_of_group('tr_main'), 'tamriel_rebuilt_main')
check('goal of tr_daedric', opts.goal_of_group('tr_daedric'), 'daedric_quests')
check('goal of tr_hlaalu', opts.goal_of_group('tr_hlaalu'), 'hlaalu')
check('goal of tr_east_empire_company', opts.goal_of_group('tr_east_empire_company'), 'east_empire_company')
check('EEC is not a free group', opts.is_free_group('tr_east_empire_company'), False)
check('tr_side is free', opts.is_free_group('tr_side'), True)
check('tr_main is not free', opts.is_free_group('tr_main'), False)
check('TR groups in sync with quest_groups.py', opts.TR_GROUPS, qg.TR_GROUPS)
check('TR faction keys in sync', opts.TR_FACTION_KEYS, qg.TR_FACTION_KEYS)
check('every TR faction key is a goal key',
      all(k in __import__('yaml').safe_load((root / 'data/goals.yaml').read_text()) for k in opts.TR_FACTION_KEYS), True)
goals = __import__('yaml').safe_load((root / 'data/goals.yaml').read_text())
check('TR main goal key in goals.yaml', opts.TR_MAIN_GOAL in goals, True)
check('TR main goal = TR_NecMQ_3 stage 200',
      goals[opts.TR_MAIN_GOAL].get('quests'), [{'quest': 'tr_necmq_3', 'stage': 200}])
check('TR main goal is not the impossible tr_main group',
      'group' in goals[opts.TR_MAIN_GOAL], False)
check('indoril faction id', goals['indoril'].get('faction'), 'T_Mw_HouseIndoril')
check('indoril rank', goals['indoril'].get('rank'), 10)
check('ja_natta faction id', goals['ja_natta_syndicate'].get('faction'), 'T_Mw_JaNattaSyndicate')
check('ja_natta rank', goals['ja_natta_syndicate'].get('rank'), 10)
# the Ordinators faction id / rank are still a placeholder until set_goal_faction.py is run
check('only the Ordinators goal is unverified', opts.UNVERIFIED_GOALS, ('ordinators',))
check('ordinators option value', getattr(opts.Faction, 'option_ordinators', None), 7)
check('ordinators goal', opts.selected_goals(make(faction='ordinators')), ['main_quest', 'ordinators'])
check('ordinators group enabled with TR factions',
      opts.selected_tr_groups(make(faction='ordinators', tamriel_rebuilt_factions=True)), ['tr_ordinators'])
check('ordinators group off without TR factions',
      opts.selected_tr_groups(make(faction='ordinators')), [])
import re as _re
_items_src = (pathlib.Path(__file__).resolve().parent.parent / 'apworld/morrowind_openmw/items.py').read_text(encoding='utf-8')
check('ordinators requirement item', bool(_re.search(r'"ordinators": \(BASE_ITEM \+ 513,', _items_src)), True)
_lua = (pathlib.Path(__file__).resolve().parent.parent / 'mod/scripts/ap/faction_requirements.lua').read_text(encoding='utf-8')
check('ordinators requirement id in Lua', 'ordinators = 7701513' in _lua, True)
check('TR main completion stage 200', gqf.STAGE_OVERRIDES.get('tr_necmq_3'), 200)
check('TR main only success stage', gqf.STAGES_OVERRIDES.get('tr_necmq_3'), [200])
check('TR main softlocks are failures', gqf.FAIL_STAGES.get('tr_necmq_3'), [190, 195, 199])
check('TR alternate completion (Troubles on the Road)',
      gqf.STAGES_OVERRIDES.get('tr_m4_bal0_troubles_a'), [200])
check('TR alternate completion main stage',
      gqf.STAGE_OVERRIDES.get('tr_m4_bal0_troubles_a'), 200)
check('TR failure-only journals', gqf.FAIL_ONLY,
      {'tr_m1_fw_ic6_lorefail': [300], 'tr_m3_aim_dreugh1b': [200, 250]})
check('a failure-only journal is never a completion',
      any(q in gqf.STAGES_OVERRIDES or q in gqf.STAGE_OVERRIDES for q in gqf.FAIL_ONLY), False)

# ---- quest locks (Tamriel Rebuilt Daedric princes) --------------------------
locks = yaml.safe_load((root / 'data/quest_locks.yaml').read_text())
tr_locks = [l for l in locks if l.get('group') == 'tr_daedric']
check('4 TR daedric locks', len(tr_locks), 4)
check('TR lock ids', [l['id'] for l in tr_locks], [7701407, 7701408, 7701409, 7701410])
check('all lock ids unique', len({l['id'] for l in locks}), len(locks))
check('vanilla locks have no group', [l.get('group') for l in locks if l['id'] < 7701407],
      [None] * 7)
expected_tr_locks = {
    'tr_m1_da_clavicus': ('Daedric Quest: Clavicus Vile', 'TR_m1_DA_Clavicus_Statue_sc',
                          'TR_m1_Clavicus_Shrine'),
    'tr_m1_da_sanguine': ('Daedric Quest: Sanguine', 'TR_m1_DA_SanguineQuest',
                          'TR_m1_Sanguine_Shrine'),
    'tr_m7_da_meridia': ('Daedric Quest: Meridia', 'TR_m7_Meridia_Shrine',
                         'TR_m7_Statue_Meridia'),
    'tr_m7_da_namira': ('Daedric Quest: Namira', 'TR_m7_DA_Namira_Statue_sc',
                        'TR_m7_Statue_Namira'),
}
by_quest = {l['quest']: l for l in tr_locks}
check('TR lock quests', sorted(by_quest), sorted(expected_tr_locks))
for quest, (name, script, activator) in expected_tr_locks.items():
    lk = by_quest.get(quest, {})
    check(f'{quest}: goal', lk.get('goal'), 'daedric_quests')
    check(f'{quest}: name', lk.get('name'), name)
    check(f'{quest}: script', lk.get('scripts'), [script])
    check(f'{quest}: activator', lk.get('activators'), [activator])

# The generated Lua tables must carry the group (used by the mod to gate the
# locks on tamriel_rebuilt_daedric_quests).
with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    gl.gen_quest_locks(root / 'data/quest_locks.yaml', td / 'locks.lua')
    gl.gen_quest_lock_activators(root / 'data/quest_locks.yaml', td / 'activators.lua')
    locks_lua = (td / 'locks.lua').read_text()
    activators_lua = (td / 'activators.lua').read_text()
check('generated lock group', "quest = 'tr_m7_da_namira', group = 'tr_daedric'" in locks_lua,
      True)
check('generated activator group',
      "['TR_m7_Statue_Namira'] = { id = 7701410, quest = 'tr_m7_da_namira', "
      "goal = 'daedric_quests', name = 'Daedric Quest: Namira', group = 'tr_daedric' }"
      in activators_lua, True)
check('generated locks count', locks_lua.count('id = '), 11)
check('generated activators keep vanilla entries', "['DaedraAzura']" in activators_lua, True)

# ---- classification (IDs confirmed on UESP) -----------------------------------
cats = {'main': {'tr_m1_fm_x'}, 'main_prefixes': (), 'daedric': {'tr_m1_da_y'}, 'daedric_prefixes': (),
        'tokens': dict(qg.DEFAULT_TR_TOKENS)}
for q, want in {
    'TR_m4_HH_Ulvo4': 'tr_hlaalu', 'TR_m2_HT_Vaerin_q2': 'tr_telvanni', 'TR_m3_TT_Lloris1c': 'tr_temple',
    'TR_m7_Ns_JNS_7': 'tr_ja_natta_syndicate', 'TR_m3_Kha_UndyingRivalry': 'tr_side',
    'TR_m3_Ord_Watch1': 'tr_ordinators', 'TR_m3_Ord_War4': 'tr_ordinators',
    'TR_m3_Ord_Doc4_wm': 'tr_ordinators', 'TR_m4_Ord_Rite': 'tr_ordinators',
    'TR_m1_EEC_Lora': 'tr_east_empire_company', 'TR_m3_EEC_Cano1': 'tr_east_empire_company',
    'TR_m1_FW_IC2_Taxes': 'tr_imperial_cult', 'TR_m1_FW_MG01': 'tr_mages_guild',
    'TR_m1_FW_MG07a': 'tr_mages_guild', 'TR_m2_He_TG1': 'tr_thieves_guild',
    'TR_m2_TGi_ComplicatComp': 'tr_side',
    'TR_m3_OE_OhWhatCustoms': 'tr_side', 'TR_m7_Ida_Net': 'tr_side', 'TR_m4_wil_TaxmanIndalruhn': 'tr_side',
    'TR_m1_FM_X': 'tr_main', 'TR_m1_DA_Y': 'tr_daedric',
}.items():
    check(f'classify {q}', qg.classify(q, None, None, cats), want)
check('eec token loaded from data/tr_categories.yaml',
      qg.load_tr_categories()['tokens'].get('eec'), 'east_empire_company')
check('TR EEC quests are faction checks, not side checks',
      qg.classify('TR_m1_EEC_Lora', None, None), 'tr_east_empire_company')
check('Tribunal ids are not TR', qg.classify('tr_sothasil'), 'tribunal_main')
check('Tribunal dbattack not TR', qg.classify('TR_DBAttack').startswith('tribunal'), True)
check('vanilla untouched', qg.classify('hh_ineedtospeaktothecaptain'), 'hlaalu')
check('origin tamriel_rebuilt', qg.classify('x_quest', {'x_quest': 'tamriel_rebuilt'}, None, cats), 'tr_side')
check('manual override', qg.classify('tr_m1_zz', {'tr_m1_zz': 'tr_main'}, None, cats), 'tr_main')
check('TR groups are valid', set(qg.TR_GROUPS) <= qg.VALID_GROUPS, True)

if fails:
    print(f'{fails} failure(s)')
    sys.exit(1)
print('all Tamriel Rebuilt tests passed')
