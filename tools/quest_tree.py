#!/usr/bin/env python3
"""Shared model for the canonical quest tree (data/quest_tree.json).

The UESP scraper (tools/scrape_uesp_quest_tree.py) produces a *content* tree:

    origin -> UESP quest line -> quest page -> ids / completion_stages /
                                             region / triggers / needs_item / rewards

This module adds the project identity on top of it.  The canonical tree is the
single source of truth for:

  * the faction / group of every journal      (`groups`)
  * the successful AND failing ending stages  (`completion_stages`, `fail`)
  * the Archipelago location of every journal (`loc_ids`, `loc_names`)
  * the progression items and unique rewards  (`needs_item_meta`, `rewards_meta`)

Everything downstream (data/*.yaml, mod/scripts/ap/*.lua, the apworld data) is
generated from that tree by tools/rebase_quest_tree.py + tools/gen_data_from_tree.py.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quest_groups import classify, load_overrides  # noqa: E402

# UESP quest line -> Archipelago group.
#
# Only *faction* lines are listed.  A line that is not listed is a location /
# miscellaneous line (Morrowind regions, TR towns, "integrations", ...): its
# journals keep the prefix classification of tools/quest_groups.py, which maps
# them to misc / tr_side (or to the TR faction token of the journal id).
#
# A manual entry of data/quest_groups_override.yaml always wins.
LINE_GROUPS = {
    'Morrowind': {
        'main_quest': 'main',
        'blades': 'main',                 # Blades quests are main-quest filler
        'daedric': 'daedric',
        'fighters_guild': 'fighters_guild',
        'house_hlaalu': 'hlaalu',
        'house_redoran': 'redoran',
        'house_telvanni': 'telvanni',
        'imperial_cult': 'imperial_cult',
        'imperial_legion': 'imperial_legion',
        'mages_guild': 'mages_guild',
        'morag_tong': 'morag_tong',
        'thieves_guild': 'thieves_guild',
        'tribunal_temple': 'temple',
        'vampire': 'vampire',
    },
    'Tribunal': {
        'main_quest': 'tribunal_main',
        'side_quest': 'tribunal_side',
    },
    'Bloodmoon': {
        'main_quest': 'bloodmoon_main',
        'side_quest': 'bloodmoon_side',
        'east_empire_company': 'east_empire_company',
    },
    'Tamriel Rebuilt': {
        'main_quest': 'tr_main',
        'daedric': 'tr_daedric',
        'east_empire_company': 'tr_east_empire_company',
        'fighters_guild': 'tr_fighters_guild',
        'great_house_telvanni': 'tr_telvanni',
        'house_hlaalu': 'tr_hlaalu',
        'house_indoril': 'tr_indoril',
        'house_redoran': 'tr_redoran',
        'imperial_cult': 'tr_imperial_cult',
        'imperial_legion': 'tr_imperial_legion',
        'ja_natta_syndicate': 'tr_ja_natta_syndicate',
        'mages_guild': 'tr_mages_guild',
        'morag_tong': 'tr_morag_tong',
        'thieves_guild': 'tr_thieves_guild',
        'tribunal_temple': 'tr_temple',
        'vampire': 'vampire',
    },
}

ORIGIN_KEYS = {
    'morrowind': 'Morrowind',
    'tribunal': 'Tribunal',
    'bloodmoon': 'Bloodmoon',
    'tamriel_rebuilt': 'Tamriel Rebuilt',
}

# Lines used for journals that the UESP tree does not contain (the scraper only
# knows quest pages with a "Quest Stages" table).  Kept out of LINE_GROUPS: the
# group of those journals comes from the prefix classification.
ESM_ONLY_LINE = '_esm_only'


def iter_pages(tree):
    """Yield (origin, line, page name, page dict), skipping metadata keys."""
    for origin, lines in tree.items():
        if str(origin).startswith('_') or not isinstance(lines, dict):
            continue
        for line, pages in lines.items():
            # `_esm_only` holds the journals known to the ESM but absent from
            # UESP: they are regular pages (other `_` keys are metadata).
            if (str(line).startswith('_') and line != ESM_ONLY_LINE) or not isinstance(pages, dict):
                continue
            for name, page in pages.items():
                if isinstance(page, dict):
                    yield origin, line, name, page


def resolve_group(origin, line, journal, overrides=None):
    """Group of a journal: manual override > faction line > journal prefix."""
    q = str(journal).strip().lower()
    overrides = overrides if overrides is not None else {}
    if q in overrides:
        return classify(q, overrides=overrides)
    group = LINE_GROUPS.get(origin, {}).get(line)
    if group:
        return group
    return classify(q, overrides=overrides)


def journal_keys(page):
    """Every journal id mentioned by a page (lowercase, insertion order)."""
    seen = []
    for key in ('ids', 'completion_stages', 'fail', 'groups', 'loc_ids'):
        value = page.get(key) or {}
        if isinstance(value, dict):
            value = value.keys()
        for jid in value:
            j = str(jid).lower()
            if j not in seen:
                seen.append(j)
    return seen


def is_canonical(tree):
    """True if the tree carries the project identity (groups / loc_ids)."""
    for _origin, _line, _name, page in iter_pages(tree):
        if 'groups' in page or 'loc_ids' in page:
            return True
    return False


def load_tree(path):
    import json
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))


def save_tree(tree, path):
    import json
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(tree, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def load_overrides_safe(data_dir='data'):
    """Overrides next to the data directory (quest_sources.yaml is read too)."""
    path = pathlib.Path(data_dir) / 'quest_groups_override.yaml'
    if not path.exists():
        return {}
    return load_overrides(path)
