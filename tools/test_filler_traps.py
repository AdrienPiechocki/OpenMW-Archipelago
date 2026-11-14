"""Tests of the varied filler and of the trap percentage (no Archipelago needed).

    python3 tools/test_filler_traps.py
"""
import importlib.util, pathlib, re, sys, types, random, collections

fake = types.ModuleType('Options')
for name, default in (('Toggle', 0), ('Choice', 0), ('DefaultOnToggle', 1), ('PerGameCommonOptions', None), ('Range', 0)):
    setattr(fake, name, type(name, (), {'default': default}))
sys.modules['Options'] = fake
base = types.ModuleType('BaseClasses')
base.Item = type('Item', (), {})
base.ItemClassification = type('ItemClassification', (), {'filler': 'filler', 'progression': 'progression',
                                                           'useful': 'useful', 'trap': 'trap'})
sys.modules['BaseClasses'] = base
root = pathlib.Path(__file__).resolve().parent.parent
pkgdir = root / 'apworld/morrowind_openmw'
pkg = types.ModuleType('mw'); pkg.__path__ = [str(pkgdir)]; sys.modules['mw'] = pkg
for n in ('options', 'items'):
    spec = importlib.util.spec_from_file_location(f'mw.{n}', pkgdir / f'{n}.py')
    m = importlib.util.module_from_spec(spec); sys.modules[f'mw.{n}'] = m; spec.loader.exec_module(m)
items, opts = sys.modules['mw.items'], sys.modules['mw.options']

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1; print(f'FAIL {name}: got {got!r}, want {want!r}')
    else:
        print(f'ok   {name}')

codes = [d.code for d in items.item_table.values() if d.code is not None]
# (quest items shared by several goals legitimately share a code: only filler / traps are checked)
own = [c for c, _w in list(items.FILLER.values()) + list(items.TRAPS.values())]
check('filler / trap codes unique and not reused', [codes.count(c) for c in own], [1] * len(own))
check('filler / trap names not shadowed by quest items', [n for n in list(items.FILLER) + list(items.TRAPS) if items.item_table[n].code != (items.FILLER.get(n) or items.TRAPS[n])[0]], [])
check('filler is varied (>= 10 kinds)', len(items.FILLER) >= 10, True)
check('traps are varied (>= 6 kinds)', len(items.TRAPS) >= 6, True)
check('filler classification', {items.item_table[n].classification for n in items.FILLER}, {'filler'})
check('trap classification', {items.item_table[n].classification for n in items.TRAPS}, {'trap'})
check('not added one by one', {items.item_table[n].frequency for n in list(items.FILLER) + list(items.TRAPS)}, {0})
check('gold is no longer the majority', items.FILLER_WEIGHTS['Gold (100)'] / sum(items.FILLER_WEIGHTS.values()) < 0.3, True)
draw = collections.Counter(random.Random(1).choices(list(items.FILLER_WEIGHTS), weights=list(items.FILLER_WEIGHTS.values()), k=2000))
check('draw: every filler can come out', set(draw), set(items.FILLER))
check('trap_percentage option', (opts.TrapPercentage.range_start, opts.TrapPercentage.range_end, opts.TrapPercentage.default), (0, 100, 10))
check('trap_percentage in options dataclass', 'trap_percentage: TrapPercentage' in (pkgdir / 'options.py').read_text(), True)

# Lua <-> apworld sync: every filler / trap code is handled by items.lua
lua = (root / 'mod/scripts/ap/items.lua').read_text(encoding='utf-8')
give = {int(x) for x in re.findall(r"\[(7701\d{3})\]\s*=\s*\{\s*'", lua)}
filler_codes = {c for c, _w in items.FILLER.values()}
check('Lua GIVE covers every filler', filler_codes <= give, True)
summons = {int(x) for x in re.findall(r"\[(7701\d{3})\]\s*=\s*\{\s*'[^']+',\s*\d+\s*\}", lua)} - filler_codes
drains = {int(x) for x in re.findall(r"\[(7701\d{3})\]\s*=\s*'(?:fatigue|magicka)'", lua)}
handled = summons | drains | {7701200, 7701201, 7701203}
check('Lua handles every trap', {c for c, _w in items.TRAPS.values()} <= handled, True)
print('FAILED' if fails else 'all filler / trap tests passed')
sys.exit(1 if fails else 0)
