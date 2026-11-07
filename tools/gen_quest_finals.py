#!/usr/bin/env python3
"""Generates data/quest_finals.yaml: completion stages per quest.

Each entry contains:
  stage  : "main" stage (the highest ending stage, or the override);
           kept for compatibility.
  stages : ALL stages that successfully finish the quest. The quest is
           completed as soon as one of these stages is reached.
  fail   : failure stages (cancel the completion).

Completion stages are deduced from the ESM: a journal entry stage that
neither a dialogue (Journal filter) nor a script (GetJournalIndex) uses as a
condition has no follow-up: it is a possible ending (candidate). The
quest_finish stages are added if they exist (tes3conv does not always export
them), then known failure stages are removed. As a fallback, we take the
highest Journal stage (< 150). Overrides fix known branches. Automatically
added stages are listed in quest_review.txt.

Usage:
  tes3conv Morrowind.esm morrowind.json
  python tools/gen_quest_finals.py /tmp/morrowind.json --out data/quest_finals.yaml
  # --recompute: also recomputes quests already present (stage/stages)
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

# Explicit "main" stage when the raw maximum does not match the quest's
# actual "successful" ending.
STAGE_OVERRIDES = {
    'fg_nchurdamz': 100,
    'il_maidentoken': 110,
    'mv_strayedpilgrim': 100,
    'tt_diseasecarrier': 100,
    'tt_ministryheathen': 100,
    'tt_sanctusshrine': 100,
    'c3_destroydagoth': 50,
    'a1_4_muzgobinformant': 30,
    'mv_recoverwidowmaker': 80,
    'mv_abusedhealer': 85,
    'il_rescuepilgrim': 100,
    'b3_zainabbride': 55,
    'eb_invisible': 120,
    'mv_cultistvictim': 100,
    'mv_3_charming': 90,
}

# COMPLETE list of completion stages, when the automatic deduction
# (quest_finish minus failures) is wrong. Takes priority over everything else.
# Nels Llendo: 90 (refusal/attack), 100 (gold), 120 and 130 (kiss) all finish
# the quest; 140 is only a follow-up at Pelagiad, often never reached.
STAGES_OVERRIDES = {
    'mv_3_charming': [90, 100, 120, 130],
}

# Stages to add to the automatic deduction (endings not flagged quest_finish).
STAGES_EXTRA = {
    # 'quest_id': [stage, ...],
    'mv_monsterdisease': [60],
}

# Stages to remove from the automatic deduction (intermediate, dialogues,
# refusals/abandonments...). Verified against the journal text (quest_review.txt).
_HORT = [5, 10, 20]
STAGES_EXCLUDE = {
    'a1_1_findspymaster': [20],
    'a1_sleepersawake': [1, 7],
    'a1_v_vivecinformants': [55],
    'a2_6_incarnate': [52, 54, 60, 62, 64, 70, 72, 74, 76, 78, 80],
    'b5_arobarhort': _HORT, 'b5_llethrihort': _HORT,
    'b5_morvaynhort': _HORT, 'b5_ramoranhort': _HORT,
    'b6_berohort': [5], 'b6_curiohort': [5], 'b6_omanihort': [5, 20],
    'b6_uleshort': [5, 20], 'b6_ynglinghort': [5, 20],
    'b7_baladashort': [5, 30], 'b7_drathahort': [5, 10, 30],
    'b7_gothrenhort': [5], 'b7_nelothhort': [5, 30], 'b7_theranahort': [5, 30],
    'c0_act_c': [1, 2, 3, 4, 5, 6, 7, 10, 15],
    'cx_backpath': [5, 10, 55, 60],
    'da_azura': [40], 'da_mehrunes': [10], 'da_molagbal': [10],
    'da_sheogorath': [20, 40, 50, 55],
    'hh_wincamonna': [5], 'hr_calderacorrupt': [30],
    'ht_archmagister': [10], 'ht_stronghold': [105],
    'ic12_dinner_not': [0], 'ic26_amanin': [5, 10], 'ic29_crusher': [10, 15],
    'ic8_heidmir': [10], 'ic8_ingokning': [10],
    'il_blueprints': [10], 'ms_fargothring': [10],
    'ms_jobashaabolitionist': [10], 'ms_piernette': [10],
    'ms_umbra': [10, 20, 30, 40], 'mt_grandmaster': [10, 20],
    'mv_abusedhealer': [60], 'mv_tradermissed': [110], 'mv_victimromance': [110],
    'town_aldruhn': [50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 76, 77, 78, 79],
    'town_tel_vos_ashur': [1],
    'va_vampamulet': [10, 25], 'va_vampcountess': [30], 'va_vampmarara': [20, 40],
}

# Stages that cancel completion (failure branch).
FAIL_STAGES = {
    'fg_nchurdamz': [110],
    'il_maidentoken': [120],
    'il_rescuepilgrim': [200],
    'mv_recoverwidowmaker': [90],
    'mv_strayedpilgrim': [110, 115],
    'tt_diseasecarrier': [110],
    'tt_ministryheathen': [200],
    'tt_sanctusshrine': [110],
    'mv_abusedhealer': [80],
    'b3_zainabbride': [60],
    'eb_invisible': [140],
    'mv_cultistvictim': [110],
    'mv_fakeslave': [90],       # Tul dies on the way
    'mv_poorpilgrim': [110],    # time ran out
    'mv_richtrader': [110],     # the merchant dies
}

PAT_QUOTED = re.compile(r'(?<!Get)Journal\s*,?\s*"([^"]+)"\s*,?\s*(\d+)', re.I)
PAT_BARE = re.compile(r'(?<!Get)Journal\s*,?\s*([A-Za-z_][A-Za-z0-9_\-]*)\s*,?\s*(\d+)', re.I)
PAT_COND = re.compile(
    r'GetJournalIndex\s*,?\s*"?([A-Za-z_][A-Za-z0-9_\-]*)"?\s*(==|=|>=|>|<=|<|!=)\s*(\d+)', re.I)

# comparison (tes3conv filter) -> operator
CMP = {'equal': '==', 'notequal': '!=', 'greater': '>', 'greaterequal': '>=',
       'less': '<', 'lessequal': '<='}


class Data:
    def __init__(self):
        self.stages = collections.defaultdict(set)   # stages set by Journal (scripts)
        self.entries = collections.defaultdict(set)  # stages having a journal entry
        self.conds = collections.defaultdict(list)   # (op, value) read as conditions
        self.finishes = collections.defaultdict(set)  # quest_finish, if exported
        self.texts = {}                              # (quest, stage) -> text


def collect_stages(esm_jsons, scripts_path=None):
    D = Data()

    def add_text(text):
        if not text:
            return
        for pat in (PAT_QUOTED, PAT_BARE):
            for m in pat.finditer(text):
                D.stages[m.group(1).strip().lower()].add(int(m.group(2)))
        for m in PAT_COND.finditer(text):
            D.conds[m.group(1).strip().lower()].append((m.group(2), int(m.group(3))))

    for esm_json in esm_jsons:
        with open(esm_json, encoding='utf-8') as f:
            data = json.load(f)
        cur_id, cur_journal = None, False
        for rec in data:
            t = rec.get('type')
            if t == 'Dialogue':
                cur_id = (rec.get('id') or '').lower()
                cur_journal = str(rec.get('dialogue_type', '')).lower() == 'journal'
            elif t == 'DialogueInfo':
                add_text(rec.get('script_text'))
                for flt in rec.get('filters') or []:
                    if str(flt.get('filter_type', '')).lower() != 'journal':
                        continue
                    op = CMP.get(str(flt.get('comparison', '')).lower())
                    val = (flt.get('value') or {}).get('data')
                    if op and isinstance(val, int) and flt.get('id'):
                        D.conds[str(flt['id']).strip().lower()].append((op, val))
                d = rec.get('data') or {}
                st = d.get('disposition')
                if cur_journal and cur_id and isinstance(st, int):
                    D.entries[cur_id].add(st)
                    D.texts.setdefault((cur_id, st), (rec.get('text') or '').strip())
                    if rec.get('quest_finish'):
                        D.finishes[cur_id].add(st)
            elif t == 'Script':
                add_text(rec.get('script_text') or rec.get('text'))

    if scripts_path:
        with open(scripts_path, encoding='utf-8', errors='replace') as f:
            for line in f:
                add_text(line)

    return D


def terminal_stages(D, qid):
    """Journal entry stages (< 150) that no condition consumes."""
    used = set()
    for op, v in D.conds.get(qid, []):
        for s in D.entries.get(qid, ()):
            if op in ('==', '>=', '>') and s == v:
                used.add(s)
            elif op == '!=' and s == v:
                used.add(s)
            elif op == '<' and s < v:
                used.add(s)
            elif op == '<=' and s <= v:
                used.add(s)
    return sorted(s for s in D.entries.get(qid, ()) if s < 150 and s not in used)


def completion_stages(qid, raw, fin, fail, known_stage=None):
    """Returns (main stage, sorted list of all ending stages)."""
    if qid in STAGES_OVERRIDES:
        found = sorted(set(STAGES_OVERRIDES[qid]))
    else:
        exclude = set(STAGES_EXCLUDE.get(qid, [])) | set(fail)
        found = set(fin) | set(STAGES_EXTRA.get(qid, []))
        if STAGE_OVERRIDES.get(qid) is not None:
            found.add(STAGE_OVERRIDES[qid])
        if known_stage:
            found.add(known_stage)
        found = sorted(s for s in found if s not in exclude)
        if not found:
            found = [raw[-1]] if raw else [0]
    main = STAGE_OVERRIDES.get(qid)
    if main is None:
        main = known_stage if known_stage else found[-1]
    if main not in found:
        found = sorted(found + [main])
    return main, found


def snippet(D, qid, st):
    t = D.texts.get((qid, st), '').replace('\n', ' ')
    return (t[:80] + '...') if len(t) > 80 else t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('esm_json', nargs='+')
    ap.add_argument('--scripts', default=None,
                    help='script text dump (optional, improves coverage)')
    ap.add_argument('--qc', default='data/quest_completions.yaml')
    ap.add_argument('--out', default='data/quest_finals.yaml')
    ap.add_argument('--recompute', action='store_true',
                    help='also recomputes stage/stages of quests already present')
    ap.add_argument('--no-auto', action='store_true',
                    help="does not add automatically deduced stages without follow-up")
    args = ap.parse_args()

    D = collect_stages(args.esm_json, args.scripts)
    if not D.finishes:
        print('info: no quest_finish in the JSON, endings deduced from conditions '
              '(Journal / GetJournalIndex filters)')

    existing = {}
    if pathlib.Path(args.out).exists():
        with open(args.out, encoding='utf-8') as f:
            for row in yaml.safe_load(f) or []:
                existing[str(row['quest']).lower()] = row

    with open(args.qc, encoding='utf-8') as f:
        completions = yaml.safe_load(f) or []

    ids = collections.defaultdict(list)
    for q in completions:
        qid = str(q['trigger']['quest']).strip().lower()
        ids[qid].append(q['id'])

    overrides = load_overrides(pathlib.Path(args.qc).parent / 'quest_groups_override.yaml')
    rows, review = [], []
    for qid in sorted(ids):
        raw = sorted(s for s in D.stages.get(qid, set()) if s < 150)
        fin = set(s for s in D.finishes.get(qid, set()) if s < 150)
        if not args.no_auto:
            fin |= set(terminal_stages(D, qid))
        fin = sorted(fin)

        if qid in existing:
            row = dict(existing[qid])
            fail = sorted(set(row.get('fail') or []) | set(FAIL_STAGES.get(qid, [])))
            known = None if args.recompute else row.get('stage')
            main, found = completion_stages(qid, raw, fin, fail, known)
            old = row.get('stages')
            if args.recompute or not old:
                row['stage'] = main
                row['stages'] = found
            else:
                row['stages'] = sorted(set(old) | set(found))
            # purge: excluded / failure stages already written by a previous run
            drop = set(STAGES_EXCLUDE.get(qid, [])) | set(fail)
            row['stages'] = sorted((set(row['stages']) - drop) | {row['stage']})
            if qid in STAGES_OVERRIDES:
                row['stages'] = sorted(STAGES_OVERRIDES[qid])
            row['fail'] = fail
            row['ids'] = ids[qid]
            row['group'] = classify(qid, overrides)
            added = [s for s in row['stages'] if s != row['stage']]
            if added and old != row['stages']:
                review.append(f'{qid}: stage={row["stage"]} stages={row["stages"]} (existing)')
                for s in added:
                    review.append(f'    + {s}: {snippet(D, qid, s)}')
            rows.append(row)
            continue

        fail = FAIL_STAGES.get(qid, [])
        main, found = completion_stages(qid, raw, fin, fail)
        rows.append({
            'quest': qid,
            'stage': main,
            'stages': found,
            'fail': fail,
            'ids': ids[qid],
            'group': classify(qid, overrides),
        })
        flag = '' if len(found) <= 1 else '  <-- several possible endings, check'
        review.append(f'{qid}: stage={main} stages={found} raw={raw}{flag}')
        for s in found:
            if s != main:
                review.append(f'    + {s}: {snippet(D, qid, s)}')

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        yaml.safe_dump(rows, f, sort_keys=False, allow_unicode=True)
    multi = sum(1 for r in rows if len(r['stages']) > 1)
    print(f'quest finals: {len(rows)} entries -> {out} ({multi} with several endings)')
    rp = out.with_name('quest_review.txt')
    if review:
        rp.write_text('\n'.join(review) + '\n', encoding='utf-8')
        print(f'to check in {rp}')
    elif rp.exists():
        rp.unlink()


if __name__ == '__main__':
    main()
