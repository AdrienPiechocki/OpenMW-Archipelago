"""Tests of the Tamriel Rebuilt options and classification (no Archipelago needed).

From the repository root:
    python3 tools/test_tamriel_rebuilt.py
"""
import importlib.util
import pathlib
import sys
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
check('TR daedric needs daedric_quests', opts.selected_tr_groups(make(tamriel_rebuilt_daedric_quests=True)), [])
check('TR daedric with daedric_quests', opts.selected_tr_groups(make(daedric=True, tamriel_rebuilt_daedric_quests=True)),
      ['tr_daedric'])
check('indoril goal', opts.selected_goals(make(house='indoril')), ['main_quest', 'indoril'])
check('ja_natta goal', opts.selected_goals(make(faction='ja_natta_syndicate')), ['main_quest', 'ja_natta_syndicate'])
check('indoril option value', getattr(opts.GreatHouse, 'option_indoril', None), 4)
check('ja_natta option value', getattr(opts.Faction, 'option_ja_natta_syndicate', None), 6)

# ---- groups ------------------------------------------------------------------
check('goal of tr_main', opts.goal_of_group('tr_main'), 'tamriel_rebuilt_main')
check('goal of tr_daedric', opts.goal_of_group('tr_daedric'), 'daedric_quests')
check('goal of tr_hlaalu', opts.goal_of_group('tr_hlaalu'), 'hlaalu')
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
check('no unverified TR goal', opts.UNVERIFIED_GOALS, ())
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

# ---- classification (IDs confirmed on UESP) -----------------------------------
cats = {'main': {'tr_m1_fm_x'}, 'main_prefixes': (), 'daedric': {'tr_m1_da_y'}, 'daedric_prefixes': (),
        'tokens': dict(qg.DEFAULT_TR_TOKENS)}
for q, want in {
    'TR_m4_HH_Ulvo4': 'tr_hlaalu', 'TR_m2_HT_Vaerin_q2': 'tr_telvanni', 'TR_m3_TT_Lloris1c': 'tr_temple',
    'TR_m7_Ns_JNS_7': 'tr_ja_natta_syndicate', 'TR_m3_Kha_UndyingRivalry': 'tr_side',
    'TR_m3_OE_OhWhatCustoms': 'tr_side', 'TR_m7_Ida_Net': 'tr_side', 'TR_m4_wil_TaxmanIndalruhn': 'tr_side',
    'TR_m1_FM_X': 'tr_main', 'TR_m1_DA_Y': 'tr_daedric',
}.items():
    check(f'classify {q}', qg.classify(q, None, None, cats), want)
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
