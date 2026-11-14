"""Tests of the Skyrim: Home of the Nords options and classification (no Archipelago needed).

From the repository root:
    python3 tools/test_skyrim.py
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


def make(main=True, house='none', guild='none', faction='none', daedric=False, **kw):
    o = types.SimpleNamespace(main_quest=Val(main), great_house=Key(house), guild=Key(guild),
                              faction=Key(faction), daedric_quests=Val(daedric))
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
check('Sky groups in sync', opts.SKY_GROUPS, qg.SKY_GROUPS)
check('Sky faction keys in sync', opts.SKY_FACTION_KEYS, qg.SKY_FACTION_KEYS)
goals = yaml.safe_load((root / 'data/goals.yaml').read_text())
check('every Sky guild key is a goal key', all(k in goals for k in opts.SKY_FACTION_KEYS), True)
check('thieves guild id is the confirmed one', goals['skyrim_thieves_guild']['faction'], 'T_Sky_ThievesGuild')
check('no unverified Sky goal', [k for k in opts.SKY_FACTION_KEYS if k in opts.UNVERIFIED_GOALS], [])
for k, fid in (('skyrim_fighters_guild', 'T_Sky_FightersGuild'), ('skyrim_mages_guild', 'T_Sky_MagesGuild'),
               ('skyrim_thieves_guild', 'T_Sky_ThievesGuild'), ('hammerfell_mages_guild', 'T_Ham_MagesGuild')):
    check(f'{k} faction id', (goals[k]['faction'], goals[k]['rank']), (fid, 10))
_items = (root / 'apworld/morrowind_openmw/items.py').read_text(encoding='utf-8')
_lua = (root / 'mod/scripts/ap/faction_requirements.lua').read_text(encoding='utf-8')
for i, k in enumerate(opts.SKY_FACTION_KEYS):
    check(f'{k} requirement item in items.py', bool(re.search(rf'"{k}": \(BASE_ITEM \+ {519 + i},', _items)), True)
    check(f'{k} requirement id in Lua', f'{k} = {7701519 + i}' in _lua, True)
check('goals.lua knows the Sky goals', all(k + ' = {' in (root / 'mod/scripts/ap/goals.lua').read_text() for k in opts.SKY_FACTION_KEYS), True)
check('player.lua lets sky_side through', "group == 'sky_side'" in (root / 'mod/scripts/ap/player.lua').read_text(), True)

# ---- options ---------------------------------------------------------------------
check('default: no Sky group', opts.selected_sky_groups(make()), [])
check('side quests: group', opts.selected_sky_groups(make(skyrim_side_quests=True)), ['sky_side'])
check('sky_side is free', opts.is_free_group('sky_side'), True)
check('sky_side active with the option', opts.group_active(make(skyrim_side_quests=True), 'sky_side'), True)
check('sky_side inactive without the option', opts.group_active(make(), 'sky_side'), False)
check('Sky guild is not a free group', opts.is_free_group('skyrim_mages_guild'), False)
check('Sky guild goal', opts.selected_goals(make(guild='skyrim_thieves_guild')), ['main_quest', 'skyrim_thieves_guild'])
check('Sky guild group active when chosen', opts.group_active(make(guild='hammerfell_mages_guild'), 'hammerfell_mages_guild'), True)
check('Sky guild distinct from the vanilla one', opts.group_active(make(guild='mages_guild'), 'skyrim_mages_guild'), False)
check('Sky guild distinct from the PC one', opts.group_active(make(guild='cyrodiil_mages_guild'), 'skyrim_mages_guild'), False)
check('Guild option values', (opts.Guild.option_skyrim_fighters_guild, opts.Guild.option_skyrim_mages_guild,
                              opts.Guild.option_hammerfell_mages_guild, opts.Guild.option_skyrim_thieves_guild), (7, 8, 9, 10))

# ---- classification (journal IDs seen on UESP) -----------------------------------------
cases = {
    'Sky_qRe_KWMG5_Journal': 'skyrim_mages_guild',        # Turbulent Teleporting
    'Sky_qRe_KWMG5a_Journal': 'skyrim_mages_guild',
    'Sky_qRe_DSMG4_Journal': 'hammerfell_mages_guild',    # Public Perception
    'Sky_qRe_DSMG4c_Journal': 'hammerfell_mages_guild',
    'Sky_qRe_DSTG1_Journal': 'skyrim_thieves_guild',      # Census and Excess
    'Sky_qRe_DSTG3a_Journal': 'skyrim_thieves_guild',
    'Sky_qRe_KWTG5_Journal': 'skyrim_thieves_guild',      # A Curious Concoction
    'Sky_qRe_KWTG8c_Journal': 'skyrim_thieves_guild',
    'Sky_qRe_KWFG1_Journal': 'skyrim_fighters_guild',     # confirmed in the ESM
    'Sky_qRe_KWFG4_Journal': 'skyrim_fighters_guild',
    'Sky_MG_Advancement': 'skyrim_mages_guild',           # counterpart of vanilla MG_Advancement
    'Sky_qRe_KW8_Journal': 'sky_side',                    # Brokk's Bundles of Barley
    'Sky_qRe_KW1b_Journal': 'sky_side',                   # Direnni Registers
    'Sky_qRe_DSW2_Journal': 'sky_side',                   # The Missing Skull
    'Sky_qRe_DSE4_Journal': 'sky_side',                   # The Dragonstar Arena
    'Sky_qRe_KW_B04_JournalA': 'sky_side',                # Bounty: Tharag gro-Kul and Meshif
    'Sky_qRe_KWB03_Journal': 'sky_side',                  # Bounty: Uldar Ember-Seeker
    'Sky_qRe_KWB05_JournalA': 'sky_side',
}
sc = qg.load_sky_categories(root / 'data/sky_categories.yaml')
for qid, want in cases.items():
    check(f'sky_group {qid}', qg.sky_group(qid, sc), want)
    check(f'classify {qid} (prefix rule)', qg.classify(qid), want)
check('a Sky journal never lands in a TR or PC group', qg.classify('Sky_qRe_KWMG5_Journal') in qg.TR_GROUPS + qg.PC_GROUPS, False)
check('PC journals unchanged', qg.classify('PC_m1_IP_Lki4'), 'itinerant_priests')
check('TR journals unchanged', qg.classify('TR_m4_HH_Ulvo4'), 'tr_hlaalu')
check('vanilla journals unchanged', qg.classify('MG_Apprentice'), 'mages_guild')
check('origin of a Sky_Main dump', extract.origin_of('build/sky_main.json'), 'skyrim_hotn')
check('origin of a Cyr_Main dump unchanged', extract.origin_of('build/cyr_main.json'), 'project_cyrodiil')
check('origin override: a journal defined by Sky_Main',
      qg.classify('Whatever_Quest', {'whatever_quest': 'skyrim_hotn'}), 'sky_side')
check('user pattern in sky_categories.yaml wins', qg.sky_group('Sky_qRe_KWX1_Journal', {
    'side': set(), 'patterns': [(re.compile('^sky_qre_kwx'), 'skyrim_fighters_guild')] + sc['patterns']}), 'skyrim_fighters_guild')

print(f'\n{fails} failure(s)')
sys.exit(1 if fails else 0)
