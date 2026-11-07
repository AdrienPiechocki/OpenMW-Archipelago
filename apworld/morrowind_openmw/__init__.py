from worlds.AutoWorld import World, WebWorld
from BaseClasses import Region, Tutorial, LocationProgressType
from Options import OptionError
from .items import MorrowindItem, item_table, item_name_groups, quest_item_names
from .locations import MorrowindLocation, location_table
from .regions import region_table
from .options import MorrowindOptions, selected_goals, goal_of_group, is_free_group, selected_expansions, selected_expansion_groups
from .rules import set_rules
from typing import Dict, Any


class MorrowindWebWorld(WebWorld):
    pass


class MorrowindWorld(World):
    game = "Morrowind OpenMW"
    required_client_version = (0, 6, 0)

    item_name_to_id = {name: data.code for name, data in item_table.items() if data.code is not None}
    location_name_to_id = {name: data.code for name, data in location_table.items() if data.code is not None}
    item_name_groups = item_name_groups

    options_dataclass = MorrowindOptions
    options: MorrowindOptions

    web = MorrowindWebWorld()

    filler_item_name = "Gold (100)"

    def get_filler_item_name(self):
        return "Gold (100)"

    def generate_early(self):
        # Without the main quest, at least one other goal is required: otherwise
        # the seed would be won immediately and the mod would never send a victory.
        if not selected_goals(self.options):
            raise OptionError(
                f"Morrowind OpenMW ({self.player_name}): no goals selected. "
                "main_quest is disabled: choose at least one great house, a "
                "guild, a faction, daedric_quests: true, tribunal_main_quest: true or "
                "bloodmoon_main_quest: true (or re-enable main_quest).")

    def create_item(self, name: str) -> MorrowindItem:
        data = item_table[name]
        return MorrowindItem(name, data.classification, data.code, self.player)

    def create_items(self):
        itempool = []
        for item_name, item_data in item_table.items():
            if not item_data.can_create(self.options):
                continue
            for _ in range(item_data.precollect):
                self.multiworld.push_precollected(self.create_item(item_name))
            itempool += [self.create_item(item_name) for _ in range(item_data.precollect, item_data.frequency)]
        unfilled = self.multiworld.get_unfilled_locations(self.player)
        total_locations = len(unfilled)
        # Locations that can hold an important item (progression / useful):
        # checks for 'safe' goal quests or quests with exclusive endings are not among them.
        open_locs = [l for l in unfilled if l.progress_type != LocationProgressType.EXCLUDED]
        self._check_progression_capacity(itempool, open_locs)
        # Fewer locations than items (only Miscellaneous quests provide
        # locations): remove traps first, then useful items / filler;
        # progression items are never removed.
        if len(itempool) > total_locations:
            def _rank(it):
                if it.advancement:
                    return None          # never removed
                if it.trap:
                    return 0
                if it.useful:
                    return 2
                return 1                 # filler
            for rank in (0, 1, 2):
                for it in [x for x in itempool if _rank(x) == rank]:
                    if len(itempool) <= total_locations:
                        break
                    itempool.remove(it)
        # Useful items do not go into excluded locations: keep only as many as
        # the open locations can hold (after progression items).
        room = len(open_locs) - sum(1 for x in itempool if x.advancement)
        useful = [x for x in itempool if x.useful and not x.advancement]
        for it in useful[max(room, 0):]:
            itempool.remove(it)
        itempool += [self.create_filler() for _ in range(total_locations - len(itempool))]
        self.multiworld.itempool += itempool

    def _check_progression_capacity(self, itempool, open_locs):
        """Fail early, with a clear message, if the seed cannot be filled.

        Goal quest checks require the quest items of their goal (see rules.py):
        the first goal's items must therefore fit into free locations
        (Miscellaneous), then each goal unlocks its own checks for the next one.
        """
        n_prog = sum(1 for x in itempool if x.advancement)
        if n_prog > len(open_locs):
            raise OptionError(
                f"Morrowind OpenMW ({self.player_name}): {n_prog} progression items "
                f"for only {len(open_locs)} locations that can hold them. "
                "Enable goal_quest_checks (more locations for progression) or "
                "remove some goals (great house / guild / faction / daedric_quests).")
        goals = selected_goals(self.options)
        need = {g: len(quest_item_names(g)) for g in goals}
        free = sum(1 for l in open_locs if l.name in location_table
                   and is_free_group(location_table[l.name].group))
        gated = {g: sum(1 for l in open_locs if l.name in location_table
                        and not is_free_group(location_table[l.name].group)
                        and goal_of_group(location_table[l.name].group) == g)
                 for g in goals}
        for g in sorted(goals, key=lambda k: need[k]):
            if need[g] > free:
                raise OptionError(
                    f"Morrowind OpenMW ({self.player_name}): goal '{g}' needs "
                    f"{need[g]} free locations for its quest items but only "
                    f"{free} are available. Enable goal_quest_checks (quests of goals "
                    "already completed free up locations) or remove a goal.")
            free += gated[g] - need[g]

    def create_regions(self):
        for region_name in region_table.keys():
            self.multiworld.regions.append(Region(region_name, self.player, self.multiworld))

        for loc_name, loc_data in location_table.items():
            if not loc_data.can_create(self.options):
                continue
            region = self.multiworld.get_region(loc_data.region, self.player)
            new_loc = MorrowindLocation(self.player, loc_name, loc_data.code, region)
            if loc_data.excluded(self.options):
                new_loc.progress_type = LocationProgressType.EXCLUDED
            region.locations.append(new_loc)

        for region_name, exit_list in region_table.items():
            region = self.multiworld.get_region(region_name, self.player)
            region.add_exits(exit_list)

    def set_rules(self):
        set_rules(self)

    def fill_slot_data(self) -> Dict[str, Any]:
        goals = selected_goals(self.options)
        return {
            # Old format (single goal): first selected goal.
            "goal": goals[0],
            "options": {
                "goal": goals[0],
                "goals": goals,
                "main_quest": "main_quest" in goals,
                "great_house": self.options.great_house.current_key,
                "guild": self.options.guild.current_key,
                "faction": self.options.faction.current_key,
                "daedric_quests": bool(self.options.daedric_quests.value),
                "traps": bool(self.options.traps.value),
                "starting_level": int(self.options.starting_level.value),
                # Enabled expansion groups (tribunal_main, bloodmoon_side...): the
                # mod only sends the checks of the quests in these groups.
                "expansion_groups": selected_expansion_groups(self.options),
                # Expansions with at least one enabled group (informational).
                "expansions": selected_expansions(self.options),
                "death_link": bool(getattr(self.options.death_link, "value", self.options.death_link)),
                "goal_quest_checks": 1,
            },
        }
