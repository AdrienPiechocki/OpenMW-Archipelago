#!/usr/bin/env python3
"""Quest item candidates per goal, extracted from the ESM with filtering / Whitelist.

Only items NEEDED FOR PROGRESSION are kept, faction by faction:
  - RemoveItem   : item handed over to validate a step (quest turn-in);
  - Item filter  : item required in the inventory by the dialogue;
  - GetItemCount : item counted to validate a condition;
  - AddItem      : item given to the player DURING the quest, only if it is
                   validated by its faction's whitelist (otherwise it is a
                   reward, not a progression item).

Usage:
  python tools/gen_quest_items.py morrowind.json [bloodmoon.json] [--apply]
  (bloodmoon.json: required for the East Empire Company items; tribunal.json: not needed,
  no Tribunal goal has quest items)
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
from script_effects import parse_script, is_quest_item, _resolve_journal  # noqa: E402

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
    'imperial_cult': 'imperial_cult', 'temple': 'temple', 'morag_tong': 'morag_tong',
    'east_empire_company': 'east_empire_company',   # Bloodmoon: needs bloodmoon.json
    'misc': 'misc',
}

ITEM_TYPES = {'book', 'miscitem', 'misc', 'weapon', 'armor', 'clothing', 'apparatus',
              'lockpick', 'probe', 'repair', 'repairitem', 'light', 'alchemy', 'ingredient'}
CONSUMABLE_TYPES = {'alchemy', 'ingredient', 'light'}
ITEMS_BASE, ITEMS_LIMIT = 7702000, 7703000

# ==============================================================================
# WHITELIST PER FACTION - only PROGRESSION items
# ==============================================================================
# Keys = goal (faction). An AddItem item is only kept if the whitelist of the
# corresponding goal contains it: this guarantees that the item helps progress
# (documents to hand over, keys, evidence...) and is not a simple reward.
QUEST_ITEMS_BY_GOAL = {
    'main_quest': {
        'bk_a1_1_caiuspackage', 'misc_dwrv_ark_cube00', 'misc_skull_llevule',
        'bk_thelostprophecy', 'wraithguard', 'keening', 'sunder',
        'bk_a1_2_antabolistocosades', 'bk_a1_4_sharnsnotes', 'bk_a1_7_huleeyainformant',
        'bk_a1_11_zainsubaninotes', 'bk_a1_v_vivecinformants', 'bk_progressoftruth',
        'misc_dwrv_ark_key00',
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
        'ingred_diamond_01', 'key_balmora_nerano', 'key_neranomanor', 'pick_master',
        'apparatus_g_retort_01', 'bk_withershins', 'bookskill_restoration1',
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
        'ring_warlock_unique', 'ebony wizard\'s staff', 'ebony_staff_trebonius',
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
}

# Shared patterns: match on the item ID or name. They only apply to AddItem
# and capture whole families of quest items.
# ==============================================================================
# ALIAS - obsolete IDs kept for compatibility, but ignored by the audit.
# The real counterpart (present in the ESM) is in QUEST_ITEMS_BY_GOAL.
# ==============================================================================
QUEST_ITEM_ALIASES = {
    # Obsolete IDs whose real counterpart (in the ESM) is known
    'bk_codebook', 'bk_alchemicalformulas', 'bk_ordersfromneminda',
    'bk_hh_sealedorders', 'bk_hh_reallanddeed', 'bk_hh_erroneouslanddeed',
    'bk_rethanmanordeed', 'claymore_chrysamere', 'cuirass_lord',
    'misc_token_maiden', 'misc_soulgem_grand_fake', 'staff_magnus',
    'staff_llothis_unique', 'bk_withershins', 'key_balmora_nerano',
    'misc_bittercup', 'ring_dahrkmezalf',
    'bk_secrets_of_dwemer_animunculi', 'ring_equity_unique',
    'bk_stronghold_c_redoran', 'bk_stronghold_ld_redoran',
    'bk_stronghold_c_telvanni', 'bk_stronghold_ld_telvanni',
    # IDs absent from the vanilla ESM (verified by grep): retry if
    # tribunal.json / bloodmoon.json are passed as input
    'bk_orvasdrenjournal', 'sc_gaveloflilmoth', 'bk_triplicate_form',
    'bk_bethamez_plans', 'bk_bethamezplans', 'bk_telvannisecretdocuments',
    'misc_dwrv_ark_tube00', 'ring_fire_unique', 'belt of northern knighthood',
    'bk_indarysmanordeed', 'bk_savortrandelmap', 'bk_teluvarithdeed',
    'shoes_st_rilm_unique',
    # WORLD items not required by dialogue/script (physical access, placement):
    # the scan cannot generate them. If the mod must randomize them, add them
    # by hand in quest_items.yaml (like Corprus Cure).
    'gavel of the ordinator', 'misc_dwrv_gear00',
    'ring_keley',  # needed for the tutorial (Fargoth's ring), do not randomize
}

QUEST_ITEM_PATTERNS_BY_GOAL = {
    None: [  # applied to all goals
        re.compile(r'^bk_.*deed.*', re.I),
        re.compile(r'^bk_.*contract.*', re.I),
        re.compile(r'^bk_.*note.*', re.I),
        re.compile(r'^bk_.*writ.*', re.I),
        re.compile(r'^bk_.*report.*', re.I),
    ],
    'morag_tong': [  # execution writs
        re.compile(r'^bk_.*writ.*', re.I),
    ],
    'thieves_guild': [
        re.compile(r'^ingred_diamond_.*', re.I),
    ],
    'hlaalu': [re.compile(r'.*stronghold.*', re.I)],
    'redoran': [re.compile(r'.*stronghold.*', re.I)],
    'telvanni': [re.compile(r'.*stronghold.*', re.I)],
    'temple': [
        re.compile(r'^ring_sanguine_.*', re.I),
        re.compile(r'^belt_sanguine_.*', re.I),
    ],
}


def is_whitelisted(goal, item_id, item_name):
    """True if the item is a known progression item for THIS goal.

    Matches on the record ID OR on the item's display name (some whitelist
    entries are names, e.g. 'belt of northern knighthood', or IDs with
    spaces, e.g. 'ebony wizard's staff').
    """
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


# ==============================================================================


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
    """Gets a field that may be a list, or a list encoded as a JSON
    string (like 'inventory'/'references' in the ESM export)."""
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
    # 'filters' and 'conditions': one or the other depending on the ESM export tool
    for f in _records_field(info, 'filters', 'conditions'):
        if isinstance(f, dict):
            fn = str(f.get('function', f.get('type', ''))).lower()
            if 'item' in fn and f.get('id'):
                out.append(str(f['id']).lower())
        elif isinstance(f, (list, tuple)) and len(f) >= 2:
            # flat form [function, id, ...]
            if 'item' in str(f[0]).lower():
                out.append(str(f[1]).lower())
    return out


def filter_journals(info):
    """Journal IDs required by the dialogue filters (JournalType, etc.).
    Some DialogueInfo records have an empty script_text: the quest is not set
    there by a Journal command, but by a filter condition."""
    out = set()
    for f in _records_field(info, 'filters', 'conditions'):
        if isinstance(f, dict):
            ft = str(f.get('filter_type', f.get('type', ''))).lower()
            fn = str(f.get('function', '')).lower()
            if ('journal' in ft or 'journal' in fn) and f.get('id'):
                out.add(str(f['id']).lower())
    return out


MAX_PLACEMENTS = 3   # a non-whitelisted record placed more often than this is stock, not a quest item


def count_placements(records):
    """record id -> number of placements in cells (references) + NPC / container inventories.
    A quest item is placed once or twice; `steel shortsword` or `sc_divineintervention`
    are everywhere. Suppressing such a record would remove EVERY copy in the world."""
    n = collections.Counter()
    for r in records:
        for ref in _records_field(r, 'references'):
            rid = ref.get('id') if isinstance(ref, dict) else None
            if rid:
                n[str(rid).lower()] += 1
        for e in _records_field(r, 'inventory'):
            if isinstance(e, (list, tuple)) and len(e) >= 2:
                n[str(e[1]).lower()] += 1
            elif isinstance(e, dict) and e.get('id'):
                n[str(e['id']).lower()] += 1
    return n


def scan(paths, overrides, include_consumables, strict_mode=True, max_placements=MAX_PLACEMENTS):
    records = list(load(paths))
    placements = count_placements(records)
    item_rec = {}
    journal_ids = set()
    for r in records:
        t = str(r.get('type', '')).lower()
        if t in ITEM_TYPES and r.get('id'):
            item_rec[str(r['id']).lower()] = (t, r.get('name') or r['id'])
        elif t == 'dialogue' and str(r.get('dialogue_type', '')).lower() == 'journal':
            journal_ids.add(str(r.get('id', '')).lower())

    found = collections.defaultdict(lambda: {'sources': set(), 'via': set(), 'count': 1})

    def add(goal, item, quest, via, count=1):
        if not item or item.startswith('gold_'):
            return
        rec = item_rec.get(item)
        if item_rec and rec is None:
            return
        if rec and rec[0] in CONSUMABLE_TYPES and not include_consumables:
            # A consumable whitelisted for THIS goal remains a progression
            # item (e.g. ingred_diamond_01 for tg_diamonds).
            if not (strict_mode and is_whitelisted(goal, item, rec[1])):
                return

        # Strict mode: an AddItem is only kept if it is whitelisted for this
        # faction (progression item).
        item_name = rec[1] if rec else ""
        wl = is_whitelisted(goal, item, item_name)
        if strict_mode and via == 'AddItem' and not wl:
            return
        # Items REQUIRED by a quest (RemoveItem / Item filter / GetItemCount) used to pass
        # unfiltered. Generic stock (sc_*, ingred_*, misc_de_*, ...) or a record placed all
        # over the world is not a progression item: any copy would do, and suppressing the
        # record would delete every one of them.
        if via != 'AddItem' and not wl:
            if not is_quest_item(item):
                return
            if placements.get(item, 0) > max_placements:
                return

        e = found[(goal, item)]
        e['sources'].add(quest)
        e['via'].add(via)
        e['count'] = max(e['count'], count)

    # --- script effects, attributed to the journal changed in the SAME if/elseif/else block
    known_up = {j.upper() for j in journal_ids}
    sorted_known = sorted(known_up, key=len, reverse=True)

    def journal_of(j):
        if not j:
            return None
        res = _resolve_journal(j.upper(), known_up, {}, sorted_known)
        return res.lower() if res else None

    def add_effects(effects, fallback_journals, quest_extra=()):
        for kind, item, qty, j in effects:
            item = item.lower()
            js = {journal_of(j)} if j else {journal_of(x) for x in fallback_journals}
            for q in js - {None}:
                goal = GOAL_OF_GROUP.get(classify(q, overrides))
                if not goal:
                    continue
                if kind == 'needed':
                    add(goal, item, q, 'needed (Player->RemoveItem/GetItemCount)', qty)
                else:
                    add(goal, item, q, 'AddItem', qty)

    for r in records:
        t = str(r.get('type', ''))
        if t == 'DialogueInfo':
            text = r.get('script_text') or ''
            fj = filter_journals(r)
            add_effects(parse_script('info:' + str(r.get('id', '')), text), fj)
            # items required by the dialogue filter itself (Item filter) count for the
            # journals the info sets (Journal command) or filters on
            qs = {journal_of(q) for q in journal_quests(text) | fj} - {None}
            for q in qs:
                goal = GOAL_OF_GROUP.get(classify(q, overrides))
                if goal:
                    for it in filter_items(r):
                        add(goal, it, q, 'required (Item filter)')
        elif t == 'Script':
            add_effects(parse_script(str(r.get('id', '')), r.get('script_text') or r.get('text') or ''), ())

    return found, item_rec, records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('esm_json', nargs='+')
    ap.add_argument('--data', default='data')
    ap.add_argument('--apply', action='store_true', help='adds the candidates to quest_items.yaml')
    ap.add_argument('--include-consumables', action='store_true')
    ap.add_argument('--max-placements', type=int, default=MAX_PLACEMENTS,
                    help='a non-whitelisted required item placed more often than this is stock (default %(default)s)')
    ap.add_argument('--prune', action='store_true',
                    help='lists (with --apply: removes) entries of quest_items.yaml that are generic stock')
    ap.add_argument('--no-strict', action='store_true', help='Disables Whitelist/RemoveItem filtering')
    ap.add_argument('--goal', action='append',
                    help='limits generation to these goals (repeat the option), e.g. --goal hlaalu')
    args = ap.parse_args()
    data = pathlib.Path(args.data)

    overrides = load_overrides(data / 'quest_groups_override.yaml')
    found, item_rec, records = scan(args.esm_json, overrides, args.include_consumables, strict_mode=not args.no_strict,
                                       max_placements=args.max_placements)

    qi_path = data / 'quest_items.yaml'
    existing = yaml.safe_load(qi_path.read_text(encoding='utf-8')) if qi_path.exists() else []
    existing = existing or []
    known_names = {e['name'].lower() for e in existing}
    known_records = set()
    for e in existing:
        known_records |= {str(x).lower() for x in e.get('suppress', [])}
        if e.get('give'):
            known_records.add(str(e['give'][0]).lower())
    if args.prune:
        placements = count_placements(records)
        flagged = []
        for e in existing:
            if not e.get('give'):
                continue
            rec = str(e['give'][0]).lower()
            name = item_rec.get(rec, ('', e['name']))[1]
            if is_whitelisted(e.get('goal'), rec, name) or rec in QUEST_ITEM_ALIASES:
                continue
            why = None
            if item_rec and rec not in item_rec:
                why = 'absent from the ESM'
            elif not is_quest_item(rec):
                why = 'generic stock (prefix)'
            elif placements.get(rec, 0) > args.max_placements:
                why = f'placed {placements[rec]}x in the world'
            if why:
                flagged.append((e, why))
        for e, why in flagged:
            print(f"  PRUNE {e['goal']:16} {e['id']} {e['give'][0]!r:40} {why}")
        print(f'{len(flagged)} entries are not quest items')
        if args.apply and flagged:
            kill = {(e['goal'], e['id']) for e, _ in flagged}
            keep = []
            for line in qi_path.read_text(encoding='utf-8').splitlines():
                m = re.search(r'goal: (\w+),', line)
                i = re.search(r'\bid: (\d+)', line)
                if m and i and (m.group(1), int(i.group(1))) in kill:
                    continue
                keep.append(line)
            qi_path.write_text('\n'.join(keep) + '\n', encoding='utf-8')
            print(f'{len(flagged)} entries removed from {qi_path} (run gen_lua.py + install_apworld.py)')
        return

    next_id = max([ITEMS_BASE] + [e['id'] for e in existing if ITEMS_BASE <= e['id'] < ITEMS_LIMIT])

    cands = []
    for (goal, item), e in sorted(found.items()):
        if args.goal and goal not in set(args.goal):
            continue
        if item in known_records:
            continue
        if item in QUEST_ITEM_ALIASES:
            continue
        name = item_rec.get(item, ('', item))[1]
        cands.append({'goal': goal, 'record': item, 'name': name, 'count': e['count'],
                      'via': sorted(e['via']), 'quests': sorted(e['sources'])})

    # --- Whitelist not found via dialogue/script: search the inventories
    # (NPCs, containers, lvl lists). A quest item carried by an NPC
    # (e.g. key_orvas_dren on Orvas Dren) remains a progression item.
    carriers_by_item = {}
    for r in records:
        inv = _records_field(r, 'inventory')
        if not inv:
            continue
        for e in inv:
            rid = None
            if isinstance(e, (list, tuple)) and len(e) >= 2:
                rid = str(e[1]).lower()
            elif isinstance(e, dict):
                rid = str(e.get('id', '')).lower()
            if rid:
                owner = f"{r.get('name') or r.get('id')} ({str(r.get('type', '')).lower()})"
                carriers_by_item.setdefault(rid, []).append(owner)
    for goal in sorted(QUEST_ITEMS_BY_GOAL):
        for wid in sorted(QUEST_ITEMS_BY_GOAL[goal]):
            w = wid.lower()
            if w in known_records or w in QUEST_ITEM_ALIASES:
                continue
            if any(c['record'] == w for c in cands):
                continue
            carriers = carriers_by_item.get(w)
            if not carriers:
                continue
            name = item_rec.get(w, ('', w))[1]
            cands.append({'goal': goal, 'record': w, 'name': name, 'count': 1,
                          'via': ['NPC/container inventory'],
                          'quests': sorted(set(carriers))[:5]})

    rep = data / 'quest_items_candidates.yaml'
    rep.write_text('# Candidates generated by tools/gen_quest_items.py (Filtered Whitelist Mode)\n' +
                   yaml.safe_dump(cands, sort_keys=False, allow_unicode=True), encoding='utf-8')
    per_goal = collections.Counter(c['goal'] for c in cands)
    print(f'{len(cands)} valid candidates -> {rep}')
    for g, n in sorted(per_goal.items()):
        print(f'  {g:18} {n}')

    # --- Audit: whitelist entries without a candidate ---------------------
    # Categories:
    #   alias            -> ignored (obsolete ID, real counterpart known)
    #   already applied  -> ignored (record already present in quest_items.yaml)
    #   obsolete ID      -> the ID does not exist in the ESM; the script suggests
    #                       records whose NAME matches the keywords
    #   not generated    -> the record exists but no candidate: we list the
    #                       journal quests that mention it with their
    #                       classification (adjust quest_groups_override)
    matched = {item for (_goal, item) in found}
    audit_path = data / 'quest_items_whitelist_audit.txt'
    cands_records = {c['record'] for c in cands}
    lines = []
    for goal in sorted(QUEST_ITEMS_BY_GOAL):
        for wid in sorted(QUEST_ITEMS_BY_GOAL[goal]):
            w = wid.lower()
            if w in matched or w in QUEST_ITEM_ALIASES or w in known_records \
                    or w in cands_records:
                continue
            if item_rec and w not in item_rec:
                # obsolete ID: suggestion by name search
                words = [x for x in re.split(r'[_\s]+', w) if len(x) > 3]
                sugg = []
                for rid, (rt, rname) in item_rec.items():
                    n = rname.lower()
                    if words and all(xd in n for xd in words):
                        sugg.append(f'{rid} ({rname})')
                    if len(sugg) >= 5:
                        break
                lines.append(f'{goal:16} {wid:40} ABSENT from the ESM'
                             + (f'; candidates by name: {", ".join(sugg)}' if sugg else '; no suggestion'))
            else:
                # record present but not generated: which quests mention it?
                mentions = {}
                for r in records:
                    t = str(r.get('type', ''))
                    if t not in ('DialogueInfo', 'Script'):
                        continue
                    text = r.get('script_text') or r.get('text') or ''
                    # the record may be required via a dialogue filter rather
                    # than in the script text
                    if w not in text.lower() and w not in \
                            [str(x).lower() for x in filter_items(r)]:
                        continue
                    for q in journal_quests(text) | filter_journals(r):
                        g = classify(q, overrides) or 'UNCLASSIFIED'
                        mentions[f'{q} ({g})'] = None
                det = ('; quests mentioning it: ' + ', '.join(sorted(mentions))) if mentions \
                    else '; no journal quest mentions it (AddItem outside scan)'
                lines.append(f'{goal:16} {wid:40} present in the ESM but not generated{det}')
    if lines:
        audit_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(f'WARNING: {len(lines)} whitelist entries without a candidate -> {audit_path}')
        for l in lines:
            print(f'  {l}')

    if args.apply and cands:
        # Record index -> id already assigned (in quest_items.yaml or in cands).
        # The same record may belong to several goals (e.g. bk_chroniclesnchuleft
        # for mages_guild and telvanni): it must then share the same AP id,
        # otherwise receiving the item from one goal does not mark the other as
        # owned and the mod removes the vanilla copy.
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
                # Duplicate: reuse the existing id, do not increment next_id.
                item_id = record_to_id[rec_low]
            else:
                next_id += 1
                if next_id >= ITEMS_LIMIT:
                    raise SystemExit('item ID range exhausted')
                item_id = next_id
                record_to_id[rec_low] = item_id
            if name.lower() in known_names:
                name = f"{name} ({c['goal']})"
            known_names.add(name.lower())
            lines.append('- {name: %s, id: %d, goal: %s, give: [%s, %d], suppress: [%s]}' % (
                json.dumps(name, ensure_ascii=False), item_id, c['goal'],
                json.dumps(rec), c['count'], json.dumps(rec)))
        with open(qi_path, 'a', encoding='utf-8') as f:
            f.write('\n# --- added by tools/gen_quest_items.py --apply ---\n' + '\n'.join(lines) + '\n')
        print(f'{len(cands)} entries added to {qi_path}')


if __name__ == '__main__':
    main()
