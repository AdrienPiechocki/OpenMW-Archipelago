import os, sys
try:
    import yaml
except Exception:
    yaml = None

from BaseClasses import Location
from typing import NamedTuple, Callable, Dict
from .options import MorrowindOptions, selected_goals, goal_of_group


class MorrowindLocation(Location):
    game = "Morrowind OpenMW"


class MorrowindLocationData(NamedTuple):
    region: str = "Seyda Neen"
    code: int | None = None
    can_create: Callable[[MorrowindOptions], bool] = lambda options: True
    locked_item: str | None = None
    group: str = "misc"
    # True : aucun item important (progression / utile) dans cette location.
    excluded: Callable[[MorrowindOptions], bool] = lambda options: False


BASE_LOC = 7700000

location_table: Dict[str, MorrowindLocationData] = {}

# Completion de quete (un check par quete)
_qc_text = None
try:
    from importlib import resources as _res
    _p = _res.files(__package__).joinpath('data', 'quest_completions.yaml')
    _qc_text = _p.read_text(encoding='utf-8')
except Exception:
    _p = os.path.join(os.path.dirname(__file__), 'data', 'quest_completions.yaml')
    if os.path.exists(_p):
        with open(_p, encoding='utf-8') as f:
            _qc_text = f.read()
# Quetes pouvant echouer / a fins exclusives (data/quest_finals.yaml, champ `fail`) :
# leur check peut devenir impossible, donc jamais d'item important dessus.
_qf_text = None
try:
    from importlib import resources as _res
    _qf_text = _res.files(__package__).joinpath('data', 'quest_finals.yaml').read_text(encoding='utf-8')
except Exception:
    _p = os.path.join(os.path.dirname(__file__), 'data', 'quest_finals.yaml')
    if os.path.exists(_p):
        with open(_p, encoding='utf-8') as f:
            _qf_text = f.read()
risky_quests = set()
if yaml is not None and _qf_text:
    for _q in yaml.safe_load(_qf_text) or []:
        if _q.get('fail'):
            risky_quests.add(str(_q['quest']).lower())


def _goal_quest_can_create(options, g):
    return goal_of_group(g) in selected_goals(options)


def _goal_quest_excluded(options, risky):
    # Seules les quetes sans branche d'echec peuvent contenir de la progression.
    return risky


if yaml is not None and _qc_text:
    _qc = yaml.safe_load(_qc_text) or []
    for q in _qc:
        name = q.get('name')
        code = q.get('id')
        region = q.get('region') or 'Seyda Neen'
        group = q.get('group', 'misc')
        if group == 'misc':
            location_table[name] = MorrowindLocationData(
                region=region, code=code, group=group,
                can_create=lambda options: True,
            )
        else:
            risky = str((q.get('trigger') or {}).get('quest', '')).lower() in risky_quests
            location_table[name] = MorrowindLocationData(
                region=region, code=code, group=group,
                can_create=lambda options, g=group: _goal_quest_can_create(options, g),
                excluded=lambda options, r=risky: _goal_quest_excluded(options, r),
            )
