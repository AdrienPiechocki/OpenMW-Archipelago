#!/usr/bin/env python3
"""Noms lisibles des quetes, pour les locations Archipelago et les logs.

Morrowind ne stocke que des IDs de journal (`A1_10_MehraMilo`, `MS_FargothRing`,
...). Les noms affiches viennent des pages de quete UESP, mises en cache dans
`data/quest_names.yaml`. Les quetes sans page connue recoivent un nom deduit de
leur ID (prefixe de faction retire, camelCase separe).

Usage :
  python tools/quest_names.py                       # verifie data/quest_completions.yaml
  python tools/quest_names.py --write               # renomme les locations
  python tools/quest_names.py --write --file data/quest_completions.yaml
"""
import argparse
import collections
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_MAP = ROOT / 'data' / 'quest_names.yaml'

# Prefixes de journal de Morrowind.esm (faction / chapitre / quete).
PREFIXES = {
    'a1', 'a2', 'a3',
    'b1', 'b2', 'b2a', 'b2b', 'b2c', 'b3', 'b4', 'b5', 'b6', 'b7', 'b8',
    'c0', 'c1', 'c2', 'c3',
    'ms', 'mv', 'mt', 'fg', 'mg', 'tg', 'hh', 'hr', 'ht', 'ic', 'il',
    'tt', 'eb', 'da', 'va', 'cx', 'blades', 'town', 'romance',
}
# Morceaux de code isoles (MT_S_*).
CODE_WORDS = {'s'}

# Repli pour les rares quetes sans page UESP (ou dont la page ne donne pas l'ID).
FALLBACK = {
    'a2_1_supplies': 'Supplies',
    'a2_1_supplies2': 'Supplies 2',
    'b1_urshilakukill': 'Urshilaku Kill',
    'book_history': 'Book History',
    'book_onmorrowind': 'Book On Morrowind',
    'fast_eddie': 'Fast Eddie',
    'hospitality_papers': 'Hospitality Papers',
    'ic0_akatosh_token': 'Akatosh Token',
    'ic0_imperialcult': 'Imperial Cult',
    'ic0_maran_token': 'Maran Token',
    'ic0_septim_token': 'Septim Token',
    'ic0_stendarr_token': 'Stendarr Token',
    'ic_guide': 'Imperial Cult Guide',
    'il_blueprints': 'Blueprints',
    'ms_propylon': 'Propylon',
    'ms_ragruzgob': "Ra'Gruzgob",
    'rules_blades': 'Rules: Blades',
    'rules_fighters': 'Rules: Fighters Guild',
    'rules_hlaalu': 'Rules: Hlaalu',
    'rules_legion': 'Rules: Imperial Legion',
    'rules_mages': 'Rules: Mages Guild',
    'rules_morag': 'Rules: Morag Tong',
    'rules_redoran': 'Rules: Redoran',
    'rules_telvanni': 'Rules: Telvanni',
    'rules_temple': 'Rules: Temple',
    'rules_thieves': 'Rules: Thieves Guild',
}


def load_names(path=None):
    """Charge {id_de_journal_minuscule: nom_lisible}."""
    p = pathlib.Path(path or DEFAULT_MAP)
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    return {str(k).lower(): str(v) for k, v in data.items()}


def _is_code_token(token):
    t = token.strip()
    if not t:
        return True
    low = t.lower()
    if low in PREFIXES or low in CODE_WORDS:
        return True
    if re.fullmatch(r'\d+', t):
        return True
    # A1, B2a, IC2, IC30... (mais pas un mot comme Supplies2)
    if len(t) <= 5 and re.fullmatch(r'[A-Za-z]+\d+[A-Za-z]?', t):
        return True
    # MT, MS, IC...
    if len(t) <= 2 and t.isalpha() and t.isupper():
        return True
    return False


def _split_words(text):
    # camelCase, sigles, lettres/chiffres (BackDoor1 -> Back Door 1)
    text = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', text)
    text = re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', text)
    text = re.sub(r'(?<=[A-Za-z])(?=\d)', ' ', text)
    text = re.sub(r'(?<=\d)(?=[A-Za-z])', ' ', text)
    return [w for w in re.split(r'\s+', text) if w]


def _cap(word):
    if not word:
        return word
    if word.isupper() and len(word) > 2:
        return word.capitalize()
    return word[:1].upper() + word[1:]


def derive_name(qid):
    """Nom de repli deduit de l'ID (sans prefixe de faction ni code)."""
    qid = str(qid)
    key = qid.lower()
    if key in FALLBACK:
        return FALLBACK[key]

    failed = key.endswith('_not')
    raw = qid[:-4] if failed else qid
    toks = re.split(r'[_\-]+', raw)
    while toks and _is_code_token(toks[0]):
        toks.pop(0)
    if not toks:
        toks = [raw]

    # A1_7HuleeyaInformant : le 7 colle au nom.
    toks[0] = re.sub(r'^\d+', '', toks[0]) or toks[0]
    words = [_cap(w) for w in _split_words(' '.join(toks))]
    name = ' '.join(words).strip()
    if failed:
        name = (name + ' (failed)').strip()
    return name or qid


def quest_name(qid, names=None):
    """Nom lisible d'une quete : page UESP si connue, sinon ID derive."""
    names = names if names is not None else load_names()
    key = str(qid).lower()
    return names.get(key) or derive_name(qid)


def _qualifier(qid, base, names):
    """Detail qui distingue une quete d'une autre portant le meme nom."""
    # L'ID est plus precis que le titre UESP quand plusieurs IDs partagent une
    # meme page (sous-quetes, variantes, etc.).
    derived = derive_name(qid)
    # On retire les mots deja presents dans le nom commun. Les mots d'une
    # lettre sont conserves : ils distinguent souvent deux variantes (A/B).
    base_words = {
        w.lower() for w in re.findall(r"[A-Za-z0-9']+", base) if len(w) > 1
    }
    words = [
        w for w in re.findall(r"[A-Za-z0-9']+", derived)
        if w.lower() not in base_words
    ]
    return ' '.join(words).strip()


def unique_names(rows, names=None):
    """{id_de_journal: nom_unique} pour des lignes de location.

    `rows` : dicts avec `trigger.quest` (ou `quest`) et `group`.
    Les homonymes (plusieurs IDs d'une meme page UESP) recoivent un suffixe
    lisible, par exemple « Sleepers Awake - Alvura ».
    """
    names = names if names is not None else load_names()
    entries = []
    for r in rows:
        trigger = r.get('trigger') or {}
        qid = str(trigger.get('quest') or r.get('quest') or '')
        if qid:
            entries.append((qid, str(r.get('group') or 'misc')))

    bases = {qid: quest_name(qid, names) for qid, _ in entries}
    by_base = collections.defaultdict(list)
    for qid, group in entries:
        by_base[bases[qid]].append((qid, group))

    out = {}
    used = set()
    for base in sorted(by_base):
        items = by_base[base]
        if len(items) == 1:
            qid = items[0][0]
            out[qid.lower()] = base
            used.add(base)
            continue

        # Plusieurs IDs partagent le meme titre UESP : suffixe distinctif.
        seen = collections.Counter()
        for qid, _group in items:
            suffix = _qualifier(qid, base, names) or 'complete'
            seen[suffix.lower()] += 1
            if seen[suffix.lower()] > 1:
                suffix = f'{suffix} {seen[suffix.lower()]}'
            # Pas de parentheses : le nom est deja affiche entre parentheses
            # dans les notifications de check.
            name = f'{base} - {suffix}'
            n = 2
            while name in used:
                name = f'{base} - {suffix} {n}'
                n += 1
            out[qid.lower()] = name
            used.add(name)
    return out


def rewrite_completions(path, names=None):
    """Renomme toutes les entrees de data/quest_completions.yaml."""
    p = pathlib.Path(path)
    rows = yaml.safe_load(p.read_text(encoding='utf-8')) or []
    mapped = unique_names(rows, names)
    for row in rows:
        qid = str((row.get('trigger') or {}).get('quest') or row.get('quest') or '')
        if qid:
            row['name'] = mapped[qid.lower()]
    p.write_text(
        yaml.safe_dump(rows, sort_keys=False, allow_unicode=True),
        encoding='utf-8',
    )
    return mapped


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--file', default='data/quest_completions.yaml')
    ap.add_argument('--map', default=None, help='table des noms (defaut: data/quest_names.yaml)')
    ap.add_argument('--write', action='store_true', help='reecrit les noms dans --file')
    args = ap.parse_args()

    names = load_names(args.map)
    p = pathlib.Path(args.file)
    rows = yaml.safe_load(p.read_text(encoding='utf-8')) or []
    mapped = unique_names(rows, names)
    report = collections.Counter(mapped.values())
    dupes = {n: c for n, c in report.items() if c > 1}
    if dupes:
        raise SystemExit(f'noms encore en double : {dupes}')
    print(f'{len(mapped)} locations, {len(report)} noms uniques')
    if args.write:
        rewrite_completions(p, names)
        print(f'noms ecrits dans {p}')


if __name__ == '__main__':
    main()
