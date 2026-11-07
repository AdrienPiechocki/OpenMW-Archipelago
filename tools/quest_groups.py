#!/usr/bin/env python3
"""Classification of quests by group (UESP categories).

Groups: main, hlaalu, redoran, telvanni, fighters_guild, mages_guild,
thieves_guild, imperial_legion, imperial_cult, temple, morag_tong, vampire,
daedric, blades, east_empire, faction_rules, non_quest, misc, plus the
expansion groups <expansion>_<category> (tribunal_main, tribunal_side,
bloodmoon_main, bloodmoon_side) and east_empire_company (the only Bloodmoon
faction: goal group of the `faction` option).

Only 'misc' (Miscellaneous) quests give checks (Archipelago locations), plus
the expansion quests whose group option is enabled (tribunal_main_quest,
tribunal_side_quests, bloodmoon_*); east_empire_company gives checks when it is
the chosen `faction`.
The main, faction and daedric groups are used for goals ('daedric' if the
Daedric Quests option is enabled); 'vampire' is ignored (neither goal nor
check).

The expansion (tribunal / bloodmoon) comes from the ESM that DEFINES the
journal (data/quest_sources.yaml, written by tools/extract.py). The tr_ / bm_
prefixes are only a fallback when that file does not exist. Within an
expansion, data/expansion_categories.yaml decides: main quest, East Empire
Company (Bloodmoon only), else side quest.

Classification is done by journal ID prefix (Morrowind.esm convention).
Exceptions are declared in data/quest_groups_override.yaml
({ 'quest_id': 'group' }).
"""
import pathlib
import re

import yaml

# Order matters: first matching rule.
PREFIX_RULES = [
    ('main',            r'^(a[1-3]|b[1-8][a-z]?|c[0-3])[_ -]'),
    ('hlaalu',          r'^hh_'),
    ('redoran',         r'^hr_'),
    ('telvanni',        r'^ht_'),
    ('fighters_guild',  r'^fg_'),
    ('mages_guild',     r'^mg_'),
    ('thieves_guild',   r'^tg_'),
    ('imperial_legion', r'^il_'),
    ('imperial_cult',   r'^ic(\d+)?_'),   # ic_*, but also ic0_ to ic30_
    ('blades',          r'^blades_'),
    ('east_empire',     r'^eb_'),
    ('non_quest',       r'^(book|romance)_'),   # not real quests
    ('faction_rules',   r'^rules_'),
    ('temple',          r'^tt_'),
    ('morag_tong',      r'^mt_'),
    ('vampire',         r'^va_'),
    ('daedric',         r'^da_'),
    ('tribunal',        r'^tr_'),
    ('bloodmoon',       r'^bm_'),
]
PREFIX_RULES = [(g, re.compile(p)) for g, p in PREFIX_RULES]

EXPANSIONS = ('tribunal', 'bloodmoon')
EXPANSION_CATEGORIES = ('main', 'side')
EXPANSION_GROUPS = tuple(f'{e}_{c}' for e in EXPANSIONS for c in EXPANSION_CATEGORIES)
VALID_GROUPS = ({g for g, _ in PREFIX_RULES} | {'misc', 'east_empire_company'} | set(EXPANSIONS) | set(EXPANSION_GROUPS))

_DATA = pathlib.Path(__file__).resolve().parent.parent / 'data'
DEFAULT_OVERRIDES = _DATA / 'quest_groups_override.yaml'
DEFAULT_CATEGORIES = _DATA / 'expansion_categories.yaml'


def load_categories(path=None):
    """data/expansion_categories.yaml: {'main': {ids}, 'side': {ids},
    'east_empire_company': {ids}, 'eec_prefixes': (prefixes,)} (lowercase)."""
    p = pathlib.Path(path or DEFAULT_CATEGORIES)
    d = (yaml.safe_load(p.read_text(encoding='utf-8')) or {}) if p.exists() else {}
    out = {c: {str(q).lower() for q in (d.get(c) or [])} for c in EXPANSION_CATEGORIES + ('east_empire_company',)}
    out['eec_prefixes'] = tuple(str(x).lower() for x in (d.get('east_empire_company_prefixes') or []))
    return out


def expansion_group(origin, qid, cats=None):
    """Group of a quest DEFINED by the expansion `origin`: 'east_empire_company'
    (the Bloodmoon faction, a goal group of the `faction` option),
    else '<origin>_main' or '<origin>_side'."""
    q = str(qid).strip().lower()
    cats = cats if cats is not None else load_categories()
    if origin == 'bloodmoon' and (q in cats['east_empire_company'] or q.startswith(cats['eec_prefixes'])):
        return 'east_empire_company'
    return f'{origin}_main' if q in cats['main'] else f'{origin}_side'


def load_overrides(path=None):
    """{quest_id: group}: ESM origin (quest_sources.yaml, next to the file)
    first, then the manual exceptions (quest_groups_override.yaml), which win."""
    p = pathlib.Path(path or DEFAULT_OVERRIDES)
    out = {}
    src = p.parent / 'quest_sources.yaml'
    if src.exists():
        d = yaml.safe_load(src.read_text(encoding='utf-8')) or {}
        for k, v in d.items():
            if v not in EXPANSIONS:
                raise SystemExit(f'unknown origin in {src}: {k}: {v} (valid: {list(EXPANSIONS)})')
            out[str(k).lower()] = v
    if p.exists():
        d = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
        for k, v in d.items():
            if v not in VALID_GROUPS:
                raise SystemExit(f'unknown group in {p}: {k}: {v} (valid: {sorted(VALID_GROUPS)})')
            out[str(k).lower()] = v
    return out


def classify(qid, overrides=None, cats=None):
    q = str(qid).strip().lower()
    group = None
    if overrides and q in overrides:
        group = overrides[q]
    else:
        for g, pat in PREFIX_RULES:
            if pat.match(q):
                group = g
                break
    if group in EXPANSIONS:              # origin only -> add the category
        return expansion_group(group, q, cats)
    return group or 'misc'
