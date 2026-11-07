"""Test of the expansion options (main / faction / side) without Archipelago.

From the repository root:
    python3 tools/test_expansion_options.py
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
import quest_names as qn  # noqa: E402


class Val:
    def __init__(self, v): self.value = v
class Key:
    def __init__(self, k): self.current_key = k


def make(main=True, **exp):
    o = types.SimpleNamespace(main_quest=Val(main), great_house=Key('none'), guild=Key('none'),
                              faction=Key('none'), daedric_quests=Val(False))
    for k, v in exp.items():
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


check('default: no expansion group', opts.selected_expansion_groups(make()), [])
check('default goals', opts.selected_goals(make()), ['main_quest'])
check('tribunal side only: check, no goal', opts.selected_goals(make(tribunal_side_quests=True)), ['main_quest'])
check('tribunal side only: group', opts.selected_expansion_groups(make(tribunal_side_quests=True)), ['tribunal_side'])
check('tribunal main = goal', opts.selected_goals(make(main=False, tribunal_main_quest=True)), ['tribunal'])
check('bloodmoon side only', opts.selected_expansion_groups(make(bloodmoon_side_quests=True)), ['bloodmoon_side'])
check('expansions (informational)', opts.selected_expansions(make(bloodmoon_side_quests=True, tribunal_side_quests=True)),
      ['tribunal', 'bloodmoon'])
check('all four', len(opts.selected_expansion_groups(make(**{f'{e}_{s}': True for e in opts.EXPANSIONS
      for s in opts.EXPANSION_CATEGORY_OPTIONS.values()}))), 4)
check('no goal when main off + side only', opts.selected_goals(make(main=False, tribunal_side_quests=True)), [])
check('groups are free groups', all(opts.is_free_group(g) for g in opts.EXPANSION_GROUPS), True)
check('same groups as quest_groups.py', opts.EXPANSION_GROUPS, qg.EXPANSION_GROUPS)

check('no faction toggle', hasattr(opts, 'TribunalFactionQuests') or hasattr(opts, 'BloodmoonFactionQuests'), False)
check('EEC is a faction choice', getattr(opts.Faction, 'option_east_empire_company', None), 5)

cats = {'main': {'tr_sothasil'}, 'side': set(), 'east_empire_company': {'bm_eec_x'}, 'eec_prefixes': ('co_',)}
ov = {'tr_sothasil': 'tribunal', 'tr_misc': 'tribunal', 'co_1': 'bloodmoon', 'bm_eec_x': 'bloodmoon',
      'bm_other': 'bloodmoon', 'co_t': 'tribunal'}
check('classify main', qg.classify('tr_sothasil', ov, cats), 'tribunal_main')
check('classify side', qg.classify('tr_misc', ov, cats), 'tribunal_side')
check('EEC by prefix (bloodmoon)', qg.classify('co_1', ov, cats), 'east_empire_company')
check('EEC by id (bloodmoon)', qg.classify('bm_eec_x', ov, cats), 'east_empire_company')
check('EEC prefix ignored for tribunal', qg.classify('co_t', ov, cats), 'tribunal_side')
check('bloodmoon side', qg.classify('bm_other', ov, cats), 'bloodmoon_side')
check('vanilla untouched', qg.classify('a1_1_findspymaster', ov, cats), 'main')
check('vanilla eb_ untouched', qg.classify('eb_actor', ov, cats), 'east_empire')
check('manual subgroup override', qg.classify('x', {'x': 'bloodmoon_main'}, cats), 'bloodmoon_main')
check('EEC goal key', opts.goal_of_group('east_empire_company'), 'east_empire_company')

# EEC journals (CO_<n>[letter]): no more "Co_1" / "A - A" / "B".
rows = [{'quest': q, 'group': 'east_empire_company'} for q in ('CO_1', 'CO_1A', 'CO_2A', 'CO_3A', 'CO_3B', 'CO_13')]
check('EEC names', sorted(qn.unique_names(rows, {}).values()),
      ['Raven Rock Colony 1', 'Raven Rock Colony 13', 'Raven Rock Colony 1A', 'Raven Rock Colony 2A',
       'Raven Rock Colony 3A', 'Raven Rock Colony 3B'])

if fails:
    print(f'{fails} failure(s)')
    sys.exit(1)
print('all expansion tests passed')
