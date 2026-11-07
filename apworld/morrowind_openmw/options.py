from dataclasses import dataclass
from Options import Toggle, Choice, DefaultOnToggle, PerGameCommonOptions, Range

class MainQuest(DefaultOnToggle):
    """Include the main quest (kill Dagoth Ur) in the goal. Enabled
    (default): it must be completed to win and its quest items are
    provided by Archipelago. Disabled: the main quest is no longer a
    goal (neither its items nor its checks); at least one other goal must then
    be chosen (great house, guild, faction or daedric quests)."""
    display_name = "Main Quest"


class GreatHouse(Choice):
    """Great House to complete IN ADDITION to the main quest if it is enabled
    (become leader, rank 10). Its quest items are provided by Archipelago."""
    display_name = "Great House"
    option_none = 0
    option_hlaalu = 1
    option_redoran = 2
    option_telvanni = 3
    default = 0


class Guild(Choice):
    """Guild to complete IN ADDITION to the main quest if it is enabled
    (become leader, rank 10).
    Its quest items are provided by Archipelago."""
    display_name = "Guild"
    option_none = 0
    option_fighters_guild = 1
    option_mages_guild = 2
    option_thieves_guild = 3
    default = 0


class Faction(Choice):
    """Faction to complete IN ADDITION to the main quest if it is enabled
    (become leader, rank 10).
    Its quest items are provided by Archipelago."""
    display_name = "Faction"
    option_none = 0
    option_imperial_cult = 1
    option_imperial_legion = 2
    option_temple = 3
    option_morag_tong = 4
    default = 0


class DaedricQuests(Toggle):
    """Add the 7 daedric quests to the goal (complete all of them).
    Each quest is locked until its Archipelago item
    (Daedric Quest: <prince>) is received, and its quest items come
    from Archipelago."""
    display_name = "Daedric Quests"
    default = False


class Traps(DefaultOnToggle):
    """Include trap items (Disease, Bounty, Summon Scamp, Steal Gold) in the
    item pool. Disabled: no trap is generated, they are replaced by filler."""
    display_name = "Traps"


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
    traps: Traps = Traps.default
    death_link: DeathLink = DeathLink.default


def selected_goals(options) -> list:
    """Goals to complete: the main quest (if enabled, by default) +
    the chosen great house, guild and faction (if != none) + the
    daedric quests (if enabled)."""
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


# Quest group (tools/quest_groups.py) -> goal key (data/goals.yaml).
# House / guild / faction groups carry the name of their goal.
GROUP_GOALS = {"main": "main_quest", "daedric": "daedric_quests"}


def goal_of_group(group: str) -> str:
    return GROUP_GOALS.get(group, group)

class HintCost(Range):
    """Pourcentage du nombre total d'emplacements que coûte un indice."""
    display_name = "Hint Cost"
    range_start = 0
    range_end = 100
    default = 1  # Définir à 1 pour 1%
