"""Test of the vampire clan category (option vampire_clan).

A player belongs to ONE clan, so only the quests open to any bloodline + the chosen clan's give checks,
and the final quest of the chosen clan is a goal.

    python3 tools/test_vampire_options.py
"""
import importlib.util, pathlib, sys, types, yaml

fake = types.ModuleType('Options')
for name, default in (('Toggle', 0), ('Choice', 0), ('DefaultOnToggle', 1),
                      ('PerGameCommonOptions', None), ('Range', 0)):
    setattr(fake, name, type(name, (), {'default': default}))
fake.OptionSet = type('OptionSet', (), {'default': frozenset(), 'valid_keys': frozenset(),
                                          '__init__': lambda self, value: setattr(self, 'value', set(value))})
sys.modules['Options'] = fake
root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('mw_options', root / 'apworld/morrowind_openmw/options.py')
opts = importlib.util.module_from_spec(spec); spec.loader.exec_module(opts)
sys.path.insert(0, str(root / 'tools'))
import quest_groups as qg  # noqa: E402

class Val:
    def __init__(self, v): self.value = v
class Key:
    def __init__(self, k): self.current_key = k

class Set:
    """Fake OptionSet value (guild / faction): 'none' -> empty, a key -> {key}, a list -> set."""
    def __init__(self, k):
        self.value = set() if k in ('none', None) else ({k} if isinstance(k, str) else set(k))

def make(vampire_clan='none', **kw):
    o = types.SimpleNamespace(main_quest=Val(True), great_house=Key('none'), guild=Set('none'),
                              faction=Set('none'), daedric_quests=Val(False),
                              vampire_clan=Key(vampire_clan))
    for k, v in kw.items():
        setattr(o, k, Val(v))
    return o

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1; print(f'FAIL {name}: got {got!r}, want {want!r}')
    else:
        print(f'ok   {name}')

# vanilla
check('default: nothing', opts.selected_category_groups(make()), [])
check('unaligned: common quests only', opts.selected_category_groups(make('unaligned')), ['vampire'])
for c in ('aundae', 'berne', 'quarra'):
    check(f'clan {c}: common + own', opts.selected_category_groups(make(c)), ['vampire', f'vampire_{c}'])
check('other clans are never enabled together',
      [g for g in opts.selected_category_groups(make('berne')) if g in ('vampire_aundae', 'vampire_quarra')], [])
# goals: the final quest of the chosen clan
for c in ('aundae', 'berne', 'quarra'):
    check(f'goal of clan {c}', opts.selected_goals(make(c)), ['main_quest', f'vampire_{c}'])
check('unaligned: no goal', opts.selected_goals(make('unaligned')), ['main_quest'])
check('none: no goal', opts.selected_goals(make()), ['main_quest'])
check('TR baluath goal', opts.selected_goals(make('baluath')), ['main_quest', 'vampire_baluath'])
check('TR orlukh goal', opts.selected_goals(make('orlukh')), ['main_quest', 'vampire_orlukh'])
check('TR unaligned: no goal', opts.selected_goals(make('tamriel_rebuilt_unaligned')), ['main_quest'])
check('one clan only (vanilla clan: no TR goal)', opts.selected_goals(make('berne')), ['main_quest', 'vampire_berne'])
check('TR unaligned: no goal', opts.selected_goals(make('tamriel_rebuilt_unaligned')), ['main_quest'])
check('TR unaligned: no vanilla group', opts.selected_category_groups(make('tamriel_rebuilt_unaligned')), [])
check('TR clan: no vanilla group', opts.selected_category_groups(make('orlukh')), [])
check('vanilla unaligned: no TR group', [g for g in opts.selected_tr_groups(make('unaligned')) if 'vampire' in g], [])

# TR
check('TR default: nothing', [g for g in opts.selected_tr_groups(make()) if 'vampire' in g], [])
check('TR unaligned', opts.selected_tr_groups(make('tamriel_rebuilt_unaligned')), ['tr_vampire'])
check('TR baluath', opts.selected_tr_groups(make('baluath')), ['tr_vampire', 'tr_vampire_baluath'])
check('TR orlukh', opts.selected_tr_groups(make('orlukh')), ['tr_vampire', 'tr_vampire_orlukh'])
check('TR clan independent of tamriel_rebuilt_factions',
      'tr_vampire_orlukh' in opts.selected_tr_groups(make('orlukh', tamriel_rebuilt_factions=False)), True)
check('vanilla clan does not enable TR groups',
      [g for g in opts.selected_tr_groups(make('berne')) if 'vampire' in g], [])
# groups
allv = opts.CATEGORY_GROUPS + opts.TR_VAMPIRE_GROUPS
check('all vampire groups are free groups', all(opts.is_free_group(g) for g in allv), True)
check('group_enabled own clan', opts.group_enabled(make('berne'), 'vampire_berne'), True)
check('group_enabled other clan', opts.group_enabled(make('berne'), 'vampire_quarra'), False)
check('group_active TR clan', opts.group_active(make('baluath'), 'tr_vampire_baluath'), True)
check('group_active TR other clan', opts.group_active(make('baluath'), 'tr_vampire_orlukh'), False)
check('apworld groups in sync with quest_groups.py', (opts.TR_GROUPS, opts.CATEGORY_GROUPS),
      (qg.TR_GROUPS, qg.VAMPIRE_GROUPS))
check('Choice values', (opts.VampireClan.option_quarra, opts.VampireClan.option_baluath, opts.VampireClan.option_orlukh), (4, 5, 6))

# classification and generated data: UESP guide = 7 quests open to any bloodline + 2 per clan
ov = qg.load_overrides(root / 'data/quest_groups_override.yaml')
for q, g in (('va_vampblood', 'vampire_berne'), ('va_vampcountess', 'vampire_berne'),
             ('va_vampchild', 'vampire_aundae'), ('va_vamphunter', 'vampire_aundae'),
             ('va_vampcult', 'vampire_quarra'), ('va_vampamulet', 'vampire_quarra'),
             ('va_vamprich', 'vampire'), ('va_vampmarara', 'vampire'), ('va_vampcurse', 'vampire'),
             ('va_shashev', 'vampire'), ('va_vampdust', 'vampire'), ('va_rimintil', 'vampire'),
             ('va_vampblood2', 'vampire'), ('ms_vampirecure', 'non_quest'),
             ('tr_m4_bal1_hunter', 'tr_vampire_baluath'), ('tr_m4_va_invasion', 'tr_vampire_orlukh'),
             ('tr_m3_va_raenor', 'tr_vampire'), ('tr_m7_va_anivamp', 'tr_side'),
             ('tr_m4_va_barendrethprotection', 'tr_side'), ('tr_m4_va_ibinai', 'tr_side'),
             ('tr_m4_va_vrashmind', 'tr_side')):
    check(f'classify {q}', qg.classify(q, ov), g)
rows = yaml.safe_load((root / 'data/quest_completions.yaml').read_text(encoding='utf-8'))
count = {}
for r in rows:
    count[r.get('group')] = count.get(r.get('group'), 0) + 1
check('quest_completions: vanilla groups', [count.get(g) for g in qg.VAMPIRE_GROUPS], [7, 2, 2, 2])
check('quest_completions: TR groups', [count.get(g) for g in qg.TR_VAMPIRE_GROUPS], [1, 10, 11])
lua = (root / 'mod/scripts/ap/player.lua').read_text(encoding='utf-8')
check('Lua: clan groups enabled by expansion_groups',
      all(f'vampire_{c} = true' in lua for c in qg.VAMPIRE_CLANS), True)
# goals: data/goals.yaml -> Lua, with the completion condition of the quest's check
goals = yaml.safe_load((root / 'data/goals.yaml').read_text(encoding='utf-8'))
want = {'vampire_aundae': 'va_vamphunter', 'vampire_berne': 'va_vampcountess', 'vampire_quarra': 'va_vampamulet',
        'vampire_baluath': 'tr_m4_bal_killorlukh', 'vampire_orlukh': 'tr_m4_va_namira'}
check('goal quests', {k: goals[k]['quests'][0]['quest'] for k in want}, want)
check('goals use the check condition', all(goals[k]['quests'][0].get('complete') for k in want), True)
fin = {r['quest'].lower(): r for r in yaml.safe_load((root / 'data/quest_finals.yaml').read_text(encoding='utf-8'))}
check('goal stage = final stage of the quest', {k: goals[k]['quests'][0]['stage'] for k in want},
      {k: fin[q]['stage'] for k, q in want.items()})
check('goal quests cannot fail', [q for q in want.values() if fin[q]['fail']], [])
check('goal quests are in their clan group', {q: fin[q]['group'] for q in want.values()},
      {'va_vamphunter': 'vampire_aundae', 'va_vampcountess': 'vampire_berne', 'va_vampamulet': 'vampire_quarra',
       'tr_m4_bal_killorlukh': 'tr_vampire_baluath', 'tr_m4_va_namira': 'tr_vampire_orlukh'})
goals_lua = (root / 'mod/scripts/ap/goals.lua').read_text(encoding='utf-8')
check('goals.lua has complete = true', goals_lua.count('complete = true'), 5)
check('player.lua honours complete', 'if e.complete then' in lua, True)
rew = yaml.safe_load((root / 'data/quest_rewards.yaml').read_text(encoding='utf-8'))
bad = [r['name'] for r in rew if 'vampire' in r['group'] and r['group'] != qg.classify(str(r['quest']).lower(), ov)]
check('reward groups follow their quest', bad, [])

# A Cure for Vampirism: no check (non_quest) + held at stage 0 by the mod while a clan goal is selected
cure = 'ms_vampirecure'
check('cure: no check in any group', [r for r in rows if str((r.get('trigger') or {}).get('quest', '')).lower() == cure
                                      and r.get('group') != 'non_quest'], [])
fb = (root / 'mod/scripts/ap/quest_forbidden.lua').read_text(encoding='utf-8')
check('Lua forbidden: every clan goal (vanilla + TR)',
      all(f"'vampire_{c}'" in fb for c in qg.VAMPIRE_CLANS + ('baluath', 'orlukh')) and f"quest = '{cure}'" in fb, True)
check('player.lua enforces forbidden quests', 'enforceForbidden(quests)' in lua, True)
print('FAILED' if fails else 'all vampire tests passed')
sys.exit(1 if fails else 0)
