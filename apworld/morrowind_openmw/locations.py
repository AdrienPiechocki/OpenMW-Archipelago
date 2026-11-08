import os, sys
try:
    import yaml
except Exception:
    yaml = None

from BaseClasses import Location
from typing import NamedTuple, Callable, Dict
from .options import (MorrowindOptions, selected_goals, goal_of_group, selected_expansion_groups,
                      selected_tr_groups, EXPANSION_GROUPS, TR_GROUPS, quest_rewards_enabled, group_active)


class MorrowindLocation(Location):
    game = "Morrowind OpenMW"


class MorrowindLocationData(NamedTuple):
    region: str = "Seyda Neen"
    code: int | None = None
    can_create: Callable[[MorrowindOptions], bool] = lambda options: True
    locked_item: str | None = None
    group: str = "misc"
    # True: no important item (progression / useful) in this location.
    excluded: Callable[[MorrowindOptions], bool] = lambda options: False


BASE_LOC = 7700000

location_table: Dict[str, MorrowindLocationData] = {}

# Quest completion (one check per quest)
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
# Quests that can fail (data/quest_finals.yaml, `fail` field): their check can
# become impossible, so never put an important item on them.
# Mutually exclusive quests (data/quest_exclusive.yaml) are NO LONGER risky:
# completing any quest of a group validates the whole group (the mod sends all
# the checks of the group), so their locations can hold progression items.
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
no_completion_quests = set()
if yaml is not None and _qf_text:
    for _q in yaml.safe_load(_qf_text) or []:
        _qid = str(_q.get('quest', '')).lower()
        if _q.get('fail') and not _q.get('fail_only'):
            risky_quests.add(_qid)
        # Failure-only journal (or no completion stage at all): the check can
        # never fire, so it must not become a dead location.
        if _q.get('fail_only') or int(_q.get('stage') or 0) <= 0:
            no_completion_quests.add(_qid)


def _goal_quest_can_create(options, g):
    return goal_of_group(g) in selected_goals(options)


def _goal_quest_excluded(options, risky):
    # Only quests without a failure branch can hold progression.
    return risky


if yaml is not None and _qc_text:
    _qc = yaml.safe_load(_qc_text) or []
    for q in _qc:
        name = q.get('name')
        code = q.get('id')
        region = q.get('region') or 'Seyda Neen'
        group = q.get('group', 'misc')
        qid = str((q.get('trigger') or {}).get('quest', '')).lower()
        if qid in no_completion_quests:
            # Failure-only journal / no successful stage: no check, no location.
            continue
        risky = qid in risky_quests
        if group == 'misc':
            # A misc quest with a failure branch can make its check impossible:
            # never put an important item on it (otherwise the seed is unbeatable).
            location_table[name] = MorrowindLocationData(
                region=region, code=code, group=group,
                can_create=lambda options: True,
                excluded=lambda options, r=risky: r,
            )
        elif group in EXPANSION_GROUPS:
            # Tribunal / Bloodmoon quests (groups tribunal_main,
            # tribunal_side, bloodmoon_main, bloodmoon_side): checks only if the option of their
            # group is enabled; never gating. Same safety rule as misc quests:
            # a quest with a failure branch never holds an important item.
            location_table[name] = MorrowindLocationData(
                region=region, code=code, group=group,
                can_create=lambda options, g=group: g in selected_expansion_groups(options),
                excluded=lambda options, r=risky: r,
            )
        elif group in TR_GROUPS:
            # Tamriel Rebuilt quests (tr_main, tr_side, tr_daedric, tr_<faction>):
            # created only if their group is enabled by the tamriel_rebuilt_*
            # options (selected_tr_groups also checks the matching goal).
            # Same safety rule: a quest with a failure branch never holds an
            # important item.
            location_table[name] = MorrowindLocationData(
                region=region, code=code, group=group,
                can_create=lambda options, g=group: g in selected_tr_groups(options),
                excluded=lambda options, r=risky: r,
            )
        else:
            location_table[name] = MorrowindLocationData(
                region=region, code=code, group=group,
                can_create=lambda options, g=group: _goal_quest_can_create(options, g),
                excluded=lambda options, r=risky: _goal_quest_excluded(options, r),
            )


# Quest rewards (unique items): one location per reward, sent when the vanilla
# reward would reach the player (data/quest_rewards.yaml). Same group (and
# therefore same logic, see rules.py) and same region as the quest itself.
# Created only if the quest_rewards option is on and the group is enabled.
_qr_text = None
try:
    from importlib import resources as _res
    _qr_text = _res.files(__package__).joinpath('data', 'quest_rewards.yaml').read_text(encoding='utf-8')
except Exception:
    _p = os.path.join(os.path.dirname(__file__), 'data', 'quest_rewards.yaml')
    if os.path.exists(_p):
        with open(_p, encoding='utf-8') as f:
            _qr_text = f.read()

if yaml is not None and _qr_text:
    for _r in yaml.safe_load(_qr_text) or []:
        _qid = str(_r['quest']).lower()
        if _qid in no_completion_quests:
            continue
        # Location names must be unique: item name + quest.
        location_table[f"{_r['name']} @ {_qid}"] = MorrowindLocationData(
            region=_r.get('region') or 'Seyda Neen',
            code=_r['loc_id'],
            group=_r['group'],
            can_create=lambda options, g=_r['group']: quest_rewards_enabled(options) and group_active(options, g),
            # A quest with a failure branch may never give its reward.
            excluded=lambda options, r=(_qid in risky_quests): r,
        )
