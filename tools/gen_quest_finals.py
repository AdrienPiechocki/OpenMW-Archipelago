#!/usr/bin/env python3
"""Genere data/quest_finals.yaml : stage de completion par quete.

Le stage de completion par defaut est le plus haut stage Journal (< 150)
trouve dans l'ESM pour la quete (en minuscules). Des overrides et des
stages d'echec corrigent les branches connues.

Usage:
  tes3conv Morrowind.esm morrowind.json
  python tools/gen_quest_finals.py /tmp/morrowind.json --out data/quest_finals.yaml
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

# Stage de completion explicite quand le max brut ne correspond pas a la
# vraie fin "reussie" de la quete.
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
    # Nels Llendo : 90 (refus/attaque), 100 (or), 120 et 130 (baiser) terminent
    # tous la quete ; 140 n'est qu'un suivi a Pelagiad, souvent jamais atteint.
    'mv_3_charming': 90,
}

# Stages qui annulent la completion (branche d'echec).
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
}

PAT_QUOTED = re.compile(r'(?<!Get)Journal\s*,?\s*"([^"]+)"\s*,?\s*(\d+)', re.I)
PAT_BARE = re.compile(r'(?<!Get)Journal\s*,?\s*([A-Za-z_][A-Za-z0-9_\-]*)\s*,?\s*(\d+)', re.I)


def collect_stages(esm_jsons, scripts_path=None):
    stages = collections.defaultdict(set)
    finishes = collections.defaultdict(set)

    def add_text(text):
        if not text:
            return
        for pat in (PAT_QUOTED, PAT_BARE):
            for m in pat.finditer(text):
                stages[m.group(1).strip().lower()].add(int(m.group(2)))

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
                d = rec.get('data') or {}
                if cur_journal and cur_id and rec.get('quest_finish') \
                        and isinstance(d.get('disposition'), int):
                    finishes[cur_id].add(d['disposition'])
            elif t == 'Script':
                add_text(rec.get('script_text') or rec.get('text'))

    if scripts_path:
        with open(scripts_path, encoding='utf-8', errors='replace') as f:
            for line in f:
                add_text(line)

    return stages, finishes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('esm_json', nargs='+')
    ap.add_argument('--scripts', default=None,
                    help='dump texte des scripts (optionnel, ameliore la couverture)')
    ap.add_argument('--qc', default='data/quest_completions.yaml')
    ap.add_argument('--out', default='data/quest_finals.yaml')
    args = ap.parse_args()

    stages, finishes = collect_stages(args.esm_json, args.scripts)

    # Les entrees deja presentes sont conservees telles quelles (stages
    # valides / overrides manuels) ; seules les nouvelles quetes sont calculees.
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
        if qid in existing:
            row = dict(existing[qid])
            row['ids'] = ids[qid]
            row['group'] = classify(qid, overrides)
            rows.append(row)
            continue
        raw = sorted(s for s in stages.get(qid, set()) if s < 150)
        fin = sorted(s for s in finishes.get(qid, set()) if s < 150)
        stage = STAGE_OVERRIDES.get(qid)
        if stage is None:
            stage = fin[-1] if fin else (raw[-1] if raw else 0)
        rows.append({
            'quest': qid,
            'stage': stage,
            'fail': FAIL_STAGES.get(qid, []),
            'ids': ids[qid],
            'group': classify(qid, overrides),
        })
        flag = '' if len(fin) <= 1 else '  <-- plusieurs fins possibles, verifier les branches d\'echec'
        review.append(f'{qid}: stage={stage} finish={fin} stages={raw}{flag}')

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        yaml.safe_dump(rows, f, sort_keys=False, allow_unicode=True)
    print(f'quest finals: {len(rows)} entries -> {out}')
    if review:
        rp = out.with_name('quest_review.txt')
        rp.write_text('\n'.join(review) + '\n', encoding='utf-8')
        print(f'{len(review)} nouvelles quetes, a verifier dans {rp}')


if __name__ == '__main__':
    main()
