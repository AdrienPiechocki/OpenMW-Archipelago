#!/usr/bin/env python3
"""ESM -> YAML extraction (quests and factions; no longer exploration).

Usage:
  tes3conv Morrowind.esm morrowind.json
  tes3conv Tribunal.esm  tribunal.json     # optional
  tes3conv Bloodmoon.esm bloodmoon.json    # optional
  tes3conv TR_Mainland.esm tr_mainland.json  # optional (Tamriel Rebuilt)
  tes3conv Cyr_Main.esm cyr_main.json        # optional (Project Cyrodiil)
  python tools/extract.py morrowind.json [tribunal.json bloodmoon.json tr_mainland.json cyr_main.json] --out data/

Fixes:
  * Journal calls WITHOUT quotes (`Journal MG_Apprentice 10`) are now
    detected (before: only calls with quotes, hence the missing guilds /
    houses / Morag Tong / cult etc.);
  * quest identifiers are validated against the ESM's Journal-type
    dialogues (no more false positives);
  * location IDs are STABLE: entries already present in data/*.yaml keep
    their ID, new ones get max+1. Seeds and existing Lua tables therefore
    remain consistent.
"""
import argparse
import json
import pathlib
import re

import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quest_groups import classify, load_overrides, TR_GROUPS, PC_GROUPS  # noqa: E402
from quest_names import load_names, quest_name, unique_names  # noqa: E402

PAT_QUOTED = re.compile(r'(?<![A-Za-z])Journal[ \t]*,?[ \t]*"([^"\r\n]+)"[ \t]*,?[ \t]*(\d+)', re.I)
PAT_BARE = re.compile(r'(?<![A-Za-z])Journal[ \t]*,?[ \t]*([A-Za-z_][A-Za-z0-9_\-]*)[ \t]*,?[ \t]*(\d+)', re.I)

STAGE_BASE, STAGE_LIMIT = 7700000, 7710000
COMPLETE_BASE, COMPLETE_LIMIT = 7720000, 7730000


def load_yaml(path):
    p = pathlib.Path(path)
    if p.exists():
        return yaml.safe_load(p.read_text(encoding='utf-8')) or []
    return []


def dump_yaml(path, data):
    pathlib.Path(path).write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding='utf-8')


def next_id_factory(used, base, limit):
    cur = max([base] + list(used))

    def nxt():
        nonlocal cur
        cur += 1
        if cur >= limit:
            raise SystemExit(f'ID range exhausted ({base}-{limit})')
        return cur
    return nxt


def load_records(paths):
    for p in paths:
        with open(p, encoding='utf-8') as f:
            for r in json.load(f):
                yield r


def origin_of(path):
    """ESM a JSON dump comes from: morrowind | tribunal | bloodmoon | tamriel_rebuilt | project_cyrodiil."""
    name = pathlib.Path(path).name.lower()
    for key in ('tribunal', 'bloodmoon'):
        if key in name:
            return key
    if 'tr_mainland' in name or 'tamriel_rebuilt' in name:
        return 'tamriel_rebuilt'
    if 'cyr_main' in name or 'project_cyrodiil' in name:
        return 'project_cyrodiil'
    return 'morrowind'


def scan_origins(paths):
    """{lower journal id: 'tribunal' | 'bloodmoon'} for journals DEFINED by an
    expansion (absent from Morrowind.esm). Expansions that merely add infos to
    a vanilla journal do not change its group."""
    defined = {}
    for path in paths:
        origin = origin_of(path)
        with open(path, encoding='utf-8') as f:
            for r in json.load(f):
                if r.get('type') == 'Dialogue' and \
                        str(r.get('dialogue_type', '')).lower() == 'journal' and r.get('id'):
                    defined.setdefault(str(r['id']).lower(), origin)
    return {q: o for q, o in defined.items() if o != 'morrowind'}


def scan_quests(paths):
    """Returns (journal_ids, pairs, finish):
    journal_ids : {lower: display name} of Journal dialogues
    pairs       : {lower: set(stages)} found in scripts/results
    finish      : {lower: set(stages)} marked 'quest_finish' in Journal infos
    """
    journal_ids, pairs, finish, journal_stages = {}, {}, {}, {}
    cur_id, cur_is_journal = None, False

    def add_text(text):
        if not text:
            return
        for pat in (PAT_QUOTED, PAT_BARE):
            for m in pat.finditer(text):
                qid = m.group(1).strip()
                if qid and (qid[0].isalpha() or qid[0] == '_'):
                    pairs.setdefault(qid.lower(), set()).add(int(m.group(2)))
                    pairs_names.setdefault(qid.lower(), qid)

    pairs_names = {}
    for r in load_records(paths):
        t = r.get('type')
        if t == 'Dialogue':
            cur_id = r.get('id') or ''
            cur_is_journal = str(r.get('dialogue_type', '')).lower() == 'journal'
            if cur_is_journal and cur_id:
                journal_ids[cur_id.lower()] = cur_id
        elif t == 'DialogueInfo':
            d = r.get('data') or {}
            is_j = str(d.get('dialogue_type', '')).lower() == 'journal' or cur_is_journal
            if is_j and cur_id:
                idx = d.get('disposition')
                if isinstance(idx, int):
                    journal_stages.setdefault(cur_id.lower(), set()).add(idx)
                    if r.get('quest_finish'):
                        finish.setdefault(cur_id.lower(), set()).add(idx)
            add_text(r.get('script_text'))
        elif t == 'Script':
            add_text(r.get('script_text') or r.get('text'))

    if journal_ids:
        dropped = sorted(q for q in pairs if q not in journal_ids)
        if dropped:
            print(f'ignored (not Journal dialogues): {len(dropped)} -> {dropped[:10]}...')
        pairs = {q: s for q, s in pairs.items() if q in journal_ids}
        names = {q: journal_ids[q] for q in pairs}
    else:
        print('WARNING: no Journal dialogue found, no quest ID validation')
        names = pairs_names
    return names, pairs, finish


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('esm_json', nargs='+', help='Morrowind.json [Tribunal.json Bloodmoon.json]')
    ap.add_argument('--out', default='data')
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # ---- origin of the journals (Tribunal / Bloodmoon options) ------------
    origins = scan_origins(args.esm_json)
    if origins:
        dump_yaml(out / 'quest_sources.yaml', dict(sorted(origins.items())))
        counts = {o: sum(1 for x in origins.values() if x == o) for o in sorted(set(origins.values()))}
        print('quest origins: ' + ', '.join(f'{n} {o}' for o, n in counts.items()) + ' -> quest_sources.yaml')
    elif len(args.esm_json) > 1:
        print('WARNING: no journal defined by an expansion found '
              '(the JSON file names must contain "tribunal" / "bloodmoon" / "tr_mainland" / "cyr_main")')

    # ---- factions ---------------------------------------------------------
    factions, seen = [], set()
    for r in load_records(args.esm_json):
        if r.get('type') == 'Faction' and r.get('id') not in seen:
            seen.add(r.get('id'))
            factions.append({'id': r.get('id'), 'name': r.get('name') or r.get('id')})
    dump_yaml(out / 'factions.yaml', factions)
    print(f'factions: {len(factions)}')

    # ---- quests (stable IDs) ---------------------------------------------
    names, pairs, _finish = scan_quests(args.esm_json)
    overrides = load_overrides(out / 'quest_groups_override.yaml')

    quests = load_yaml(out / 'quests.yaml')
    have = {(str(q['trigger']['quest']).lower(), int(q['trigger']['stage'])) for q in quests}
    nxt = next_id_factory([q['id'] for q in quests], STAGE_BASE, STAGE_LIMIT)
    n_before = len(quests)
    n_tr_skipped = 0
    for qid in sorted(pairs):
        for stage in sorted(pairs[qid]):
            if (qid, stage) in have:
                continue
            display = names[qid]
            # quests.yaml (one row per stage) is a legacy file used by neither the apworld nor
            # the mod. Tamriel Rebuilt has too many stages for its 10000-ID range: skipped.
            if classify(display, overrides) in TR_GROUPS + PC_GROUPS:
                n_tr_skipped += 1
                continue
            quests.append({
                'id': nxt(),
                'name': f'{display} (stage {stage})',
                'category': 'quest',
                'trigger': {'quest': display, 'stage': stage},
                'group': classify(display, overrides),
                'region': 'Seyda Neen',
            })
    dump_yaml(out / 'quests.yaml', quests)
    print(f'quests (stages): {len(quests)} (+{len(quests) - n_before}); {n_tr_skipped} Tamriel Rebuilt stages skipped (unused)')

    comps = load_yaml(out / 'quest_completions.yaml')
    name_map_path = out / 'quest_names.yaml'
    name_map = load_names(name_map_path if name_map_path.exists() else None)
    have_c = {str(c['trigger']['quest']).lower() for c in comps}
    nxt = next_id_factory([c['id'] for c in comps], COMPLETE_BASE, COMPLETE_LIMIT)
    new_c = []
    for qid in sorted(pairs):
        if qid in have_c:
            continue
        display = names[qid]
        comps.append({
            'id': nxt(),
            'name': quest_name(display, name_map),
            'category': 'quest_complete',
            'trigger': {'quest': display},
            'group': classify(display, overrides),
            'region': 'Seyda Neen',
        })
        new_c.append(display)
    # Archipelago locations carry the readable quest name, not the journal
    # ID. Homonyms (several IDs from the same UESP page) are suffixed to stay
    # unique.
    mapped = unique_names(comps, name_map)
    for c in comps:
        c['name'] = mapped[str(c['trigger']['quest']).lower()]
    dump_yaml(out / 'quest_completions.yaml', comps)
    print(f'quest completions: {len(comps)} (+{len(new_c)})')
    if new_c:
        print('new quests:', ', '.join(new_c))
    print("Next, run: python tools/classify_quests.py  (group report)")


if __name__ == '__main__':
    main()
