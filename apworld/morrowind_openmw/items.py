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

item_table: Dict[str, MorrowindItemData] = {
    "Gold (100)": MorrowindItemData(code=BASE_ITEM + 1, classification=ItemClassification.filler),
    "Healing Potion": MorrowindItemData(code=BASE_ITEM + 2, classification=ItemClassification.filler),
    "Soul Gem": MorrowindItemData(code=BASE_ITEM + 3, classification=ItemClassification.filler),
    "Arrow (30)": MorrowindItemData(code=BASE_ITEM + 4, classification=ItemClassification.filler),
    # +10 niveaux : ajoute la progression de 10 montees de niveau vanilla.
    # Le joueur dort pour choisir ses attributs (voir mod/scripts/ap/level_up.lua).
    "Level Up (+10)": MorrowindItemData(
        code=BASE_ITEM + 2000, classification=ItemClassification.useful, frequency=4
    ),
    # "Niveau de Levitation" et "Bonus de Force" supprimes
    "Piege: Maladie": MorrowindItemData(code=BASE_ITEM + 200, classification=ItemClassification.trap),
    "Piege: Bounty": MorrowindItemData(code=BASE_ITEM + 201, classification=ItemClassification.trap),
    "Piege: Summon Scamp": MorrowindItemData(code=BASE_ITEM + 202, classification=ItemClassification.trap),
    "Piege: Steal Gold": MorrowindItemData(code=BASE_ITEM + 203, classification=ItemClassification.trap),
    # Niveaux de competence (+5)
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

# Objets de quete par objectif (goal) : data/quest_items.yaml.
# Ils ne sont dans le pool que si le goal choisi correspond.
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
# Quetes verrouillees : un item de progression par quete (data/quest_locks.yaml).
quest_locks = _load_yaml('quest_locks.yaml')
for _it in quest_items + quest_locks:
    item_table[_it['name']] = MorrowindItemData(
        code=_it['id'],
        classification=ItemClassification.progression,
        can_create=lambda options, g=_it['goal']: g in selected_goals(options),
    )


def quest_item_names(goal_key):
    """Noms des items AP necessaires pour l'objectif `goal_key` : objets de
    quete + items de deverrouillage de quetes."""
    return [i['name'] for i in quest_items + quest_locks if i['goal'] == goal_key]


item_name_groups = {
    "Filler": ["Gold (100)", "Healing Potion", "Soul Gem", "Arrow (30)"],
}