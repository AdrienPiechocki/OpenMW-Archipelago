from worlds.AutoWorld import World

from worlds.generic.Rules import add_rule

from .items import quest_item_names
from .locations import location_table
from .options import selected_goals, goal_of_group


def set_rules(world: World):
    player = world.player
    multiworld = world.multiworld

    # Quetes Miscellaneous : toutes accessibles librement.
    # Checks de quetes d'objectif : le mod retire les objets de quete (et verrouille
    # les quetes daedriques) tant que l'item AP n'est pas recu. On ne sait pas quel
    # objet sert a quelle quete : le check exige donc TOUS les items de son
    # objectif (logique prudente, jamais plus permissive que le jeu).
    for loc in multiworld.get_locations(player):
        data = location_table.get(loc.name)
        if data is None or data.group == "misc":
            continue
        names = quest_item_names(goal_of_group(data.group))
        if names:
            add_rule(loc, lambda state, n=tuple(names): state.has_all(n, player))

    # Condition de victoire : la quete principale + la grande maison / guilde /
    # faction choisies sont accomplies en jeu, ce qui exige tous leurs objets de
    # quete (data/quest_items.yaml). Le mod retire ces objets des quetes tant
    # que l'item Archipelago n'est pas recu.
    needed = []
    for goal in selected_goals(world.options):
        for name in quest_item_names(goal):
            if name not in needed:
                needed.append(name)
    if needed:
        multiworld.completion_condition[player] = lambda state: state.has_all(needed, player)
    else:
        multiworld.completion_condition[player] = lambda state: True
