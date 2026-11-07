from worlds.AutoWorld import World

from worlds.generic.Rules import add_rule

from .items import quest_item_names
from .locations import location_table
from .options import selected_goals, goal_of_group, is_free_group


def set_rules(world: World):
    player = world.player
    multiworld = world.multiworld

    # Miscellaneous and expansion (Tribunal / Bloodmoon) quests: all freely
    # accessible (no logic: we do not model access to Mournhold / Solstheim).
    # Goal quest checks: the mod removes quest items (and locks
    # daedric quests) until the AP item is received. We do not know which
    # item is used for which quest: the check therefore requires ALL items of its
    # goal (conservative logic, never more permissive than the game).
    for loc in multiworld.get_locations(player):
        data = location_table.get(loc.name)
        if data is None or is_free_group(data.group):
            continue
        names = quest_item_names(goal_of_group(data.group))
        if names:
            add_rule(loc, lambda state, n=tuple(names): state.has_all(n, player))

    # Victory condition: the main quest + the chosen great house / guild /
    # faction are completed in-game, which requires all of their quest
    # items (data/quest_items.yaml). The mod removes these items from quests while
    # the Archipelago item has not been received.
    needed = []
    for goal in selected_goals(world.options):
        for name in quest_item_names(goal):
            if name not in needed:
                needed.append(name)
    if needed:
        multiworld.completion_condition[player] = lambda state: state.has_all(needed, player)
    else:
        multiworld.completion_condition[player] = lambda state: True
