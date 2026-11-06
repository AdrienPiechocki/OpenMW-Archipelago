"""Test de selected_goals() (option main_quest) sans Archipelago installe.

Depuis la racine du depot :
    python3 tools/test_selected_goals.py
"""
import importlib.util
import pathlib
import sys
import types

# Faux module `Options` : juste de quoi importer options.py.
fake = types.ModuleType('Options')
# Comme dans Archipelago : Toggle vaut 0 par defaut, DefaultOnToggle 1.
for name, default in (('Toggle', 0), ('Choice', 0), ('DefaultOnToggle', 1), ('PerGameCommonOptions', None)):
    setattr(fake, name, type(name, (), {'default': default}))
sys.modules['Options'] = fake

path = pathlib.Path(__file__).resolve().parent.parent / 'apworld/morrowind_openmw/options.py'
spec = importlib.util.spec_from_file_location('mw_options', path)
opts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opts)


class Val:
    def __init__(self, value):
        self.value = value


class Key:
    def __init__(self, key):
        self.current_key = key


def make(main=True, house='none', guild='none', faction='none', daedric=False, with_main=True,
         gqc=None):
    o = types.SimpleNamespace(great_house=Key(house), guild=Key(guild), faction=Key(faction),
                              daedric_quests=Val(daedric))
    if gqc is not None:
        o.goal_quest_checks = Val(gqc)
    if with_main:
        o.main_quest = Val(main)
    return o


fails = 0


def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f'FAIL {name}: got {got!r}, want {want!r}')
    else:
        print(f'ok   {name}')


check('default', opts.selected_goals(make()), ['main_quest'])
check('option absent -> main quest', opts.selected_goals(make(with_main=False)), ['main_quest'])
check('main off + house', opts.selected_goals(make(main=False, house='hlaalu')), ['hlaalu'])
check('main off + daedric', opts.selected_goals(make(main=False, daedric=True)), ['daedric_quests'])
check('main off + several', opts.selected_goals(
    make(main=False, house='redoran', guild='mages_guild', faction='temple', daedric=True)),
    ['redoran', 'mages_guild', 'temple', 'daedric_quests'])
check('main on + house', opts.selected_goals(make(house='hlaalu')), ['main_quest', 'hlaalu'])
# Sans aucun objectif : liste vide (generate_early leve alors une OptionError).
check('nothing selected', opts.selected_goals(make(main=False)), [])
# goal_quest_checks : simple on / off (on = ancien 'full', code 2 pour le mod).
check('goal checks on', opts.goal_quest_mode(make(gqc=1)), 2)
check('goal checks off', opts.goal_quest_mode(make(gqc=0)), 0)
check('goal checks absent', opts.goal_quest_mode(make()), 0)
check('GoalQuestChecks is on by default', opts.GoalQuestChecks.default, 1)
check('quest_granularity removed', hasattr(opts, 'QuestGranularity'), False)
check('no granularity field', 'quest_granularity' in opts.MorrowindOptions.__annotations__, False)
check('MainQuest option exists', hasattr(opts, 'MainQuest'), True)
check('dataclass field', 'main_quest' in opts.MorrowindOptions.__annotations__, True)

if fails:
    print(f'{fails} failure(s)')
    sys.exit(1)
print('all selected_goals tests passed')
