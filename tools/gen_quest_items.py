#!/usr/bin/env python3
"""Quest item candidates per goal, extracted from the ESM with filtering / Whitelist.

Only items NEEDED FOR PROGRESSION are kept, faction by faction:
  - RemoveItem   : item handed over to validate a step (quest turn-in);
  - Item filter  : item required in the inventory by the dialogue;
  - GetItemCount : item counted to validate a condition;
  - AddItem      : item given to the player DURING the quest, only if it is
                   validated by its faction's whitelist (otherwise it is a
                   reward, not a progression item).

Tamriel Rebuilt support:
  - Any journal id defined in a TR JSON (tr_mainland.json / tamriel_data.json)
    is routed to the single goal 'tamriel_rebuilt'.
  - TR items with a generic prefix (t_bk_, t_de_, t_imp_, t_com_, t_ing_,
    t_sc_, t_ensc_, t_dae_, ...) are treated as ambient unless their ID
    contains a unique marker (_unique, _uni, uni_, _reward).
  - TR uses a very low global-item threshold (TR_GLOBAL_ITEM_THRESHOLD=1)
    because with ~600 quests, an item mentioned in 2+ quests of the same
    faction is almost always a generic token, not a fetch item.

Filters applied to RemoveItem / Item filter / GetItemCount:
  * AMBIENT_ITEMS / AMBIENT_PREFIXES / TR_AMBIENT_PREFIXES : generic objects.
  * FACTION_GLOBAL_ITEMS : items that appear in every quest of a faction.
  * A frequency filter: any item that appears in more than N quests of the
    same faction is treated as a global token and dropped.
  * (option 2) Items whose ONLY evidence is a GetItemCount are dropped: a
    conditional read (`if GetItemCount "x" >= 1`) is not a fetch/turn-in
    and would create false cross-quest dependencies.
  * (new) The 't_ingmine_' prefix is treated as TR ambient: raw ore items
    (T_IngMine_OreGold_01, T_IngMine_OreIron_01, ...) are trade goods, not
    quest items. They were previously slipping through because the prefix
    list only had 't_ing_' (with underscore), not 't_ingmine_'.

FIX (canonical case): ESM record IDs are case-sensitive in the engine
(e.g. 'TR_m2_q_18_Potion', not 'tr_m2_q_18_potion'). The YAML now stores
the canonical ID as it appears in the ESM, so the game / mod can resolve
the item without relying on a case-insensitive lookup. Matching against
script text / dialogue filters stays case-insensitive.

The 'via' field is preserved in the final YAML so the canonical tree
(tools/rebase_quest_tree.py) can distinguish real progression items from
GetItemCount-only false positives.

Usage:
  python tools/gen_quest_items.py build/morrowind.json build/bloodmoon.json --apply
  python tools/gen_quest_items.py build/morrowind.json build/bloodmoon.json \\
      build/tr_mainland.json build/tamriel_data.json --apply
"""
import argparse
import collections
import json
import pathlib
import re
import sys
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quest_groups import classify, load_overrides  # noqa: E402

PAT_JOURNAL_Q = re.compile(r'(?<![A-Za-z])Journal[ \t]*,?[ \t]*"([^"\r\n]+)"[ \t]*,?[ \t]*\d+', re.I)
PAT_JOURNAL_B = re.compile(r'(?<![A-Za-z])Journal[ \t]*,?[ \t]*([A-Za-z_][A-Za-z0-9_\-]*)[ \t]*,?[ \t]*\d+', re.I)
PAT_ADD = re.compile(r'AddItem[ \t]*,?[ \t]*"?([^"\s,]+)"?(?:[ \t]*,?[ \t]*(\d+))?', re.I)
PAT_REMOVE = re.compile(r'RemoveItem[ \t]*,?[ \t]*"?([^"\s,]+)"?(?:[ \t]*,?[ \t]*(\d+))?', re.I)
PAT_COUNT = re.compile(r'GetItemCount[ \t]*,?[ \t]*"?([^"\s,)]+)"?', re.I)

GOAL_OF_GROUP = {
    'main': 'main_quest', 'daedric': 'daedric_quests',
    'hlaalu': 'hlaalu', 'redoran': 'redoran', 'telvanni': 'telvanni',
    'fighters_guild': 'fighters_guild', 'mages_guild': 'mages_guild',
    'thieves_guild': 'thieves_guild', 'imperial_legion': 'imperial_legion',
    'imperial_cult': 'imperial_cult', 'temple': 'temple',
    'morag_tong': 'morag_tong',
    'east_empire_company': 'east_empire_company',
    'misc': 'misc',
}

ITEM_TYPES = {'book', 'miscitem', 'misc', 'weapon', 'armor', 'clothing', 'apparatus',
              'lockpick', 'probe', 'repair', 'repairitem', 'light', 'alchemy', 'ingredient'}
CONSUMABLE_TYPES = {'alchemy', 'ingredient', 'light'}

ITEMS_BASE, ITEMS_LIMIT = 7702000, 7705000

AMBIENT_ITEMS = {
    'common_glove_l', 'common_glove_r',
    'common_glove_l_balmolagmer', 'common_glove_r_balmolagmer',
    'common_shirt_01', 'common_shirt_02', 'common_shirt_03', 'common_shirt_04',
    'common_pants_01', 'common_pants_02',
    'common_shoes_01', 'common_shoes_02',
    'common_ring_01', 'common_ring_02', 'common_amulet_01', 'common_belt_01',
    'gold_001', 'gold_005', 'gold_010', 'gold_025', 'gold_100',
    'misc_lw_bowl', 'misc_lw_cup', 'misc_lw_platter',
    'misc_de_goblet_01', 'misc_de_bowl_orange_green_01',
    'misc_de_drum_02', 'misc_de_plate_01',
    'misc_soulgem_petty', 'misc_soulgem_lesser', 'misc_soulgem_common',
    'misc_soulgem_greater', 'misc_soulgem_grand',
    'sc_divineintervention', 'sc_almsiviintervention',
    'sc_invisibility', 'sc_teleportation', 'sc_recall',
    'potion_of_cure_common_disease', 'potion_of_cure_blight_disease',
    'potion_of_cure_poison', 'potion_of_cure_paralysis',
    'ingred_diamond_01', 'ingred_ruby_01', 'ingred_emerald_01',
    'ingred_bread_01', 'food_kwama_egg_02', 'food_kwama_egg_01',
    'ingred_horn_lily_bulb_01', 'ingred_gold_kanet_01',
    'fur_colovian_helm',
    'bk_abcs',
    'exquisite_shirt_01', 'exquisite_shirt_02', 'exquisite_shirt_03',
    'exquisite_pants_01', 'exquisite_pants_02',
    'exquisite_skirt_01', 'exquisite_skirt_02',
    'exquisite_shoes_01', 'exquisite_shoes_02',
    'exquisite_robe_01', 'exquisite_robe_02',
    'exquisite_amulet_01', 'exquisite_amulet_02',
    'exquisite_ring_01', 'exquisite_ring_02',
    'exquisite_belt_01',
    *[f'misc_dwrv_artifact{i:02d}' for i in range(10, 100)],
    'exclusive_fortify_luck', 'exclusive_restore_health',
    'exclusive_restore_fatigue', 'exclusive_restore_magicka',
    'exclusive_fortify_personality', 'exclusive_fortify_intelligence',
    'exclusive_fortify_attack', 'exclusive_fortify_magicka',
    'exclusive_invisibility', 'exclusive_potion_of_shadow',
    'exclusive_potion_of_feather', 'exclusive_rising_force_potion',
    'quality_restore_health', 'quality_restore_fatigue',
    'quality_restore_magicka', 'quality_restore_strength',
    'quality_fortify_health', 'quality_fortify_endurance',
    'quality_fortify_personality', 'quality_fortify_intelligence',
    'quality_fortify_strength', 'quality_fortify_attack',
    'quality_fortify_willpower', 'quality_lightning_shield',
    'quality_fire_resistance', 'quality_frost_resistance',
    'quality_magicka_resistance', 'quality_paralysis_resistance',
    'standard_restore_health_potion', 'standard_restore_fatigue',
    'standard_restore_magicka_potion', 'standard_fortify_endurance',
    'standard_fortify_health_potion', 'standard_fortify_speed',
    'standard_potion_of_invisibility', 'standard_potion_of_night_eye',
    'bargain_fortify_personality', 'cheap_restore_health',
    'cheap_restore_magicka', 'cheap_restore_fatigue',
    'distilled_fortify_intelligence',
    'potion_of_slowfalling', 'potion_of_telekinesis',
    'potion_of_water_breathing', 'potion_of_seven_wonders',
    'potion_of_sweet_little_lies', 'potion_of_open_mind',
    'misc_dwrv_ark_key00', 'dwemer_boots'
}

AMBIENT_PREFIXES = (
    'common_', 'misc_soulgem_', 'ingred_', 'food_', 'sc_',
    'potion_of_', 'bookskill_', 'exclusive_', 'quality_',
    'standard_', 'bargain_', 'cheap_', 'distilled_', 'p_',
)

TR_AMBIENT_PREFIXES = (
    't_bk_', 't_de_', 't_imp_', 't_com_', 't_ing_', 't_ingmine_', 't_sc_', 't_ensc_',
    't_dae_', 't_bre_', 't_nor_', 't_rga_', 't_arg_', 't_kha_', 't_we_',
    't_ag_', 't_miss_', 't_lore_',
)
TR_UNIQUE_MARKERS = ('_unique', '_uni', 'uni_', '_unic', '_reward')


def is_tr_ambient(item_id):
    low = item_id.lower()
    if not any(low.startswith(p) for p in TR_AMBIENT_PREFIXES):
        return False
    if any(marker in low for marker in TR_UNIQUE_MARKERS):
        return False
    return True


def is_ambient(item_id):
    low = item_id.lower()
    if low in AMBIENT_ITEMS:
        return True
    if any(low.startswith(p) for p in AMBIENT_PREFIXES):
        return True
    if is_tr_ambient(item_id):
        return True
    return False


FACTION_GLOBAL_ITEMS = {
    'bk_bm_stockcert',
    'bk_colonyreport', 'bk_colony_toralf', 'bk_carniusnote',
    *[f'writ_{x}' for x in (
        'alen', 'baladas', 'belvayn', 'bemis', 'berano', 'bero', 'brilnosu',
        'dils', 'galasa', 'guril', 'hloggar', 'mavon', 'navil', 'oran',
        'sadus', 'saren', 'therana', 'varro', 'vendu', 'yasalmibaal',
    )],
    'common_glove_l_balmolagmer', 'common_glove_r_balmolagmer',
    *[f'sanguine{kind}{name}w' for kind in ('ring', 'amulet', 'belt', 'glove')
      for name in (
          'red', 'green', 'denial', 'golden', 'hewing', 'silver', 'unseen',
          'leaping', 'smiting', 'impaling', 'stalking', 'hornyfist',
          'deepbiting', 'glibspeech', 'sureflight', 'swiftblade',
          'nimblearmor', 'safekeeping', 'stolidarmor', 'fluidevasion',
          'martialcraft', 'transcendent', 'balancedarmor', 'transfigur',
      )],
    'slave_bracer_left', 'slave_bracer_right',
    't_glb_var_headfixer',
    't_bk_stockcerteec_nar',
}


def is_faction_global(item_id):
    return item_id.lower() in {x.lower() for x in FACTION_GLOBAL_ITEMS}


GLOBAL_ITEM_THRESHOLD = 5
TR_GLOBAL_ITEM_THRESHOLD = 1

QUEST_ITEMS_BY_GOAL = {
    'main_quest': {
        'bk_a1_1_caiuspackage', 'misc_dwrv_ark_cube00', 'misc_skull_llevule',
        'bk_thelostprophecy', 'wraithguard', 'keening', 'sunder',
        'bk_a1_2_antabolistocosades', 'bk_a1_4_sharnsnotes', 'bk_a1_7_huleeyainformant',
        'bk_a1_11_zainsubaninotes', 'bk_a1_v_vivecinformants', 'bk_progressoftruth',
    },
    'hlaalu': {
        'bk_ordersfromneminda', 'bk_nemindasorders', 'bk_alchemicalformulas',
        'bk_auranefrernis1', 'bk_auranefrernis2', 'bk_auranefrernis3',
        'bk_hh_sealedorders', 'bk_treasuryorders', 'bk_treasuryreport',
        'bk_hh_reallanddeed', 'bk_landdeed_hhrd',
        'bk_hh_erroneouslanddeed', 'bk_landdeedfake_hhrd',
        'bk_rethanmanordeed', 'bk_stronghold_ld_hlaalu',
        'bk_calderaminingcontract', 'bk_stronghold_c_hlaalu',
        'key_orvas_dren',
    },
    'redoran': {
        'bk_shishireport', 'bk_calderarecordbook2',
        'misc_6th_ash_statue_01', 'misc_6th_ash_hrcs', 'misc_6th_ash_hrmm',
    },
    'telvanni': {
        'bk_secrets_of_dwemer_animunculi', 'bk_secretsdwemeranimunculi',
        'bk_antecedantsdwemerlaw',
        'bk_nchunaksfireandfaith', 'bk_responsefromdivaythfyr',
        'ring_equity_uniq',
        'bk_stronghold_c_telvanni', 'bk_stronghold_ld_telvanni',
        'ring_dahrkmezalf', 'ring_dahrkmezalf_uniq', 'ring_blackjinx_uniq',
    },
    'thieves_guild': {
        'key_balmora_nerano', 'key_neranomanor',
        'apparatus_g_retort_01', 'bk_withershins',
        'misc_bittercup', 'artifact_bittercup_01', 'bk_ynglingledger',
        'bk_indreledeed', 'bk_redorancookingsecrets',
    },
    'fighters_guild': {
        'bk_codebook', 'bk_sottildescodebook', 'misc_dwrv_goblet00',
        'misc_dwrv_artifact50', 'misc_uniq_egg_of_gold',
    },
    'mages_guild': {
        'misc_soulgem_grand_fake', 'misc_fakesoulgem',
        'staff_magnus', 'staff_magnus_unique',
        'ring_warlock_unique', "ebony wizard's staff", 'ebony_staff_trebonius',
    },
    'imperial_cult': {
        'boots_apostle_unique', 'ring_wind_unique', 'cuirass_lord',
        'lords_cuirass_unique', 'claymore_chrysamere', 'claymore_chrysamere_unique',
        'claymore_iceblade_unique', 'warhammer_crusher_unique',
    },
    'imperial_legion': {
        'bk_widowdeed', 'bk_talostreason',
        'key_arvs-drelen_cell', 'key_oritius', 'misc_dwrv_artifact_ils',
        'expensive_glove_left_ilmeni',
    },
    'temple': {
        'staff_llothis_unique', 'crosierstllothis',
        'cleaverstfelms', 'ebon_plate_cuirass_unique',
        'expensive_shirt_hair', 'extravagant_rt_art_wild', 'bk_saryonissermons',
    },
    'morag_tong': set(),
    'daedric_quests': set(),
    'misc': {
        'amulet of ashamanu (unique)',
        'amulet_agustas_unique',
        'apparatus_a_spipe_tsiya',
        'bk_aedra_tarer_unique',
        'bk_notefrombashuk',
        'bk_notefrombugrol',
        'bk_notefromernil',
        'bk_notefromnelos',
        'bk_seydaneentaxrecord',
        'cloudcleaver_unique',
        'common_pants_02_hentus',
        'expensive_amulet_aeta',
        'expensive_ring_aeta',
        'exquisite_ring_processus',
        'extravagant_glove_left_maur',
        'icecap_unique',
        'key_arenim',
        'misc_beluelle_silver_bowl',
        'nuccius_ring',
        'widowmaker_unique',
    },
    'east_empire_company': set(),
    'tamriel_rebuilt': set(),
}

QUEST_ITEM_ALIASES = {
    'bk_codebook', 'bk_alchemicalformulas', 'bk_ordersfromneminda',
    'bk_hh_sealedorders', 'bk_hh_reallanddeed', 'bk_hh_erroneouslanddeed',
    'bk_rethanmanordeed', 'claymore_chrysamere', 'cuirass_lord',
    'misc_token_maiden', 'misc_soulgem_grand_fake', 'staff_magnus',
    'staff_llothis_unique', 'bk_withershins', 'key_balmora_nerano',
    'misc_bittercup', 'ring_dahrkmezalf',
    'bk_secrets_of_dwemer_animunculi', 'ring_equity_unique',
    'bk_stronghold_c_redoran', 'bk_stronghold_ld_redoran',
    'bk_stronghold_c_telvanni', 'bk_stronghold_ld_telvanni',
    'bk_orvasdrenjournal', 'sc_gaveloflilmoth', 'bk_triplicate_form',
    'bk_bethamez_plans', 'bk_bethamezplans', 'bk_telvannisecretdocuments',
    'misc_dwrv_ark_tube00', 'ring_fire_unique', 'belt of northern knighthood',
    'bk_indarysmanordeed', 'bk_savortrandelmap', 'bk_teluvarithdeed',
    'shoes_st_rilm_unique',
    'gavel of the ordinator', 'misc_dwrv_gear00',
    'ring_keley',
}

QUEST_ITEM_PATTERNS_BY_GOAL = {
    None: [
        re.compile(r'^bk_.*deed.*', re.I),
        re.compile(r'^bk_.*contract.*', re.I),
        re.compile(r'^bk_.*note.*', re.I),
        re.compile(r'^bk_.*writ.*', re.I),
        re.compile(r'^bk_.*report.*', re.I),
        re.compile(r'.*stronghold.*', re.I),
    ],
    'morag_tong': [],
    'thieves_guild': [],
    'main_quest': [
        re.compile(r'^misc_dwrv_.*', re.I),
    ],
    'temple': [
        re.compile(r'^ring_sanguine_.*', re.I),
        re.compile(r'^belt_sanguine_.*', re.I),
    ],
    'tamriel_rebuilt': [
        re.compile(r'^tr_m\d+_[a-z0-9]+_q_\w*reward\w*$', re.I),
        re.compile(r'^tr_m\d+_q_\w+$', re.I),
        re.compile(r'^tr_m\d+_[a-z]+_q\w*$', re.I),
    ],
}


def is_whitelisted(goal, item_id, item_name):
    item_id_low = item_id.lower()
    item_name_low = (item_name or '').lower()
    explicit = QUEST_ITEMS_BY_GOAL.get(goal, set())
    if item_id_low in explicit or (item_name_low and item_name_low in explicit):
        return True
    for g, pats in [(None, QUEST_ITEM_PATTERNS_BY_GOAL[None]),
                    (goal, QUEST_ITEM_PATTERNS_BY_GOAL.get(goal, []))]:
        for pat in pats:
            if pat.match(item_id_low) or (item_name and pat.match(item_name)):
                return True
    return False


def origin_of_file(path):
    name = pathlib.Path(path).name.lower()
    if 'tribunal' in name:
        return 'tribunal'
    if 'bloodmoon' in name:
        return 'bloodmoon'
    if 'tr_mainland' in name or 'tamriel_rebuilt' in name:
        return 'tamriel_rebuilt'
    if 'tamriel_data' in name:
        return 'tamriel_data'
    return 'morrowind'


def load(paths):
    for p in paths:
        with open(p, encoding='utf-8') as f:
            for r in json.load(f):
                yield r


def journal_quests(text):
    out = set()
    for pat in (PAT_JOURNAL_Q, PAT_JOURNAL_B):
        for m in pat.finditer(text or ''):
            out.add(m.group(1).strip().lower())
    return out


def _records_field(info, *keys):
    out = []
    for k in keys:
        v = info.get(k)
        if v is None:
            continue
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except (ValueError, TypeError):
                continue
        if isinstance(v, list):
            out.extend(v)
    return out


def filter_items(info):
    out = []
    for f in _records_field(info, 'filters', 'conditions'):
        if isinstance(f, dict):
            fn = str(f.get('function', f.get('type', ''))).lower()
            if 'item' in fn and f.get('id'):
                out.append(str(f['id']).lower())
        elif isinstance(f, (list, tuple)) and len(f) >= 2:
            if 'item' in str(f[0]).lower():
                out.append(str(f[1]).lower())
    return out


def filter_journals(info):
    out = set()
    for f in _records_field(info, 'filters', 'conditions'):
        if isinstance(f, dict):
            ft = str(f.get('filter_type', f.get('type', ''))).lower()
            fn = str(f.get('function', '')).lower()
            if ('journal' in ft or 'journal' in fn) and f.get('id'):
                out.add(str(f['id']).lower())
    return out


def scan(paths, overrides, include_consumables, strict_mode=True):
    # item_rec stores (type, name, canonical_id) so the YAML keeps the
    # exact case used by the ESM engine ('TR_m2_q_18_Potion', not lowercased).
    item_rec = {}
    journal_origin = {}
    # case-insensitive lookup: {lower_id: canonical_id}
    canonical_by_lower = {}

    for path in paths:
        origin = origin_of_file(path)
        with open(path, encoding='utf-8') as f:
            for r in json.load(f):
                t = str(r.get('type', '')).lower()
                if t in ITEM_TYPES and r.get('id'):
                    rid = str(r['id'])
                    key = rid.lower()
                    if key not in item_rec:
                        item_rec[key] = (t, r.get('name') or rid, rid)
                        canonical_by_lower[key] = rid
                elif t == 'dialogue' and str(r.get('dialogue_type', '')).lower() == 'journal':
                    journal_origin.setdefault(str(r.get('id', '')).lower(), origin)

    def canonical(item_lower):
        return canonical_by_lower.get(item_lower, item_lower)

    def goal_of(qid):
        origin = journal_origin.get(qid)
        if origin in ('tamriel_rebuilt', 'tamriel_data'):
            return 'tamriel_rebuilt'
        if origin == 'tribunal':
            return None
        return GOAL_OF_GROUP.get(classify(qid, overrides))

    found = collections.defaultdict(lambda: {'sources': set(), 'via': set(), 'count': 1})

    def add(goal, item, quest, via, count=1):
        if not goal or not item or item.startswith('gold_'):
            return
        # item is already lowercased by the caller; resolve to canonical
        rec = item_rec.get(item)
        if item_rec and rec is None:
            return
        if rec and rec[0] in CONSUMABLE_TYPES and not include_consumables:
            if not (strict_mode and is_whitelisted(goal, item, rec[1])):
                return
        if is_ambient(item):
            return
        if is_faction_global(item):
            return
        if strict_mode and via == 'AddItem':
            item_name = rec[1] if rec else ""
            if not is_whitelisted(goal, item, item_name):
                return
        # store the canonical ID as the key so the YAML keeps the ESM case.
        canonical_item = canonical(item)
        e = found[(goal, canonical_item)]
        e['sources'].add(quest)
        e['via'].add(via)
        e['count'] = max(e['count'], count)

    for path in paths:
        with open(path, encoding='utf-8') as f:
            for r in json.load(f):
                t = str(r.get('type', ''))
                if t == 'DialogueInfo':
                    text = r.get('script_text') or ''
                    qs = journal_quests(text) | filter_journals(r)
                    for q in qs:
                        goal = goal_of(q)
                        if not goal:
                            continue
                        for m in PAT_REMOVE.finditer(text):
                            add(goal, m.group(1).lower(), q,
                                'RemoveItem (Quest)', int(m.group(2) or 1))
                        for it in filter_items(r):
                            add(goal, it, q, 'required (Item filter)')
                        for m in PAT_COUNT.finditer(text):
                            add(goal, m.group(1).lower(), q, 'GetItemCount')
                        for m in PAT_ADD.finditer(text):
                            add(goal, m.group(1).lower(), q, 'AddItem',
                                int(m.group(2) or 1))
                elif t == 'Script':
                    text = r.get('script_text') or r.get('text') or ''
                    for q in journal_quests(text):
                        goal = goal_of(q)
                        if not goal:
                            continue
                        for m in PAT_REMOVE.finditer(text):
                            add(goal, m.group(1).lower(), q,
                                'RemoveItem (Quest)', int(m.group(2) or 1))
                        for m in PAT_COUNT.finditer(text):
                            add(goal, m.group(1).lower(), q, 'GetItemCount')
                        for m in PAT_ADD.finditer(text):
                            add(goal, m.group(1).lower(), q, 'AddItem',
                                int(m.group(2) or 1))

    by_goal_quests = collections.defaultdict(lambda: collections.defaultdict(set))
    for (goal, item), e in found.items():
        by_goal_quests[goal][item] = e['sources']

    removed_global = []
    for goal, items in by_goal_quests.items():
        threshold = (TR_GLOBAL_ITEM_THRESHOLD if goal == 'tamriel_rebuilt'
                     else GLOBAL_ITEM_THRESHOLD)
        for item, quests in items.items():
            if len(quests) > threshold:
                removed_global.append((goal, item, len(quests)))
                found.pop((goal, item), None)

    if removed_global:
        print(f'dropped {len(removed_global)} items that appear in too many '
              f'quests of the same faction:', file=sys.stderr)
        for goal, item, n in sorted(removed_global, key=lambda x: -x[2])[:20]:
            print(f'  {goal:18} {item:40} x{n}', file=sys.stderr)

    return found, item_rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('esm_json', nargs='+')
    ap.add_argument('--data', default='data')
    ap.add_argument('--apply', action='store_true',
                    help='adds the candidates to quest_items.yaml')
    ap.add_argument('--include-consumables', action='store_true')
    ap.add_argument('--no-strict', action='store_true')
    ap.add_argument('--goal', action='append')
    args = ap.parse_args()
    data = pathlib.Path(args.data)

    overrides = load_overrides(data / 'quest_groups_override.yaml')
    found, item_rec = scan(args.esm_json, overrides,
                            args.include_consumables,
                            strict_mode=not args.no_strict)

    qi_path = data / 'quest_items.yaml'
    existing = yaml.safe_load(qi_path.read_text(encoding='utf-8')) if qi_path.exists() else []
    existing = existing or []
    known_names = {e['name'].lower() for e in existing}
    known_records = set()
    for e in existing:
        known_records |= {str(x).lower() for x in e.get('suppress', [])}
        if e.get('give'):
            known_records.add(str(e['give'][0]).lower())
    next_id = max([ITEMS_BASE] + [e['id'] for e in existing
                                    if ITEMS_BASE <= e['id'] < ITEMS_LIMIT])

    # option 2: drop items whose only evidence is a GetItemCount test.
    n_dropped_getitemcount = 0
    real_found = {}
    for key, e in found.items():
        via = set(e['via'])
        if not (via - {'GetItemCount'}):
            n_dropped_getitemcount += 1
            continue
        real_found[key] = e
    found = real_found

    if n_dropped_getitemcount:
        print(f'dropped {n_dropped_getitemcount} items whose only evidence '
              f'is a GetItemCount (false progression positives):',
              file=sys.stderr)

    cands = []
    for (goal, item), e in sorted(found.items()):
        if args.goal and goal not in set(args.goal):
            continue
        if item.lower() in known_records:
            continue
        if item.lower() in QUEST_ITEM_ALIASES:
            continue
        name = item_rec.get(item.lower(), ('', item, item))[1]
        cands.append({'goal': goal, 'record': item, 'name': name, 'count': e['count'],
                      'via': sorted(e['via']),
                      'quests': sorted(e['sources'])})

    rep = data / 'quest_items_candidates.yaml'
    rep.write_text('# Candidates generated by tools/gen_quest_items.py\n' +
                   yaml.safe_dump(cands, sort_keys=False, allow_unicode=True),
                   encoding='utf-8')
    per_goal = collections.Counter(c['goal'] for c in cands)
    print(f'{len(cands)} valid candidates -> {rep}')
    for g, n in sorted(per_goal.items()):
        print(f'  {g:18} {n}')

    matched = {item.lower() for (_goal, item) in found}
    audit_path = data / 'quest_items_whitelist_audit.txt'
    cands_records = {c['record'].lower() for c in cands}
    lines = []
    for goal in sorted(QUEST_ITEMS_BY_GOAL):
        for wid in sorted(QUEST_ITEMS_BY_GOAL[goal]):
            w = wid.lower()
            if w in matched or w in QUEST_ITEM_ALIASES or w in known_records \
                    or w in cands_records:
                continue
            if is_ambient(w) or is_faction_global(w):
                continue
            if item_rec and w not in item_rec:
                words = [x for x in re.split(r'[_\s]+', w) if len(x) > 3]
                sugg = []
                for rid, (rt, rname, _canon) in item_rec.items():
                    n = rname.lower()
                    if words and all(xd in n for xd in words):
                        sugg.append(f'{rid} ({rname})')
                    if len(sugg) >= 5:
                        break
                lines.append(f'{goal:16} {wid:40} ABSENT from the ESM'
                             + (f'; candidates by name: {", ".join(sugg)}' if sugg else '; no suggestion'))
            else:
                lines.append(f'{goal:16} {wid:40} present in the ESM but not generated')
    if lines:
        audit_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(f'WARNING: {len(lines)} whitelist entries without a candidate -> {audit_path}')

    if args.apply and cands:
        record_to_id = {}
        for e in existing:
            for r in e.get('suppress', []) or []:
                record_to_id[str(r).lower()] = e['id']
            if e.get('give'):
                record_to_id[str(e['give'][0]).lower()] = e['id']

        lines = []
        for c in cands:
            name = c['name']
            rec = c['record']
            rec_low = rec.lower()
            if rec_low in record_to_id:
                item_id = record_to_id[rec_low]
            else:
                next_id += 1
                if next_id >= ITEMS_LIMIT:
                    raise SystemExit(
                        f'item ID range exhausted (max {ITEMS_LIMIT - ITEMS_BASE} '
                        f'slots, got {len(cands)} candidates). '
                        f'Either widen the range or tighten the filters '
                        f'(TR_AMBIENT_PREFIXES / TR_GLOBAL_ITEM_THRESHOLD).')
                item_id = next_id
                record_to_id[rec_low] = item_id
            if name.lower() in known_names:
                name = f"{name} ({c['goal']})"
            known_names.add(name.lower())
            lines.append(
                '- {name: %s, id: %d, goal: %s, give: [%s, %d], suppress: [%s], via: [%s]}' % (
                    json.dumps(name, ensure_ascii=False), item_id, c['goal'],
                    json.dumps(rec), c['count'], json.dumps(rec),
                    json.dumps(c['via'])))
        with open(qi_path, 'a', encoding='utf-8') as f:
            f.write('\n# --- added by tools/gen_quest_items.py --apply ---\n'
                    + '\n'.join(lines) + '\n')
        print(f'{len(cands)} entries added to {qi_path}')


if __name__ == '__main__':
    main()
