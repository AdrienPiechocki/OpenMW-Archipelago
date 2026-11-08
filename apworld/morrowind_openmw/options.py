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
    Its quest items are provided by Archipelago. east_empire_company is the
    Bloodmoon faction (rank Factor): it requires Bloodmoon.esm in OpenMW."""
    display_name = "Faction"
    option_none = 0
    option_imperial_cult = 1
    option_imperial_legion = 2
    option_temple = 3
    option_morag_tong = 4
    option_east_empire_company = 5
    default = 0


class DaedricQuests(Toggle):
    """Add the 7 daedric quests to the goal (complete all of them).
    Each quest is locked until its Archipelago item
    (Daedric Quest: <prince>) is received, and its quest items come
    from Archipelago."""
    display_name = "Daedric Quests"
    default = False


class StartingLevel(Range):
    """Starting level of the character (1-100). Once the tutorial is over
    (character creation finished), the level is set to this value and each
    attribute and skill is increased by this amount (capped at 100). The
    health that level-ups would have given is added too. 1 = vanilla (no
    bonus)."""
    display_name = "Starting Level"
    range_start = 1
    range_end = 100
    default = 1


class TribunalMainQuest(Toggle):
    """Tribunal: its main quest (The Mad God, death of Almalexia) gives checks
    for its quests AND becomes a goal. Requires Tribunal.esm in OpenMW."""
    display_name = "Tribunal: Main Quest"
    default = False


class TribunalSideQuests(Toggle):
    """Tribunal: the other quests of the expansion (Tribunal has no faction
    quests) completed give a check. Never a goal. Requires Tribunal.esm."""
    display_name = "Tribunal: Side Quests"
    default = False


class BloodmoonMainQuest(Toggle):
    """Bloodmoon: its main quest (Hircine's Hunt) gives checks for its quests
    AND becomes a goal. Requires Bloodmoon.esm in OpenMW."""
    display_name = "Bloodmoon: Main Quest"
    default = False


class BloodmoonSideQuests(Toggle):
    """Bloodmoon: the quests that are neither the main quest nor the East Empire
    Company (faction option) completed give a check. Never a goal.
    Requires Bloodmoon.esm."""
    display_name = "Bloodmoon: Side Quests"
    default = False


class Traps(DefaultOnToggle):
    """Include trap items (Damage, Bounty, Summon Scamp, Steal Gold) in the
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
    starting_level: StartingLevel = StartingLevel.default
    tribunal_main_quest: TribunalMainQuest = TribunalMainQuest.default
    tribunal_side_quests: TribunalSideQuests = TribunalSideQuests.default
    bloodmoon_main_quest: BloodmoonMainQuest = BloodmoonMainQuest.default
    bloodmoon_side_quests: BloodmoonSideQuests = BloodmoonSideQuests.default
    traps: Traps = Traps.default
    death_link: DeathLink = DeathLink.default


def selected_goals(options) -> list:
    """Goals to complete: the main quest (if enabled, by default) +
    the chosen great house, guild and faction (if != none) + the
    daedric quests (if enabled) + the main quest of each expansion whose
    `<expansion>_main_quest` option is enabled (tribunal, bloodmoon)."""
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
    for exp in EXPANSIONS:
        if _enabled(options, f"{exp}_main_quest"):
            goals.append(exp)
    return goals


# Quest group (tools/quest_groups.py) -> goal key (data/goals.yaml).
# House / guild / faction groups carry the name of their goal.
GROUP_GOALS = {"main": "main_quest", "daedric": "daedric_quests"}


# Expansions and their quest categories (the East Empire Company faction is not
# here: it is the `faction` option). Each expansion quest belongs to ONE
# group "<expansion>_<category>" (tools/quest_groups.py); each group is
# enabled by its own option "<expansion>_<option suffix>".
EXPANSIONS = ("tribunal", "bloodmoon")
EXPANSION_CATEGORY_OPTIONS = {"main": "main_quest", "side": "side_quests"}
EXPANSION_GROUPS = tuple(f"{e}_{c}" for e in EXPANSIONS for c in EXPANSION_CATEGORY_OPTIONS)

# Quest groups that give checks without being a goal: Miscellaneous quests
# (always) and expansion quests (if the option of their group is enabled).
FREE_GROUPS = ("misc",) + EXPANSION_GROUPS


def _enabled(options, name) -> bool:
    opt = getattr(options, name, None)
    return bool(getattr(opt, "value", opt))


def is_free_group(group: str) -> bool:
    return group in FREE_GROUPS


def selected_expansion_groups(options) -> list:
    """Enabled expansion groups, e.g. ["tribunal_main", "bloodmoon_side"]."""
    return [f"{e}_{c}" for e in EXPANSIONS for c, suffix in EXPANSION_CATEGORY_OPTIONS.items()
            if _enabled(options, f"{e}_{suffix}")]


def selected_expansions(options) -> list:
    """Expansions with at least one enabled category, in EXPANSIONS order."""
    groups = selected_expansion_groups(options)
    return [e for e in EXPANSIONS if any(g.startswith(e + "_") for g in groups)]


def goal_of_group(group: str) -> str:
    return GROUP_GOALS.get(group, group)

class HintCost(Range):
    """Pourcentage du nombre total d'emplacements que coûte un indice."""
    display_name = "Hint Cost"
    range_start = 0
    range_end = 100
    default = 1  # Définir à 1 pour 1%
