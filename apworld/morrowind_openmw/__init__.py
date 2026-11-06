from worlds.AutoWorld import World, WebWorld
from BaseClasses import Region, Tutorial, LocationProgressType
from Options import OptionError
from .items import MorrowindItem, item_table, item_name_groups, quest_item_names
from .locations import MorrowindLocation, location_table
from .regions import region_table
from .options import MorrowindOptions, selected_goals, goal_of_group
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
        # Sans quete principale, il faut au moins un autre objectif : sinon la
        # seed serait gagnee d'emblee et le mod n'enverrait jamais de victoire.
        if not selected_goals(self.options):
            raise OptionError(
                f"Morrowind OpenMW ({self.player_name}) : aucun objectif. "
                "main_quest est desactive : choisis au moins une maison, une "
                "guilde, une faction ou daedric_quests: true (ou reactive main_quest).")

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
        # Locations pouvant recevoir un item important (progression / utile) :
        # les checks de quetes d'objectif 'safe' ou a fins exclusives n'en font pas partie.
        open_locs = [l for l in unfilled if l.progress_type != LocationProgressType.EXCLUDED]
        self._check_progression_capacity(itempool, open_locs)
        # Moins de locations que d'items (seules les quetes Miscellaneous en
        # fournissent) : retirer d'abord les pieges, puis les items utiles /
        # filler ; les items progression ne sont jamais retires.
        if len(itempool) > total_locations:
            def _rank(it):
                if it.advancement:
                    return None          # jamais retire
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
        # Les items utiles ne vont pas dans les locations exclues : n'en garder
        # que ce que les locations ouvertes peuvent accueillir (apres la progression).
        room = len(open_locs) - sum(1 for x in itempool if x.advancement)
        useful = [x for x in itempool if x.useful and not x.advancement]
        for it in useful[max(room, 0):]:
            itempool.remove(it)
        itempool += [self.create_filler() for _ in range(total_locations - len(itempool))]
        self.multiworld.itempool += itempool

    def _check_progression_capacity(self, itempool, open_locs):
        """Echoue tot, avec un message clair, si la seed ne peut pas etre remplie.

        Les checks de quetes d'objectif exigent les objets de quete de leur
        objectif (voir rules.py) : il faut donc pouvoir placer les objets du
        premier objectif dans des locations libres (Miscellaneous), puis
        chaque objectif debloque ses propres checks pour le suivant.
        """
        n_prog = sum(1 for x in itempool if x.advancement)
        if n_prog > len(open_locs):
            raise OptionError(
                f"Morrowind OpenMW ({self.player_name}) : {n_prog} items de progression "
                f"pour seulement {len(open_locs)} locations pouvant les contenir. "
                "Active goal_quest_checks (plus de locations pour la progression) ou "
                "retire des objectifs (maison / guilde / faction / daedric_quests).")
        goals = selected_goals(self.options)
        need = {g: len(quest_item_names(g)) for g in goals}
        free = sum(1 for l in open_locs if l.name in location_table
                   and location_table[l.name].group == "misc")
        gated = {g: sum(1 for l in open_locs if l.name in location_table
                        and location_table[l.name].group != "misc"
                        and goal_of_group(location_table[l.name].group) == g)
                 for g in goals}
        for g in sorted(goals, key=lambda k: need[k]):
            if need[g] > free:
                raise OptionError(
                    f"Morrowind OpenMW ({self.player_name}) : l'objectif '{g}' a besoin de "
                    f"{need[g]} locations libres pour ses objets de quete mais seules "
                    f"{free} sont disponibles. Active goal_quest_checks (les quetes des objectifs "
                    "deja accomplis liberent des locations) ou retire un objectif.")
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
            # Ancien format (un seul objectif) : premier objectif choisi.
            "goal": goals[0],
            "options": {
                "goal": goals[0],
                "goals": goals,
                "main_quest": "main_quest" in goals,
                "great_house": self.options.great_house.current_key,
                "guild": self.options.guild.current_key,
                "faction": self.options.faction.current_key,
                "daedric_quests": bool(self.options.daedric_quests.value),
                "death_link": bool(getattr(self.options.death_link, "value", self.options.death_link)),
                "goal_quest_checks": 1,
            },
        }
