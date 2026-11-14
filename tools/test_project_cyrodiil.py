"""Tests of the Project Cyrodiil options and classification (no Archipelago needed).

From the repository root:
    python3 tools/test_project_cyrodiil.py
"""
import importlib.util
import pathlib
import re
import sys
import types

fake = types.ModuleType('Options')
for name, default in (('Toggle', 0), ('Choice', 0), ('DefaultOnToggle', 1),
                      ('PerGameCommonOptions', None), ('Range', 0)):
    setattr(fake, name, type(name, (), {'default': default}))
fake.OptionSet = type('OptionSet', (), {'default': frozenset(), 'valid_keys': frozenset(),
                                          '__init__': lambda self, value: setattr(self, 'value', set(value))})
sys.modules['Options'] = fake

root = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('mw_options', root / 'apworld/morrowind_openmw/options.py')
opts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opts)
sys.path.insert(0, str(root / 'tools'))
import quest_groups as qg  # noqa: E402
import extract  # noqa: E402
import yaml  # noqa: E402


class Val:
    def __init__(self, v): self.value = v
class Key:
    def __init__(self, k): self.current_key = k

class Set:
    """Fake OptionSet value (guild / faction): 'none' -> empty, a key -> {key}, a list -> set."""
    def __init__(self, k):
        self.value = set() if k in ('none', None) else ({k} if isinstance(k, str) else set(k))


def make(main=True, house='none', guild='none', faction='none', daedric=False, **kw):
    o = types.SimpleNamespace(main_quest=Val(main), great_house=Key(house), guild=Set(guild),
                              faction=Set(faction), daedric_quests=Val(daedric))
    for k, v in kw.items():
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


# ---- sync apworld <-> tools ------------------------------------------------------
check('PC groups in sync', opts.PC_GROUPS, qg.PC_GROUPS)
check('PC faction keys in sync', opts.PC_FACTION_KEYS, qg.PC_FACTION_KEYS)
goals = yaml.safe_load((root / 'data/goals.yaml').read_text())
check('every PC faction key is a goal key', all(k in goals for k in opts.PC_FACTION_KEYS), True)
check('PC goals are verified', any(k in opts.UNVERIFIED_GOALS for k in opts.PC_FACTION_KEYS), False)
for k, fid in (('kingdom_of_anvil', 'T_Cyr_KingdomAnvil'), ('itinerant_priests', 'T_Cyr_ItinerantPriests'),
               ('cyrodiil_fighters_guild', 'T_Cyr_FightersGuild'), ('cyrodiil_mages_guild', 'T_Cyr_MagesGuild'),
               ('cyrodiil_thieves_guild', 'T_Cyr_ThievesGuild')):
    check(f'{k} faction id', (goals[k]['faction'], goals[k]['rank']), (fid, 10))
_items = (root / 'apworld/morrowind_openmw/items.py').read_text(encoding='utf-8')
_lua = (root / 'mod/scripts/ap/faction_requirements.lua').read_text(encoding='utf-8')
for i, k in enumerate(('kingdom_of_anvil', 'itinerant_priests')):
    check(f'{k} requirement item in items.py', bool(re.search(rf'"{k}": \(BASE_ITEM \+ {514 + i},', _items)), True)
    check(f'{k} requirement id in Lua', f'{k} = {7701514 + i}' in _lua, True)
for k, base in (('cyrodiil_fighters_guild', 'fighters_guild'), ('cyrodiil_mages_guild', 'mages_guild'),
                ('cyrodiil_thieves_guild', 'thieves_guild')):
    check(f'{k} shares the {base} requirement item (items.py)', f'"{k}": "{base}"' in _items, True)
    check(f'{k} shares the {base} requirement item (Lua)', f"{k} = '{base}'" in _lua, True)
    check(f'{k} has no item of its own', f'"{k}": (BASE_ITEM' in _items, False)
check('goals.lua knows the PC goals', all(k + ' = {' in (root / 'mod/scripts/ap/goals.lua').read_text() for k in opts.PC_FACTION_KEYS), True)

# ---- options -----------------------------------------------------------------------
check('default: no PC group', opts.selected_pc_groups(make()), [])
check('PC side quests: group', opts.selected_pc_groups(make(project_cyrodiil_side_quests=True)), ['pc_side'])
check('pc_side is free', opts.is_free_group('pc_side'), True)
check('pc_side active with the option', opts.group_active(make(project_cyrodiil_side_quests=True), 'pc_side'), True)
check('pc_side inactive without the option', opts.group_active(make(), 'pc_side'), False)
check('PC faction is not a free group', opts.is_free_group('kingdom_of_anvil'), False)
check('Anvil goal', opts.selected_goals(make(faction='kingdom_of_anvil')), ['main_quest', 'kingdom_of_anvil'])
check('Cyrodiil Mages Guild goal', opts.selected_goals(make(main=False, guild='cyrodiil_mages_guild')),
      ['cyrodiil_mages_guild'])
check('PC faction group follows its goal', opts.goal_of_group('itinerant_priests'), 'itinerant_priests')
check('PC faction group active when chosen', opts.group_active(make(faction='itinerant_priests'), 'itinerant_priests'), True)
check('PC faction group inactive otherwise', opts.group_active(make(), 'itinerant_priests'), False)
check('PC guild distinct from the vanilla guild',
      opts.group_active(make(guild='mages_guild'), 'cyrodiil_mages_guild'), False)
check('Faction option keys', {'kingdom_of_anvil', 'itinerant_priests'} <= set(opts.Faction.valid_keys), True)
check('Guild option keys', {'cyrodiil_fighters_guild', 'cyrodiil_mages_guild', 'cyrodiil_thieves_guild'}
      <= set(opts.Guild.valid_keys), True)
check('several guilds + factions at once',
      opts.selected_goals(make(main=False, guild=['cyrodiil_thieves_guild', 'cyrodiil_mages_guild'],
                               faction=['itinerant_priests', 'kingdom_of_anvil'])),
      ['cyrodiil_mages_guild', 'cyrodiil_thieves_guild', 'kingdom_of_anvil', 'itinerant_priests'])


# ---- early-access mods: the goal also accepts "every quest of the group completed" ----------
import pathlib as _pl, yaml as _yaml
_root = _pl.Path(__file__).resolve().parent.parent
_goals = _yaml.safe_load((_root / 'data/goals.yaml').read_text(encoding='utf-8'))
_cp = next(p for p in (_root / 'data/quest_completions.yaml', _root / 'apworld/morrowind_openmw/data/quest_completions.yaml') if p.exists())
_rows = _yaml.safe_load(_cp.read_text(encoding='utf-8'))
for _k in ('kingdom_of_anvil', 'itinerant_priests', 'cyrodiil_fighters_guild', 'cyrodiil_mages_guild', 'cyrodiil_thieves_guild'):
    check(f'{_k}: goal has a group condition', _goals[_k].get('group'), _k)
    check(f'{_k}: goal keeps the rank condition', _goals[_k].get('rank'), 10)
    check(f'{_k}: group has quests', any(r.get('group') == _k for r in _rows), True)
_lua = (_root / 'mod/scripts/ap/goals.lua').read_text(encoding='utf-8')
check('goals.lua carries the group', all(f"group = '{_k}'" in _lua for _k in ('kingdom_of_anvil', 'itinerant_priests', 'cyrodiil_fighters_guild', 'cyrodiil_mages_guild', 'cyrodiil_thieves_guild')), True)

# ---- classification (journal IDs seen on UESP) -----------------------------------------
cases = {
    'PC_m1_IP_Lki4': 'itinerant_priests',       # The Drowned
    'PC_m1_IP_Run1LE': 'itinerant_priests',     # Alms for the Hostel of Saint Rosunius (sub-journal)
    'PC_m1_IP_HY4A': 'itinerant_priests',
    'PC_m1_K1_MC1': 'kingdom_of_anvil',         # Ashes of the Missing (numbered token K1)
    'PC_m1_MG_Anv6': 'cyrodiil_mages_guild',    # token MG, then place token Anv
    'PC_m1_Anv_WellMet': 'pc_side',             # misc quest: place token only
    'PC_m1_Anv_CallTribe': 'pc_side',
}
for qid, want in cases.items():
    check(f'pc_group {qid}', qg.pc_group(qid, qg.load_pc_categories(root / 'data/pc_categories.yaml')), want)
    check(f'classify {qid} (prefix rule)', qg.classify(qid), want)
check('a PC journal never lands in a TR group', qg.classify('PC_m1_IP_Lki4') in qg.TR_GROUPS, False)
check('TR journals unchanged', qg.classify('TR_m4_HH_Ulvo4'), 'tr_hlaalu')
check('vanilla journals unchanged', qg.classify('MG_Apprentice'), 'mages_guild')
check('origin of a Cyr_Main dump', extract.origin_of('build/cyr_main.json'), 'project_cyrodiil')
check('origin of a TR dump unchanged', extract.origin_of('build/tr_mainland.json'), 'tamriel_rebuilt')
check('origin override: a journal defined by Cyr_Main',
      qg.classify('Whatever_Quest', {'whatever_quest': 'project_cyrodiil'}), 'pc_side')
check('PC stages are skipped like TR ones in extract.py', 'kingdom_of_anvil' in qg.PC_GROUPS, True)

print(f'\n{fails} failure(s)')
sys.exit(1 if fails else 0)
