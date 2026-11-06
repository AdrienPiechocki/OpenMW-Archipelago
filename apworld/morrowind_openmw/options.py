from dataclasses import dataclass
from Options import Toggle, Choice, DefaultOnToggle, PerGameCommonOptions


class MainQuest(DefaultOnToggle):
    """Inclut la quete principale (tuer Dagoth Ur) dans l'objectif. Active
    (defaut) : elle doit etre terminee pour gagner et ses objets de quete sont
    fournis par Archipelago. Desactive : la quete principale n'est plus un
    objectif (ni ses objets, ni ses checks) ; il faut alors choisir au moins un
    autre objectif (maison, guilde, faction ou quetes daedriques)."""
    display_name = "Main Quest"


class GreatHouse(Choice):
    """Grande Maison a terminer EN PLUS de la quete principale si elle est activee
    (devenir chef, rang 10). Ses objets de quete sont fournis par Archipelago."""
    display_name = "Great House"
    option_none = 0
    option_hlaalu = 1
    option_redoran = 2
    option_telvanni = 3
    default = 0


class Guild(Choice):
    """Guilde a terminer EN PLUS de la quete principale si elle est activee
    (devenir chef, rang 10).
    Ses objets de quete sont fournis par Archipelago."""
    display_name = "Guild"
    option_none = 0
    option_fighters_guild = 1
    option_mages_guild = 2
    option_thieves_guild = 3
    default = 0


class Faction(Choice):
    """Faction a terminer EN PLUS de la quete principale si elle est activee
    (devenir chef, rang 10).
    Ses objets de quete sont fournis par Archipelago."""
    display_name = "Faction"
    option_none = 0
    option_imperial_cult = 1
    option_imperial_legion = 2
    option_temple = 3
    option_morag_tong = 4
    default = 0


class DaedricQuests(Toggle):
    """Ajoute les 7 quetes daedriques a l'objectif (les terminer toutes).
    Chaque quete est verrouillee tant que son item Archipelago
    (Daedric Quest: <prince>) n'est pas recu, et ses objets de quete viennent
    d'Archipelago."""
    display_name = "Daedric Quests"
    default = False


class DeathLink(Toggle):
    display_name = "Death Link"
    default = True


@dataclass
class MorrowindOptions(PerGameCommonOptions):
    main_quest: MainQuest = MainQuest.default
    great_house: GreatHouse = GreatHouse.default
    guild: Guild = Guild.default
    faction: Faction = Faction.default
    daedric_quests: DaedricQuests = DaedricQuests.default
    death_link: DeathLink = DeathLink.default


def selected_goals(options) -> list:
    """Objectifs a accomplir : la quete principale (si activee, par defaut) +
    la grande maison, la guilde et la faction choisies (si != none) + les
    quetes daedriques (si activees)."""
    goals = []
    main = getattr(options, "main_quest", None)
    if getattr(main, "value", True if main is None else main):
        goals.append("main_quest")
    for name in ("great_house", "guild", "faction"):
        key = getattr(options, name).current_key
        if key != "none":
            goals.append(key)
    if getattr(options.daedric_quests, "value", options.daedric_quests):
        goals.append("daedric_quests")
    return goals


# Groupe de quetes (tools/quest_groups.py) -> cle d'objectif (data/goals.yaml).
# Les groupes de maisons / guildes / factions portent le nom de leur objectif.
GROUP_GOALS = {"main": "main_quest", "daedric": "daedric_quests"}


def goal_of_group(group: str) -> str:
    return GROUP_GOALS.get(group, group)

