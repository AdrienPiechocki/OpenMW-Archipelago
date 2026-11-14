from BaseClasses import Item, ItemClassification
import os
from typing import NamedTuple, Dict, Callable

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None
from .options import MorrowindOptions, group_enabled, selected_goals, quest_rewards_enabled, group_active


class MorrowindItem(Item):
    game = "Morrowind OpenMW"


class MorrowindItemData(NamedTuple):
    code: int | None = None
    classification: ItemClassification = ItemClassification.filler
    frequency: int = 1
    precollect: int = 0
    can_create: Callable[[MorrowindOptions], bool] = lambda options: True


BASE_ITEM = 7701000


def _traps_enabled(options) -> bool:
    """Trap items are only in the pool if the `traps` option is enabled."""
    t = getattr(options, "traps", None)
    return bool(getattr(t, "value", True if t is None else t))

# Filler: the slots left once the real items are placed are filled by a WEIGHTED draw in this table
# (name: (AP code, weight)), so a seed is not 90% gold. Codes must stay in sync with GIVE in
# mod/scripts/ap/items.lua (tools/check_filler_records.py checks the record ids against the ESMs).
FILLER = {
    "Gold (100)": (BASE_ITEM + 1, 4),
    "Gold (250)": (BASE_ITEM + 5, 1),
    "Healing Potion": (BASE_ITEM + 2, 3),
    "Quality Healing Potion": (BASE_ITEM + 6, 1),
    "Magicka Potion": (BASE_ITEM + 7, 2),
    "Fatigue Potion": (BASE_ITEM + 8, 2),
    "Soul Gem": (BASE_ITEM + 3, 2),
    "Soul Gem (Greater)": (BASE_ITEM + 9, 1),
    "Arrow (30)": (BASE_ITEM + 4, 2),
    "Steel Arrow (30)": (BASE_ITEM + 10, 1),
    "Lockpicks (3)": (BASE_ITEM + 11, 2),
    "Probes (3)": (BASE_ITEM + 12, 1),
    "Bread (5)": (BASE_ITEM + 13, 1),
    "Scrib Jelly (3)": (BASE_ITEM + 14, 1),
    "Comberry Wine": (BASE_ITEM + 15, 1),
    "Local Brew": (BASE_ITEM + 16, 1),
}

# Traps: converted from filler by the `trap_percentage` option (only if `traps` is on).
TRAPS = {
    "Trap: Damage": (BASE_ITEM + 200, 3),
    "Trap: Bounty": (BASE_ITEM + 201, 2),
    "Trap: Summon Scamp": (BASE_ITEM + 202, 3),
    "Trap: Steal Gold": (BASE_ITEM + 203, 3),
    "Trap: Summon Flame Atronach": (BASE_ITEM + 204, 1),
    "Trap: Summon Clannfear": (BASE_ITEM + 205, 1),
    "Trap: Summon Cliff Racers": (BASE_ITEM + 206, 1),
    "Trap: Drain Fatigue": (BASE_ITEM + 207, 2),
    "Trap: Drain Magicka": (BASE_ITEM + 208, 2),
}
FILLER_WEIGHTS = {name: w for name, (_c, w) in FILLER.items()}
TRAP_WEIGHTS = {name: w for name, (_c, w) in TRAPS.items()}

item_table: Dict[str, MorrowindItemData] = {
    # +10 levels: adds the progression of 10 vanilla level-ups.
    # The player sleeps to choose attributes (see mod/scripts/ap/level_up.lua).
    "Level Up (+10)": MorrowindItemData(
        code=BASE_ITEM + 2000, classification=ItemClassification.progression, frequency=4
    ),
}
# frequency=0: never added one by one, only through the weighted draws of create_items.
for _name, (_code, _w) in FILLER.items():
    item_table[_name] = MorrowindItemData(code=_code, classification=ItemClassification.filler, frequency=0)
for _name, (_code, _w) in TRAPS.items():
    item_table[_name] = MorrowindItemData(code=_code, classification=ItemClassification.trap, frequency=0,
                                          can_create=_traps_enabled)

# "<faction> Requirements added": one progression item per faction goal
# (great house / guild / faction). In game it raises the player's attributes
# and skills to the faction's maximum rank requirements (see
# mod/scripts/ap/faction_requirements.lua, ids must stay in sync).
# Replaces the old "Skill: <name>" (+15) items.
FACTION_REQUIREMENTS = {
    # goal key: (item code, faction display name)
    "hlaalu": (BASE_ITEM + 500, "Hlaalu"),
    "redoran": (BASE_ITEM + 501, "Redoran"),
    "telvanni": (BASE_ITEM + 502, "Telvanni"),
    "indoril": (BASE_ITEM + 503, "Indoril"),
    "fighters_guild": (BASE_ITEM + 504, "Fighters Guild"),
    "mages_guild": (BASE_ITEM + 505, "Mages Guild"),
    "thieves_guild": (BASE_ITEM + 506, "Thieves Guild"),
    "imperial_cult": (BASE_ITEM + 507, "Imperial Cult"),
    "imperial_legion": (BASE_ITEM + 508, "Imperial Legion"),
    "temple": (BASE_ITEM + 509, "Temple"),
    "morag_tong": (BASE_ITEM + 510, "Morag Tong"),
    "east_empire_company": (BASE_ITEM + 511, "East Empire Company"),
    "ja_natta_syndicate": (BASE_ITEM + 512, "Ja-Natta Syndicate"),
    "ordinators": (BASE_ITEM + 513, "Ordinators"),
    # Project Cyrodiil (Cyr_Main.esm)
    "kingdom_of_anvil": (BASE_ITEM + 514, "Kingdom of Anvil"),
    "itinerant_priests": (BASE_ITEM + 515, "Itinerant Priests"),
    "cyrodiil_fighters_guild": (BASE_ITEM + 516, "Cyrodiil Fighters Guild"),
    "cyrodiil_mages_guild": (BASE_ITEM + 517, "Cyrodiil Mages Guild"),
    "cyrodiil_thieves_guild": (BASE_ITEM + 518, "Cyrodiil Thieves Guild"),
    # Skyrim: Home of the Nords (Sky_Main.esm)
    "skyrim_fighters_guild": (BASE_ITEM + 519, "Skyrim Fighters Guild"),
    "skyrim_mages_guild": (BASE_ITEM + 520, "Skyrim Mages Guild"),
    "hammerfell_mages_guild": (BASE_ITEM + 521, "Hammerfell Mages Guild"),
    "skyrim_thieves_guild": (BASE_ITEM + 522, "Skyrim Thieves Guild"),
}
FACTION_REQUIREMENT_NAMES = {
    goal: f"{label} Requirements added" for goal, (_code, label) in FACTION_REQUIREMENTS.items()
}

for _goal, (_code, _label) in FACTION_REQUIREMENTS.items():
    item_table[FACTION_REQUIREMENT_NAMES[_goal]] = MorrowindItemData(
        code=_code,
        classification=ItemClassification.progression,
        can_create=lambda options, g=_goal: g in selected_goals(options),
    )


# Quest items per goal: data/quest_items.yaml.
# They are only in the pool if the selected goal matches.
def _load_yaml(filename):
    text = None
    try:
        from importlib import resources as _res
        text = _res.files(__package__).joinpath('data', filename).read_text(encoding='utf-8')
    except Exception:
        _p = os.path.join(os.path.dirname(__file__), 'data', filename)
        if os.path.exists(_p):
            with open(_p, encoding='utf-8') as f:
                text = f.read()
    if yaml is None or not text:
        return []
    return yaml.safe_load(text) or []


quest_items = _load_yaml('quest_items.yaml')
# Locked quests: one progression item per quest (data/quest_locks.yaml).
quest_locks = _load_yaml('quest_locks.yaml')

for _it in quest_items + quest_locks:
    _goal = _it['goal']
    _group = _it.get('group')
    if _goal == 'misc':
        # Miscellaneous quest items: always in the pool, but "useful"
        # (they are not required for victory). Otherwise they would saturate
        # progression locations and make the capacity check fail.
        item_table[_it['name']] = MorrowindItemData(
            code=_it['id'],
            classification=ItemClassification.useful,
            can_create=lambda options: True,
        )
    else:
        # Goal items (main, houses, guilds, factions, daedric):
        # only if the goal is selected, and as progression.
        item_table[_it['name']] = MorrowindItemData(
            code=_it['id'],
            classification=ItemClassification.progression,
            can_create=lambda options, g=_goal, grp=_group: (
                g in selected_goals(options) and group_enabled(options, grp)
            ),
        )


# Quest rewards (unique items): data/quest_rewards.yaml. One useful item per
# reward, only if the quest_rewards option is on and the quest's group is
# enabled in the seed (same condition as the matching location).
quest_rewards = _load_yaml('quest_rewards.yaml')
for _r in quest_rewards:
    item_table[_r['name']] = MorrowindItemData(
        code=_r['item_id'],
        classification=ItemClassification.useful,
        can_create=lambda options, grp=_r['group']: (
            quest_rewards_enabled(options) and group_active(options, grp)
        ),
    )


def quest_item_names(goal_key, options=None):
    """Names of the AP items required for goal `goal_key`: quest items
    + quest unlock items.

    Locks with a `group` (e.g. the TR Daedric princes) are only included
    when that group is enabled in the seed: their item does not exist
    otherwise."""
    locks = quest_locks
    if options is not None:
        locks = [i for i in quest_locks if group_enabled(options, i.get('group'))]
    names = [i['name'] for i in quest_items + locks if i['goal'] == goal_key]
    # The faction's Requirements item is also needed to complete its goal.
    if goal_key in FACTION_REQUIREMENT_NAMES:
        names.append(FACTION_REQUIREMENT_NAMES[goal_key])
    return names


item_name_groups = {
    "Filler": list(FILLER),
    "Traps": list(TRAPS),
    "Faction Requirements": list(FACTION_REQUIREMENT_NAMES.values()),
}
