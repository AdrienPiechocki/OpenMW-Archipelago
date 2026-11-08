from BaseClasses import Item, ItemClassification
import os
from typing import NamedTuple, Dict, Callable

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None
from .options import MorrowindOptions, selected_goals


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

item_table: Dict[str, MorrowindItemData] = {
    "Gold (100)": MorrowindItemData(code=BASE_ITEM + 1, classification=ItemClassification.filler),
    "Healing Potion": MorrowindItemData(code=BASE_ITEM + 2, classification=ItemClassification.filler),
    "Soul Gem": MorrowindItemData(code=BASE_ITEM + 3, classification=ItemClassification.filler),
    "Arrow (30)": MorrowindItemData(code=BASE_ITEM + 4, classification=ItemClassification.filler),
    # +10 levels: adds the progression of 10 vanilla level-ups.
    # The player sleeps to choose attributes (see mod/scripts/ap/level_up.lua).
    "Level Up (+10)": MorrowindItemData(
        code=BASE_ITEM + 2000, classification=ItemClassification.progression, frequency=4
    ),
    # "Levitation Level" and "Strength Bonus" removed
    "Trap: Damage": MorrowindItemData(code=BASE_ITEM + 200, classification=ItemClassification.trap, can_create=_traps_enabled),
    "Trap: Bounty": MorrowindItemData(code=BASE_ITEM + 201, classification=ItemClassification.trap, can_create=_traps_enabled),
    "Trap: Summon Scamp": MorrowindItemData(code=BASE_ITEM + 202, classification=ItemClassification.trap, can_create=_traps_enabled),
    "Trap: Steal Gold": MorrowindItemData(code=BASE_ITEM + 203, classification=ItemClassification.trap, can_create=_traps_enabled),
    # Skill levels (+5)
    "Skill: Acrobatics": MorrowindItemData(code=BASE_ITEM + 300, classification=ItemClassification.useful),
    "Skill: Alchemy": MorrowindItemData(code=BASE_ITEM + 301, classification=ItemClassification.useful),
    "Skill: Alteration": MorrowindItemData(code=BASE_ITEM + 302, classification=ItemClassification.useful),
    "Skill: Armorer": MorrowindItemData(code=BASE_ITEM + 303, classification=ItemClassification.useful),
    "Skill: Athletics": MorrowindItemData(code=BASE_ITEM + 304, classification=ItemClassification.useful),
    "Skill: Axe": MorrowindItemData(code=BASE_ITEM + 305, classification=ItemClassification.useful),
    "Skill: Block": MorrowindItemData(code=BASE_ITEM + 306, classification=ItemClassification.useful),
    "Skill: Blunt Weapon": MorrowindItemData(code=BASE_ITEM + 307, classification=ItemClassification.useful),
    "Skill: Conjuration": MorrowindItemData(code=BASE_ITEM + 308, classification=ItemClassification.useful),
    "Skill: Destruction": MorrowindItemData(code=BASE_ITEM + 309, classification=ItemClassification.useful),
    "Skill: Enchant": MorrowindItemData(code=BASE_ITEM + 310, classification=ItemClassification.useful),
    "Skill: Hand to Hand": MorrowindItemData(code=BASE_ITEM + 311, classification=ItemClassification.useful),
    "Skill: Heavy Armor": MorrowindItemData(code=BASE_ITEM + 312, classification=ItemClassification.useful),
    "Skill: Illusion": MorrowindItemData(code=BASE_ITEM + 313, classification=ItemClassification.useful),
    "Skill: Light Armor": MorrowindItemData(code=BASE_ITEM + 314, classification=ItemClassification.useful),
    "Skill: Long Blade": MorrowindItemData(code=BASE_ITEM + 315, classification=ItemClassification.useful),
    "Skill: Marksman": MorrowindItemData(code=BASE_ITEM + 316, classification=ItemClassification.useful),
    "Skill: Medium Armor": MorrowindItemData(code=BASE_ITEM + 317, classification=ItemClassification.useful),
    "Skill: Mercantile": MorrowindItemData(code=BASE_ITEM + 318, classification=ItemClassification.useful),
    "Skill: Mysticism": MorrowindItemData(code=BASE_ITEM + 319, classification=ItemClassification.useful),
    "Skill: Restoration": MorrowindItemData(code=BASE_ITEM + 320, classification=ItemClassification.useful),
    "Skill: Security": MorrowindItemData(code=BASE_ITEM + 321, classification=ItemClassification.useful),
    "Skill: Short Blade": MorrowindItemData(code=BASE_ITEM + 322, classification=ItemClassification.useful),
    "Skill: Sneak": MorrowindItemData(code=BASE_ITEM + 323, classification=ItemClassification.useful),
    "Skill: Spear": MorrowindItemData(code=BASE_ITEM + 324, classification=ItemClassification.useful),
    "Skill: Speechcraft": MorrowindItemData(code=BASE_ITEM + 325, classification=ItemClassification.useful),
    "Skill: Unarmored": MorrowindItemData(code=BASE_ITEM + 326, classification=ItemClassification.useful),
}

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
            can_create=lambda options, g=_goal: g in selected_goals(options),
        )


def quest_item_names(goal_key):
    """Names of the AP items required for goal `goal_key`: quest items
    + quest unlock items."""
    return [i['name'] for i in quest_items + quest_locks if i['goal'] == goal_key]


item_name_groups = {
    "Filler": ["Gold (100)", "Healing Potion", "Soul Gem", "Arrow (30)"],
}
