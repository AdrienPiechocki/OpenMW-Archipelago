#!/usr/bin/env python3
"""Merge ESM-derived needs_item / rewards into quest_tree.json.

The UESP scraper only knows ids / completion_stages / region / triggers.
Progression items (needs_item) come from data/quest_items.yaml
(gen_quest_items.py --apply), rewards come from data/quest_rewards.yaml
(gen_quest_rewards.py --apply). Both files index by *journal id*; this
script joins them to quest_tree.json via each quest's "ids" list.

FIXES applied in this version:
  1. rewards are attached to the reward's REAL stage (e['stage']) instead
     of ALL completion stages of the quest.
  2. quests whose completion_stages are ALL empty are removed from the
     tree (they cannot be a valid Archipelago goal).
  3. every needs_item is validated against the ESM JSON dumps passed via
     --esm-json. Non-resolvable IDs are logged and dropped. The canonical
     case (e.g. 'TR_m2_q_18_Potion') is restored from the ESM.
  4. an item that is in FACTION_GLOBAL_ITEMS is kept if it is explicitly
     whitelisted in QUEST_ITEMS_BY_GOAL (e.g. 'writ_oran'), so the two
     lists no longer contradict each other.
  5. needs_item entries whose ONLY evidence in the ESM is a GetItemCount
     are dropped (false progression positives).
  6. data/quest_items.yaml may contain a `via` field as a *list of lists*
     (e.g. [['required (Item filter)']]) due to an earlier double
     serialisation bug. `load_items()` flattens it.
  7. PROGRESSION_BLOCKLIST (global): items that are false positives even
     when the `via` heuristic would keep them. Includes ambient items that
     slipped through (raw ore, common potions) and known mis-attributed
     items (Ash Statue).
  8. PROGRESSION_BLOCKLIST_BY_QUEST (per-quest): items that are false
     positives only for a *specific* quest. Used to remove:
       - cross-attributed items when a multi-journal dialogue shares an
         item between unrelated quests (e.g. TR_m4_HH_GavrosStatue is
         shared between tr_m4_and_missingmerchant (legitimate) and both
         a1_2_antabolisinformant and a2_2_6thhouse (false positives));
       - items consumed by a *different* NPC than the quest giver (e.g.
         Caius consuming bk_A1_1_CaiusPackage in a dialogue that also sets
         the a1_2_antabolisinformant journal stage).
  9. (NEW) a reward's stage does NOT have to be a completion stage. The
     stage is only used by the mod to know WHEN to remove the vanilla
     item; AddItem can happen at any journal stage. If the raw stage is
     not a completion stage, it is bumped to the smallest completion stage
     >= raw stage (or the smallest completion stage if none is higher),
     so the vanilla item is never removed before the check can be sent.
 10. (NEW) an item whose ONLY evidence in quest_items.yaml is 'AddItem'
     is not a progression item: it is given to the player (reward, key,
     scroll). Such items belong in quest_rewards.yaml, not needs_item.

The per-faction frequency filter (GLOBAL_ITEM_THRESHOLD) is applied by
gen_quest_items.py at scan time, where the faction of a record is known.

Usage:
  python tools/merge_quest_items_into_tree.py \\
      --tree uesp_tree_out/quest_tree.json \\
      --items data/quest_items.yaml \\
      --rewards data/quest_rewards.yaml \\
      --esm-json build/morrowind.json build/tribunal.json build/bloodmoon.json \\
                 build/tr_mainland.json build/tamriel_data.json \\
      --out uesp_tree_out/quest_tree.json
"""
import argparse
import collections
import json
import pathlib
import sys

import yaml

AMBIENT_PREFIXES = (
    'common_', 'misc_soulgem_', 'ingred_', 'food_', 'sc_',
    'potion_of_', 'bookskill_', 'exclusive_', 'quality_',
    'standard_', 'bargain_', 'cheap_', 'distilled_', 'p_',
)
AMBIENT_ITEMS = {
    'gold_001', 'gold_005', 'gold_010', 'gold_025', 'gold_100',
    'misc_lw_bowl', 'misc_lw_cup', 'misc_lw_platter',
    'misc_de_goblet_01', 'misc_de_bowl_orange_green_01',
    'misc_de_drum_02', 'misc_de_plate_01',
    'fur_colovian_helm', 'bk_abcs',
    'exquisite_shirt_01', 'exquisite_shirt_02', 'exquisite_shirt_03',
    'exquisite_pants_01', 'exquisite_pants_02',
    'exquisite_skirt_01', 'exquisite_skirt_02',
    'exquisite_shoes_01', 'exquisite_shoes_02',
    'exquisite_robe_01', 'exquisite_robe_02',
    'exquisite_amulet_01', 'exquisite_amulet_02',
    'exquisite_ring_01', 'exquisite_ring_02',
    'exquisite_belt_01',
    *[f'misc_dwrv_artifact{i:02d}' for i in range(10, 100)],
}
TR_AMBIENT_PREFIXES = (
    't_bk_', 't_de_', 't_imp_', 't_com_', 't_ing_', 't_ingmine_', 't_sc_', 't_ensc_',
    't_dae_', 't_bre_', 't_nor_', 't_rga_', 't_arg_', 't_kha_', 't_we_',
    't_ag_', 't_miss_', 't_lore_',
)
TR_UNIQUE_MARKERS = ('_unique', '_uni', 'uni_', '_unic', '_reward')
FACTION_GLOBAL_ITEMS = {
    'bk_bm_stockcert', 'bk_colonyreport', 'bk_colony_toralf', 'bk_carniusnote',
    *[f'writ_{x}' for x in (
        'alen', 'baladas', 'belvayn', 'bemis', 'berano', 'bero', 'brilnosu',
        'dils', 'galasa', 'guril', 'hloggar', 'mavon', 'navil', 'oran',
        'sadus', 'saren', 'therana', 'varro', 'vendu', 'yasalmibaal',
    )],
    'common_glove_l_balmolagmer', 'common_glove_r_balmolagmer',
    'slave_bracer_left', 'slave_bracer_right',
    't_glb_var_headfixer',
    't_bk_stockcerteec_nar',
}

# FIX #7: items that are known false positives even when the `via` heuristic
# would keep them. Items listed here are NEVER treated as progression
# requirements, in any quest.
PROGRESSION_BLOCKLIST = {
    # Appears in "Report to Caius Cosades" (main_quest) and in redoran
    # quests, but no dialogue linked to a1_1_findspymaster actually
    # requires it.
    'misc_6th_ash_statue_01',
    # Raw ore items: trade goods, not quest items. They slip through
    # TR_AMBIENT_PREFIXES because 't_ingmine_' is not a prefix of 't_ing_'.
    't_ingmine_oregold_01',
    't_ingmine_oreiron_01',
    # Generic common potion: not a quest item, appears in multi-journal
    # trade dialogues.
    'p_cure_common_s',
    # Leftover from a test mod ('11111 test journal').
    "miner's",
}

# FIX #8: items that are false positives only for a *specific* quest.
# Used to remove:
#   - cross-attributed items when a multi-journal dialogue shares an item
#     between unrelated quests;
#   - items consumed by a *different* NPC than the quest giver.
#
# Each entry maps a journal id (lowercase) to a set of item ids (lowercase)
# that must NOT be treated as progression items for that quest.
PROGRESSION_BLOCKLIST_BY_QUEST = {
    'a1_2_antabolisinformant': {
        # TR item shared with tr_m4_and_missingmerchant via a multi-journal
        # dialogue (build/tr_mainland.json id 695272403243818288). Belongs
        # to tr_m4_and_missingmerchant, not to Antabolis Informant.
        'tr_m4_hh_gavrosstatue',
        # Mages Guild item shared with mg_excavation via a multi-journal
        # dialogue (build/morrowind.json id 30149342957665081). Belongs
        # to mg_excavation (Nchuleftingth Expedition).
        'bk_a1_2_introtocadiusus',
        # Consumed by Caius in a dialogue that also sets the
        # a1_2_antabolisinformant journal stage (build/morrowind.json id
        # 43741759216181215), but the package belongs to a1_1_findspymaster
        # (Report to Caius Cosades). Antabolis never asks for the package.
        'bk_a1_1_caiuspackage',
    },
    'a2_2_6thhouse': {
        # TR item shared with tr_m4_and_missingmerchant via a multi-journal
        # dialogue (build/tr_mainland.json id 1638124430414121453). Belongs
        # to tr_m4_and_missingmerchant, not to Sixth House Base.
        'tr_m4_hh_gavrosstatue',
    },
}


def is_tr_ambient(item):
    low = item.lower()
    if not any(low.startswith(p) for p in TR_AMBIENT_PREFIXES):
        return False
    if any(marker in low for marker in TR_UNIQUE_MARKERS):
        return False
    return True


def is_ambient(item):
    low = item.lower()
    if low in AMBIENT_ITEMS:
        return True
    if any(low.startswith(p) for p in AMBIENT_PREFIXES):
        return True
    if is_tr_ambient(item):
        return True
    return False


def is_faction_global(item):
    return item.lower() in {x.lower() for x in FACTION_GLOBAL_ITEMS}


def is_protected_by_whitelist(item):
    """True if 'item' is explicitly listed in ANY QUEST_ITEMS_BY_GOAL set."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    try:
        import gen_quest_items as gqi
    except Exception:
        return False
    low = item.lower()
    for goal_items in gqi.QUEST_ITEMS_BY_GOAL.values():
        if low in {str(x).lower() for x in goal_items}:
            return True
    return False


def _flatten_via(via):
    """FIX #6: accept ['a','b'], [['a','b']], [['a'],['b']], None and
    return a flat list of strings."""
    out = []
    for v in via or []:
        if isinstance(v, (list, tuple)):
            out.extend(str(x) for x in v)
        else:
            out.append(str(v))
    return out


def is_real_progression(entry):
    """FIX #5: an item is a progression requirement only if at least one
    non-GetItemCount evidence produced it."""
    via = _flatten_via(entry.get('via')) if entry else []
    if not via:
        return True
    return any(v != 'GetItemCount' for v in via)


def is_add_only(entry):
    """FIX #10: an item whose ONLY evidence is 'AddItem' is given to the
    player (reward, key, scroll), not consumed by a quest step. It belongs
    in quest_rewards.yaml, not in needs_item."""
    via = _flatten_via(entry.get('via')) if entry else []
    return bool(via) and all(v == 'AddItem' for v in via)


def load_items(path):
    """Return {record_lower: {'name':..., 'goal':..., 'via': [...]}}."""
    data = yaml.safe_load(pathlib.Path(path).read_text(encoding='utf-8')) or []
    out = {}
    for e in data:
        via = _flatten_via(e.get('via'))
        for r in (e.get('suppress') or []):
            out.setdefault(str(r).lower(),
                           {'name': e.get('name'), 'goal': e.get('goal'), 'via': via})
        if e.get('give'):
            out.setdefault(str(e['give'][0]).lower(),
                           {'name': e.get('name'), 'goal': e.get('goal'), 'via': via})
    return out


def load_rewards(path):
    data = yaml.safe_load(pathlib.Path(path).read_text(encoding='utf-8')) or []
    out = collections.defaultdict(list)
    for e in data:
        q = str(e.get('quest', '')).lower()
        if q:
            out[q].append(e)
    return out


def load_esm_item_ids(esm_paths):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import gen_quest_items as gqi

    by_lower = {}
    for p in esm_paths:
        try:
            with open(p, encoding='utf-8') as f:
                for r in json.load(f):
                    t = str(r.get('type', '')).lower()
                    if t in gqi.ITEM_TYPES and r.get('id'):
                        rid = str(r['id'])
                        by_lower.setdefault(rid.lower(), rid)
        except FileNotFoundError:
            print(f'WARNING: ESM JSON not found: {p}', file=sys.stderr)
    return by_lower


def load_quest_items_from_esm(esm_paths, known_progression_records):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import gen_quest_items as gqi

    wanted = {r.lower() for r in known_progression_records}
    if not wanted:
        return {}

    item_rec = {}
    journal_ids = set()
    for p in esm_paths:
        with open(p, encoding='utf-8') as f:
            for r in json.load(f):
                t = str(r.get('type', '')).lower()
                if t in gqi.ITEM_TYPES and r.get('id'):
                    rid = str(r['id'])
                    item_rec.setdefault(rid.lower(), (t, r.get('name') or rid, rid))
                elif t == 'dialogue' and str(r.get('dialogue_type', '')).lower() == 'journal':
                    journal_ids.add(str(r.get('id', '')).lower())

    out = collections.defaultdict(set)

    for p in esm_paths:
        with open(p, encoding='utf-8') as f:
            for r in json.load(f):
                t = str(r.get('type', ''))
                if t not in ('DialogueInfo', 'Script'):
                    continue
                text = r.get('script_text') or r.get('text') or ''
                quests = set()
                for q in gqi.journal_quests(text) | gqi.filter_journals(r):
                    if not journal_ids or q in journal_ids:
                        quests.add(q)
                if not quests:
                    continue

                found_records = set()
                for m in gqi.PAT_REMOVE.finditer(text):
                    found_records.add(m.group(1).lower())
                for m in gqi.PAT_COUNT.finditer(text):
                    found_records.add(m.group(1).lower())
                if isinstance(r, dict):
                    for it in gqi.filter_items(r):
                        found_records.add(it)
                for m in gqi.PAT_ADD.finditer(text):
                    found_records.add(m.group(1).lower())

                for rec in found_records & wanted:
                    for q in quests:
                        out[q].add(rec)

    return dict(out)


def merge(tree, needs_by_journal, rewards_by_journal, esm_item_ids, items_by_record):
    """Apply all filters and produce the final tree."""

    def keep(rec, qid):
        low = rec.lower()
        if low in PROGRESSION_BLOCKLIST:
            return False
        if low in PROGRESSION_BLOCKLIST_BY_QUEST.get(qid, set()):
            return False
        if is_ambient(rec):
            return False
        if is_faction_global(rec) and not is_protected_by_whitelist(rec):
            return False
        # FIX #10: an item that is ONLY given to the player (AddItem) is a
        # reward/key, not a progression item.
        if is_add_only(items_by_record.get(low)):
            return False
        return True

    def canonical(rec):
        return esm_item_ids.get(rec.lower(), rec)

    total_needs = 0
    total_rewards = 0
    dropped = collections.Counter()
    dropped_getitemcount = collections.Counter()
    dropped_addonly = collections.Counter()
    dropped_blocklist = collections.Counter()
    dropped_blocklist_by_quest = collections.Counter()
    dropped_needs_unknown = []
    removed_empty = []

    for origin, lines in tree.items():
        for line, quests in lines.items():
            for qname, qdata in list(quests.items()):
                all_stages = sorted({
                    s for v in qdata.get('completion_stages', {}).values()
                    for s in v
                })

                if not all_stages:
                    removed_empty.append((origin, line, qname))
                    del quests[qname]
                    continue

                qids = {str(i).lower() for i in qdata.get('ids', [])}

                needs = []
                seen_needs = set()
                for qid in qids:
                    for rec in needs_by_journal.get(qid, ()):
                        low = rec.lower()
                        if low in PROGRESSION_BLOCKLIST:
                            dropped_blocklist[rec] += 1
                            continue
                        if low in PROGRESSION_BLOCKLIST_BY_QUEST.get(qid, set()):
                            dropped_blocklist_by_quest[(qid, rec)] += 1
                            continue
                        entry = items_by_record.get(rec)
                        if not is_real_progression(entry):
                            dropped_getitemcount[rec] += 1
                            continue
                        if is_add_only(entry):
                            dropped_addonly[rec] += 1
                            continue
                        if not keep(rec, qid):
                            dropped[rec] += 1
                            continue
                        canon = canonical(rec)
                        if esm_item_ids and canon.lower() not in esm_item_ids:
                            dropped_needs_unknown.append((origin, line, qname, rec))
                            continue
                        if canon.lower() in seen_needs:
                            continue
                        seen_needs.add(canon.lower())
                        needs.append(canon)
                needs.sort()
                qdata['needs_item'] = needs
                total_needs += len(needs)

                rew = {}
                for qid in qids:
                    for e in rewards_by_journal.get(qid, []):
                        rec = str(e['record'])
                        if rec.lower() in PROGRESSION_BLOCKLIST:
                            continue
                        canon = canonical(rec)
                        if canon.lower() in seen_needs:
                            continue
                        stage = int(e.get('stage', 0))
                        if stage <= 0:
                            continue
                        # FIX #9: a reward's stage does NOT have to be a
                        # completion stage. The stage only tells the mod when
                        # to remove the vanilla item. If the raw stage is not
                        # a completion stage, bump it to the smallest
                        # completion stage >= raw stage (so the vanilla item
                        # is never removed before the check can be sent); if
                        # none is higher, use the smallest completion stage.
                        if stage not in all_stages:
                            higher = [s for s in all_stages if s >= stage]
                            stage = min(higher) if higher else min(all_stages)
                        rew.setdefault(canon, set()).add(stage)
                qdata['rewards'] = {k: sorted(v) for k, v in sorted(rew.items())}
                total_rewards += len(qdata['rewards'])

    if dropped:
        print(f'dropped {len(dropped)} ambient/global items from needs_item:',
              file=sys.stderr)
        for rec, n in dropped.most_common(20):
            print(f'  {rec:45} x{n}', file=sys.stderr)

    if dropped_blocklist:
        print(f'dropped {len(dropped_blocklist)} PROGRESSION_BLOCKLIST items:',
              file=sys.stderr)
        for rec, n in dropped_blocklist.most_common(20):
            print(f'  {rec:45} x{n}', file=sys.stderr)

    if dropped_blocklist_by_quest:
        print(f'dropped {len(dropped_blocklist_by_quest)} '
              f'PROGRESSION_BLOCKLIST_BY_QUEST items:', file=sys.stderr)
        for (qid, rec), n in dropped_blocklist_by_quest.most_common(20):
            print(f'  {qid:35} {rec:45} x{n}', file=sys.stderr)

    if dropped_getitemcount:
        print(f'dropped {len(dropped_getitemcount)} GetItemCount-only items:',
              file=sys.stderr)
        for rec, n in dropped_getitemcount.most_common(20):
            print(f'  {rec:45} x{n}', file=sys.stderr)

    if dropped_addonly:
        print(f'dropped {len(dropped_addonly)} AddItem-only items '
              f'(these belong in quest_rewards.yaml):', file=sys.stderr)
        for rec, n in dropped_addonly.most_common(20):
            print(f'  {rec:45} x{n}', file=sys.stderr)

    if dropped_needs_unknown:
        print(f'dropped {len(dropped_needs_unknown)} needs_item not found in ESM:',
              file=sys.stderr)
        for origin, line, qname, rec in dropped_needs_unknown[:40]:
            print(f'  {origin}/{line}/{qname}: {rec!r}', file=sys.stderr)

    if removed_empty:
        print(f'removed {len(removed_empty)} quests with no completion stage:',
              file=sys.stderr)
        for origin, line, qname in removed_empty[:40]:
            print(f'  {origin}/{line}/{qname}', file=sys.stderr)

    return tree, total_needs, total_rewards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    ap.add_argument('--items', required=True)
    ap.add_argument('--rewards', required=True)
    ap.add_argument('--esm-json', nargs='+', required=True)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    tree_path = pathlib.Path(args.tree)
    tree = json.loads(tree_path.read_text(encoding='utf-8'))

    esm_item_ids = load_esm_item_ids(args.esm_json)
    if not esm_item_ids:
        print('WARNING: no ESM item IDs loaded; needs_item will NOT be validated.',
              file=sys.stderr)

    items_by_record = load_items(args.items)
    known_progression_records = set(items_by_record.keys())
    rewards_by_journal = load_rewards(args.rewards)
    needs_by_journal = load_quest_items_from_esm(args.esm_json, known_progression_records)

    tree, total_needs, total_rewards = merge(
        tree, needs_by_journal, rewards_by_journal, esm_item_ids, items_by_record)

    out = pathlib.Path(args.out) if args.out else tree_path
    out.write_text(json.dumps(tree, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'merged items -> {out}')
    print(f'  needs_item: {total_needs} records across all quests')
    print(f'  rewards:    {total_rewards} records across all quests')


if __name__ == '__main__':
    main()
