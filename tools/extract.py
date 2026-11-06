#!/usr/bin/env python3
"""Extraction ESM -> YAML (quetes et factions ; plus d'exploration).

Usage:
  tes3conv Morrowind.esm morrowind.json
  tes3conv Tribunal.esm  tribunal.json     # optionnel
  tes3conv Bloodmoon.esm bloodmoon.json    # optionnel
  python tools/extract.py morrowind.json [tribunal.json bloodmoon.json] --out data/

Corrections :
  * les appels Journal SANS guillemets (`Journal MG_Apprentice 10`) sont
    maintenant detectes (avant : seuls les appels avec guillemets, d'ou les
    guildes / maisons / Morag Tong / culte etc. manquants) ;
  * les identifiants de quete sont valides contre les dialogues de type
    Journal de l'ESM (plus de faux positifs) ;
  * les IDs de locations sont STABLES : les entrees deja presentes dans
    data/*.yaml gardent leur ID, les nouvelles recoivent max+1. Les seeds et
    les tables Lua existantes restent donc coherentes.
"""
import argparse
import json
import pathlib
import re

import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quest_groups import classify, load_overrides  # noqa: E402

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
            raise SystemExit(f'plage d\'IDs epuisee ({base}-{limit})')
        return cur
    return nxt


def load_records(paths):
    for p in paths:
        with open(p, encoding='utf-8') as f:
            for r in json.load(f):
                yield r


def scan_quests(paths):
    """Retourne (journal_ids, pairs, finish) :
    journal_ids : {lower: nom affiche} des dialogues Journal
    pairs       : {lower: set(stages)} trouves dans les scripts/resultats
    finish      : {lower: set(stages)} marques 'quest_finish' dans les infos Journal
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
            print(f'ignores (pas des dialogues Journal) : {len(dropped)} -> {dropped[:10]}...')
        pairs = {q: s for q, s in pairs.items() if q in journal_ids}
        names = {q: journal_ids[q] for q in pairs}
    else:
        print('ATTENTION : aucun dialogue Journal trouve, pas de validation des IDs de quete')
        names = pairs_names
    return names, pairs, finish


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('esm_json', nargs='+', help='Morrowind.json [Tribunal.json Bloodmoon.json]')
    ap.add_argument('--out', default='data')
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # ---- factions ---------------------------------------------------------
    factions, seen = [], set()
    for r in load_records(args.esm_json):
        if r.get('type') == 'Faction' and r.get('id') not in seen:
            seen.add(r.get('id'))
            factions.append({'id': r.get('id'), 'name': r.get('name') or r.get('id')})
    dump_yaml(out / 'factions.yaml', factions)
    print(f'factions: {len(factions)}')

    # ---- quetes (IDs stables) --------------------------------------------
    names, pairs, _finish = scan_quests(args.esm_json)
    overrides = load_overrides(out / 'quest_groups_override.yaml')

    quests = load_yaml(out / 'quests.yaml')
    have = {(str(q['trigger']['quest']).lower(), int(q['trigger']['stage'])) for q in quests}
    nxt = next_id_factory([q['id'] for q in quests], STAGE_BASE, STAGE_LIMIT)
    n_before = len(quests)
    for qid in sorted(pairs):
        for stage in sorted(pairs[qid]):
            if (qid, stage) in have:
                continue
            display = names[qid]
            quests.append({
                'id': nxt(),
                'name': f'{display} (stage {stage})',
                'category': 'quest',
                'trigger': {'quest': display, 'stage': stage},
                'group': classify(display, overrides),
                'region': 'Seyda Neen',
            })
    dump_yaml(out / 'quests.yaml', quests)
    print(f'quests (stages): {len(quests)} (+{len(quests) - n_before})')

    comps = load_yaml(out / 'quest_completions.yaml')
    have_c = {str(c['trigger']['quest']).lower() for c in comps}
    nxt = next_id_factory([c['id'] for c in comps], COMPLETE_BASE, COMPLETE_LIMIT)
    new_c = []
    for qid in sorted(pairs):
        if qid in have_c:
            continue
        display = names[qid]
        comps.append({
            'id': nxt(),
            'name': f'{display} (complete)',
            'category': 'quest_complete',
            'trigger': {'quest': display},
            'group': classify(display, overrides),
            'region': 'Seyda Neen',
        })
        new_c.append(display)
    dump_yaml(out / 'quest_completions.yaml', comps)
    print(f'quest completions: {len(comps)} (+{len(new_c)})')
    if new_c:
        print('nouvelles quetes :', ', '.join(new_c))
    print("Lance ensuite : python tools/classify_quests.py  (rapport des groupes)")


if __name__ == '__main__':
    main()
