#!/usr/bin/env python3
"""Classification of quests by group (UESP categories).

Groups: main, hlaalu, redoran, telvanni, fighters_guild, mages_guild,
thieves_guild, imperial_legion, imperial_cult, temple, morag_tong, vampire,
daedric, blades, east_empire, faction_rules, non_quest, expansion, misc.

Only 'misc' (Miscellaneous) quests give checks (Archipelago locations).
The main, faction and daedric groups are used for goals ('daedric' if the
Daedric Quests option is enabled); 'vampire' and 'expansion' are ignored
(neither goal nor check).

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
    ('expansion',       r'^(tr|bm)_'),
]
PREFIX_RULES = [(g, re.compile(p)) for g, p in PREFIX_RULES]

VALID_GROUPS = {g for g, _ in PREFIX_RULES} | {'misc'}

DEFAULT_OVERRIDES = pathlib.Path(__file__).resolve().parent.parent / 'data' / 'quest_groups_override.yaml'


def load_overrides(path=None):
    p = pathlib.Path(path or DEFAULT_OVERRIDES)
    if not p.exists():
        return {}
    d = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    out = {}
    for k, v in d.items():
        if v not in VALID_GROUPS:
            raise SystemExit(f'unknown group in {p}: {k}: {v} (valid: {sorted(VALID_GROUPS)})')
        out[str(k).lower()] = v
    return out


def classify(qid, overrides=None):
    q = str(qid).strip().lower()
    if overrides and q in overrides:
        return overrides[q]
    for group, pat in PREFIX_RULES:
        if pat.match(q):
            return group
    return 'misc'
