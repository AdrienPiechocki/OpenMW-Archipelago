"""Tests of the quest-lock item gating (no Archipelago needed).

The TR Daedric locks must only create their item (and only be required by the
logic) when both `daedric_quests` and `tamriel_rebuilt_daedric_quests` are
enabled. From the repository root:
    python3 tools/test_quest_locks.py
"""
import importlib.util
import pathlib
import shutil
import sys
import tempfile
import types

# Fake `Options` module: just enough to import options.py.
fake = types.ModuleType('Options')
for name, default in (('Toggle', 0), ('Choice', 0), ('DefaultOnToggle', 1),
                      ('PerGameCommonOptions', None), ('Range', 0)):
    setattr(fake, name, type(name, (), {'default': default}))
sys.modules['Options'] = fake

# Fake BaseClasses: only Item and ItemClassification are used by items.py.
base = types.ModuleType('BaseClasses')
base.Item = type('Item', (), {})
classification = type('ItemClassification', (), {
    'filler': 'filler', 'progression': 'progression',
    'useful': 'useful', 'trap': 'trap',
})
base.ItemClassification = classification
sys.modules['BaseClasses'] = base

root = pathlib.Path(__file__).resolve().parent.parent


def load_package(pkgdir, pkgname):
    """Load options.py + items.py as a package, with data from pkgdir/data."""
    pkg = types.ModuleType(pkgname)
    pkg.__path__ = [str(pkgdir)]
    sys.modules[pkgname] = pkg

    def load(name):
        spec = importlib.util.spec_from_file_location(f'{pkgname}.{name}', pkgdir / f'{name}.py')
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'{pkgname}.{name}'] = mod
        spec.loader.exec_module(mod)
        return mod

    return load


class Val:
    def __init__(self, v): self.value = v


class Key:
    def __init__(self, k): self.current_key = k


def make(daedric, tr_daedric, **extra):
    o = types.SimpleNamespace(
        main_quest=Val(True), great_house=Key('none'), guild=Key('none'),
        faction=Key('none'), daedric_quests=Val(daedric),
        tamriel_rebuilt_daedric_quests=Val(tr_daedric))
    for k, v in extra.items():
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


with tempfile.TemporaryDirectory() as td:
    pkgdir = pathlib.Path(td) / 'mw_lock_test'
    (pkgdir / 'data').mkdir(parents=True)
    for name in ('options.py', 'items.py'):
        shutil.copy(root / 'apworld/morrowind_openmw' / name, pkgdir / name)
    for name in ('quest_locks.yaml', 'quest_items.yaml'):
        shutil.copy(root / 'data' / name, pkgdir / 'data' / name)
    load = load_package(pkgdir, 'mw_lock_test')
    opts = load('options')
    items = load('items')

    on = make(True, True)
    off = make(True, False)

    namira = items.item_table['Daedric Quest: Namira']
    azura = items.item_table['Daedric Quest: Azura']
    check('TR lock item created when both options on', namira.can_create(on), True)
    check('TR lock item absent without TR option', namira.can_create(off), False)
    check('TR lock item absent without daedric goal',
          namira.can_create(make(False, True)), False)
    check('vanilla lock item always created', azura.can_create(off), True)

    names_on = items.quest_item_names('daedric_quests', on)
    names_off = items.quest_item_names('daedric_quests', off)
    check('logic requires the 4 TR lock items when enabled',
          sum(1 for n in names_on if n in {
              'Daedric Quest: Clavicus Vile', 'Daedric Quest: Sanguine',
              'Daedric Quest: Meridia', 'Daedric Quest: Namira'}), 4)
    check('logic ignores the TR lock items when disabled',
          any(n.startswith('Daedric Quest: Clavicus') for n in names_off), False)
    check('vanilla daedric requirements unchanged', len(names_off), 10)
    check('daedric requirements with TR', len(names_on), 14)
    check('item and goal gating agree', opts.group_enabled(on, 'tr_daedric'), True)
    check('group disabled without TR option',
          opts.group_enabled(off, 'tr_daedric'), False)

if fails:
    print(f'{fails} failure(s)')
    sys.exit(1)
print('all quest lock tests passed')
