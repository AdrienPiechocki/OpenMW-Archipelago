#!/usr/bin/env python3
"""Classification of quests by group (UESP categories).

Groups: main, hlaalu, redoran, telvanni, fighters_guild, mages_guild,
thieves_guild, imperial_legion, imperial_cult, temple, morag_tong, vampire,
daedric, east_empire, faction_rules, non_quest, misc, plus the
expansion groups <expansion>_<category> (tribunal_main, tribunal_side,
bloodmoon_main, bloodmoon_side), the Tamriel Rebuilt groups (tr_main, tr_side,
tr_daedric, tr_<faction>) and east_empire_company (the only Bloodmoon
faction: goal group of the `faction` option).

Only 'misc' (Miscellaneous) quests give checks (Archipelago locations), plus
the expansion quests whose group option is enabled (tribunal_main_quest,
tribunal_side_quests, bloodmoon_*); east_empire_company gives checks when it is
the chosen `faction`.
The Blades quests (blades_*, Caius Cosades' agents) are counted in the 'main'
group: filler checks of the main quest, only active if the main quest goal is
selected.
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
    ('main',            r'^((a[1-3]|b[1-8][a-z]?|c[0-3])[_ -]|blades_)'),
    ('hlaalu',          r'^hh_'),
    ('redoran',         r'^hr_'),
    ('telvanni',        r'^ht_'),
    ('fighters_guild',  r'^fg_'),
    ('mages_guild',     r'^mg_'),
    ('thieves_guild',   r'^tg_'),
    ('imperial_legion', r'^il_'),
    ('imperial_cult',   r'^ic(\d+)?_'),   # ic_*, but also ic0_ to ic30_
    ('non_quest',       r'^(book|romance)_'),   # not real quests
    ('faction_rules',   r'^rules_'),
    ('temple',          r'^tt_'),
    ('morag_tong',      r'^mt_'),
    ('vampire',         r'^va_'),
    ('daedric',         r'^da_'),
    ('tamriel_rebuilt', r'^tr_m\d+[a-z]?_'),   # TR journals (TR_m3_..): BEFORE the Tribunal rule
    ('tribunal',        r'^tr_'),
    ('bloodmoon',       r'^bm_'),
]
PREFIX_RULES = [(g, re.compile(p)) for g, p in PREFIX_RULES]

# Tamriel Rebuilt (TR_Mainland.esm). Keep in sync with apworld/.../options.py.
TR_FACTION_KEYS = (
    'hlaalu', 'redoran', 'telvanni', 'indoril',
    'fighters_guild', 'mages_guild', 'thieves_guild',
    'imperial_cult', 'imperial_legion', 'temple', 'morag_tong',
    'ja_natta_syndicate', 'east_empire_company',
)
TR_GROUPS = ('tr_main', 'tr_side', 'tr_daedric') + tuple(f'tr_{k}' for k in TR_FACTION_KEYS)
# Faction token of a TR journal id (TR_m<N>_[<place>_]<TOKEN>_...). CONFIRMED on UESP:
# hh (TR_m4_HH_Ulvo4), ht (TR_m2_HT_Vaerin_q2), tt (TR_m3_TT_Lloris1), jns (TR_m7_Ns_JNS_7),
# eec (TR_m1_EEC_Lora / TR_m3_EEC_*, the East Empire Company questline).
# The others follow the same naming but are NOT confirmed: check with tools/list_tr.py.
# data/tr_categories.yaml (faction_tokens) completes / overrides this table.
DEFAULT_TR_TOKENS = {
    'hh': 'hlaalu', 'ht': 'telvanni', 'tt': 'temple', 'jns': 'ja_natta_syndicate',
    'hr': 'redoran', 'fg': 'fighters_guild', 'mg': 'mages_guild', 'tg': 'thieves_guild',
    'il': 'imperial_legion', 'ic': 'imperial_cult', 'mt': 'morag_tong',
    'eec': 'east_empire_company',
}
# Faction tokens followed by a number and an optional variant letter:
# IC1, MG01, TG1, MG07a (the vanilla convention is ^ic(\d+)?_).
TR_NUMBERED_TOKEN = re.compile(r'^([a-z]+)\d+[a-z]?$')
# TR vampire quests: TR_m4_Bal_* / Bal0..Bal5 and TR_m4_VA_* -> 'vampire',
# like the vanilla va_* journals (ignored: neither goal nor check).
TR_VAMPIRE = re.compile(r'^(tr_m4_bal[0-5]?|tr_m4_va)_')

EXPANSIONS = ('tribunal', 'bloodmoon')
ORIGINS = EXPANSIONS + ('tamriel_rebuilt',)
EXPANSION_CATEGORIES = ('main', 'side')
EXPANSION_GROUPS = tuple(f'{e}_{c}' for e in EXPANSIONS for c in EXPANSION_CATEGORIES)
VALID_GROUPS = ({g for g, _ in PREFIX_RULES} | {'misc', 'east_empire_company'} | set(EXPANSIONS) | set(EXPANSION_GROUPS)
                | set(TR_GROUPS) | {'tamriel_rebuilt'})

_DATA = pathlib.Path(__file__).resolve().parent.parent / 'data'
DEFAULT_OVERRIDES = _DATA / 'quest_groups_override.yaml'
DEFAULT_CATEGORIES = _DATA / 'expansion_categories.yaml'
DEFAULT_TR_CATEGORIES = _DATA / 'tr_categories.yaml'


def load_tr_categories(path=None):
    """data/tr_categories.yaml: {'main': ids, 'main_prefixes': (...), 'daedric': ids,
    'daedric_prefixes': (...), 'tokens': {token: faction key}} (lowercase)."""
    p = pathlib.Path(path or DEFAULT_TR_CATEGORIES)
    d = (yaml.safe_load(p.read_text(encoding='utf-8')) or {}) if p.exists() else {}
    tokens = dict(DEFAULT_TR_TOKENS)
    for tok, key in (d.get('faction_tokens') or {}).items():
        if key not in TR_FACTION_KEYS:
            raise SystemExit(f'unknown faction in {p}: {tok}: {key} (valid: {list(TR_FACTION_KEYS)})')
        tokens[str(tok).lower()] = key
    return {
        'main': {str(q).lower() for q in (d.get('main') or [])},
        'main_prefixes': tuple(str(x).lower() for x in (d.get('main_prefixes') or [])),
        'daedric': {str(q).lower() for q in (d.get('daedric') or [])},
        'daedric_prefixes': tuple(str(x).lower() for x in (d.get('daedric_prefixes') or [])),
        'tokens': tokens,
    }


def tr_group(qid, tr_cats=None):
    """Group of a Tamriel Rebuilt journal: tr_main, tr_daedric, tr_<faction> or tr_side."""
    q = str(qid).strip().lower()
    c = tr_cats if tr_cats is not None else load_tr_categories()
    if q in c['main'] or (c['main_prefixes'] and q.startswith(c['main_prefixes'])):
        return 'tr_main'
    if q in c['daedric'] or (c['daedric_prefixes'] and q.startswith(c['daedric_prefixes'])):
        return 'tr_daedric'
    if TR_VAMPIRE.match(q):            # TR_m4_Bal* / TR_m4_VA_* (see the yaml)
        return 'vampire'
    # TR_m<N>_<TOKEN>_... or TR_m<N>_<place>_<TOKEN>_...: the token is one of the 2 parts after mN.
    # Faction tokens may carry a number and an optional variant letter: IC1, MG01, TG1, MG07a.
    for part in q.split('_')[2:4]:
        key = c['tokens'].get(part)
        if key is None:
            m = TR_NUMBERED_TOKEN.match(part)
            if m:
                key = c['tokens'].get(m.group(1))
        if key:
            return f'tr_{key}'
    return 'tr_side'


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
            if v not in ORIGINS:
                raise SystemExit(f'unknown origin in {src}: {k}: {v} (valid: {list(ORIGINS)})')
            out[str(k).lower()] = v
    if p.exists():
        d = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
        for k, v in d.items():
            if v not in VALID_GROUPS:
                raise SystemExit(f'unknown group in {p}: {k}: {v} (valid: {sorted(VALID_GROUPS)})')
            out[str(k).lower()] = v
    return out


def classify(qid, overrides=None, cats=None, tr_cats=None):
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
    if group == 'tamriel_rebuilt':       # origin only -> faction / main / daedric / side
        return tr_group(q, tr_cats)
    return group or 'misc'
