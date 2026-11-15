from dataclasses import dataclass
from Options import Toggle, Choice, DefaultOnToggle, PerGameCommonOptions, Range, OptionSet

class MainQuest(DefaultOnToggle):
    """Include the main quest (kill Dagoth Ur) in the goal. Enabled
    (default): it must be completed to win and its quest items are
    provided by Archipelago. Disabled: the main quest is no longer a
    goal (neither its items nor its checks); at least one other goal must then
    be chosen (great house, guild, faction or daedric quests)."""
    display_name = "Main Quest"


class GreatHouse(Choice):
    """Great House to complete IN ADDITION to the main quest if it is enabled
    (become leader, rank 10). Its quest items are provided by Archipelago.
    indoril is the Tamriel Rebuilt house (TR_Mainland.esm required)."""
    display_name = "Great House"
    option_none = 0
    option_hlaalu = 1
    option_redoran = 2
    option_telvanni = 3
    # Tamriel Rebuilt (TR_Mainland.esm + Tamriel_Data.esm required in OpenMW).
    option_indoril = 4
    default = 0


# Guilds / factions: several can be chosen at once (goals = all of them).
# Keys are listed in a fixed order: it is the order of the goals in selected_goals().
GUILD_KEYS = (
    # Vanilla.
    "fighters_guild", "mages_guild", "thieves_guild",
    # Project Cyrodiil guilds (Cyr_Main.esm + Tamriel_Data.esm required), separate from the vanilla ones.
    "cyrodiil_fighters_guild", "cyrodiil_mages_guild", "cyrodiil_thieves_guild",
    # Skyrim: Home of the Nords guilds (Sky_Main.esm + Tamriel_Data.esm required).
    "skyrim_fighters_guild", "skyrim_mages_guild", "hammerfell_mages_guild", "skyrim_thieves_guild",
)
FACTION_KEYS = (
    # Vanilla / Bloodmoon.
    "imperial_cult", "imperial_legion", "temple", "morag_tong", "east_empire_company",
    # Tamriel Rebuilt (TR_Mainland.esm + Tamriel_Data.esm required); the Ordinators come with Poison Song.
    "ja_natta_syndicate", "ordinators",
    # Project Cyrodiil (Cyr_Main.esm + Tamriel_Data.esm required).
    "kingdom_of_anvil", "itinerant_priests",
)


class _KeySet(OptionSet):
    """Set of keys: case-insensitive, `-` accepted for `_`, `none` ignored (= empty set)."""
    def __init__(self, value):
        if isinstance(value, str):
            value = [v for v in value.split(",")]
        super().__init__({str(v).strip().lower().replace("-", "_") for v in value
                          if str(v).strip().lower() not in ("", "none")})


class Guild(_KeySet):
    """Guilds to complete IN ADDITION to the main quest if it is enabled
    (become leader, rank 10 in each). You can choose several, across regions, e.g.
    `guild: [mages_guild, skyrim_mages_guild, hammerfell_mages_guild]`. Empty = no guild.
    Its quest items are provided by Archipelago.
    Vanilla: fighters_guild, mages_guild, thieves_guild.
    Project Cyrodiil (Cyr_Main.esm + Tamriel_Data.esm required): cyrodiil_fighters_guild,
    cyrodiil_mages_guild, cyrodiil_thieves_guild.
    Skyrim: Home of the Nords (Sky_Main.esm + Tamriel_Data.esm required): skyrim_fighters_guild,
    skyrim_mages_guild, hammerfell_mages_guild, skyrim_thieves_guild."""
    display_name = "Guild"
    valid_keys = frozenset(GUILD_KEYS)
    default = frozenset()


class Faction(_KeySet):
    """Factions to complete IN ADDITION to the main quest if it is enabled
    (become leader, rank 10 in each). You can choose several, e.g.
    `faction: [temple, ordinators]`. Empty = no faction.
    Its quest items are provided by Archipelago. east_empire_company is the
    Bloodmoon faction (rank Factor): it requires Bloodmoon.esm in OpenMW.
    With tamriel_rebuilt_factions it also enables the Tamriel Rebuilt East
    Empire Company questline. ja_natta_syndicate (also accepted: ja-natta_syndicate) and
    ordinators are Tamriel Rebuilt factions (TR_Mainland.esm; the Ordinators come with Poison Song).
    kingdom_of_anvil and itinerant_priests are Project Cyrodiil factions
    (Cyr_Main.esm + Tamriel_Data.esm)."""
    display_name = "Faction"
    valid_keys = frozenset(FACTION_KEYS)
    default = frozenset()


class DaedricQuests(Toggle):
    """Add the 7 daedric quests to the goal (complete all of them).
    Each quest is locked until its Archipelago item
    (Daedric Quest: <prince>) is received, and its quest items come
    from Archipelago."""
    display_name = "Daedric Quests"
    default = False


class _StartBonus(Range):
    """Base of the starting attribute / skill bonuses (not a player option)."""
    range_start = 0
    range_end = 100
    default = 0


class AttributeStrength(_StartBonus):
    """Bonus added to Strength once the tutorial is over (character creation
    finished). 0 = vanilla. The attribute is capped at 100 and never lowered."""
    display_name = "Attribute: Strength"


class AttributeIntelligence(_StartBonus):
    """Bonus added to Intelligence once the tutorial is over (character creation
    finished). 0 = vanilla. The attribute is capped at 100 and never lowered."""
    display_name = "Attribute: Intelligence"


class AttributeWillpower(_StartBonus):
    """Bonus added to Willpower once the tutorial is over (character creation
    finished). 0 = vanilla. The attribute is capped at 100 and never lowered."""
    display_name = "Attribute: Willpower"


class AttributeAgility(_StartBonus):
    """Bonus added to Agility once the tutorial is over (character creation
    finished). 0 = vanilla. The attribute is capped at 100 and never lowered."""
    display_name = "Attribute: Agility"


class AttributeSpeed(_StartBonus):
    """Bonus added to Speed once the tutorial is over (character creation
    finished). 0 = vanilla. The attribute is capped at 100 and never lowered."""
    display_name = "Attribute: Speed"


class AttributeEndurance(_StartBonus):
    """Bonus added to Endurance once the tutorial is over (character creation
    finished). 0 = vanilla. The attribute is capped at 100 and never lowered."""
    display_name = "Attribute: Endurance"


class AttributePersonality(_StartBonus):
    """Bonus added to Personality once the tutorial is over (character creation
    finished). 0 = vanilla. The attribute is capped at 100 and never lowered."""
    display_name = "Attribute: Personality"


class AttributeLuck(_StartBonus):
    """Bonus added to Luck once the tutorial is over (character creation
    finished). 0 = vanilla. The attribute is capped at 100 and never lowered."""
    display_name = "Attribute: Luck"


class SkillAcrobatics(_StartBonus):
    """Bonus added to the Acrobatics skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Acrobatics"


class SkillAlchemy(_StartBonus):
    """Bonus added to the Alchemy skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Alchemy"


class SkillAlteration(_StartBonus):
    """Bonus added to the Alteration skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Alteration"


class SkillArmorer(_StartBonus):
    """Bonus added to the Armorer skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Armorer"


class SkillAthletics(_StartBonus):
    """Bonus added to the Athletics skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Athletics"


class SkillAxe(_StartBonus):
    """Bonus added to the Axe skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Axe"


class SkillBlock(_StartBonus):
    """Bonus added to the Block skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Block"


class SkillBluntweapon(_StartBonus):
    """Bonus added to the Blunt Weapon skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Blunt Weapon"


class SkillConjuration(_StartBonus):
    """Bonus added to the Conjuration skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Conjuration"


class SkillDestruction(_StartBonus):
    """Bonus added to the Destruction skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Destruction"


class SkillEnchant(_StartBonus):
    """Bonus added to the Enchant skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Enchant"


class SkillHandtohand(_StartBonus):
    """Bonus added to the Hand-to-hand skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Hand-to-hand"


class SkillHeavyarmor(_StartBonus):
    """Bonus added to the Heavy Armor skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Heavy Armor"


class SkillIllusion(_StartBonus):
    """Bonus added to the Illusion skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Illusion"


class SkillLightarmor(_StartBonus):
    """Bonus added to the Light Armor skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Light Armor"


class SkillLongblade(_StartBonus):
    """Bonus added to the Long Blade skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Long Blade"


class SkillMarksman(_StartBonus):
    """Bonus added to the Marksman skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Marksman"


class SkillMediumarmor(_StartBonus):
    """Bonus added to the Medium Armor skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Medium Armor"


class SkillMercantile(_StartBonus):
    """Bonus added to the Mercantile skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Mercantile"


class SkillMysticism(_StartBonus):
    """Bonus added to the Mysticism skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Mysticism"


class SkillRestoration(_StartBonus):
    """Bonus added to the Restoration skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Restoration"


class SkillSecurity(_StartBonus):
    """Bonus added to the Security skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Security"


class SkillShortblade(_StartBonus):
    """Bonus added to the Short Blade skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Short Blade"


class SkillSneak(_StartBonus):
    """Bonus added to the Sneak skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Sneak"


class SkillSpear(_StartBonus):
    """Bonus added to the Spear skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Spear"


class SkillSpeechcraft(_StartBonus):
    """Bonus added to the Speechcraft skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Speechcraft"


class SkillUnarmored(_StartBonus):
    """Bonus added to the Unarmored skill once the tutorial is over (character
    creation finished). 0 = vanilla. The skill is capped at 100 and never lowered."""
    display_name = "Skill: Unarmored"


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


class TamrielRebuiltMainQuest(Toggle):
    """Tamriel Rebuilt: add the TR main quest (Foul Murder, epilogue of the
    Morrowind main quest) to the main quest goal. Only effective if
    main_quest is enabled. Gives checks AND must be completed to win.
    Requires TR_Mainland.esm and Tamriel_Data.esm in OpenMW."""
    display_name = "Tamriel Rebuilt: Main Quest"
    default = False


class TamrielRebuiltSideQuests(Toggle):
    """Tamriel Rebuilt: the miscellaneous quests of TR (neither main,
    faction nor Daedric quests) give a check. Never a goal."""
    display_name = "Tamriel Rebuilt: Side Quests"
    default = False


class TamrielRebuiltFactions(Toggle):
    """Tamriel Rebuilt: the TR quests of the great house / guild / faction
    chosen in great_house, guild and faction give checks (they are part of
    that goal's checks). TR quests of unchosen factions are ignored.
    The East Empire Company questline is enabled by faction:
    east_empire_company."""
    display_name = "Tamriel Rebuilt: Factions"
    default = False


class TamrielRebuiltDaedricQuests(Toggle):
    """Tamriel Rebuilt: the TR Daedric quests give checks and are added to
    the Daedric goal. Only effective if daedric_quests is enabled."""
    display_name = "Tamriel Rebuilt: Daedric Quests"
    default = False


class ProjectCyrodiilSideQuests(Toggle):
    """Project Cyrodiil: the quests of the mod that belong to none of its
    factions (Kingdom of Anvil, Itinerant Priests, Cyrodiil guilds) give a
    check. Never a goal. The quests of a Project Cyrodiil guild / faction
    chosen in `guild` / `faction` are always part of that goal's checks.
    Requires Cyr_Main.esm and Tamriel_Data.esm in OpenMW."""
    display_name = "Project Cyrodiil: Side Quests"
    default = False


class SkyrimSideQuests(Toggle):
    """Skyrim: Home of the Nords: the quests of the mod that belong to none of
    its guilds (bounties, arena, miscellaneous quests of Karthwasten and
    Dragonstar...) give a check. Never a goal. The quests of a Skyrim guild
    chosen in `guild` are always part of that goal's checks.
    Requires Sky_Main.esm and Tamriel_Data.esm in OpenMW."""
    display_name = "Skyrim: Home of the Nords: Side Quests"
    default = False


class VampireClan(Choice):
    """Vampire clan: a category of its own, not a house, a guild or a faction. A player belongs
    to ONE clan only (the one of the vampire that infected them), so you choose a single one,
    vanilla or Tamriel Rebuilt. You get a check for the quests open to any bloodline and for the
    quests of your clan, and the final quest of your clan becomes a goal.
    Vanilla: aundae (The Vampire Hunter), berne (The Vampire Merta),
    quarra (The Quarra Amulet); 7 quests open to any bloodline + 2 per clan.
    Tamriel Rebuilt (TR_Mainland.esm + Tamriel_Data.esm required): baluath (Slay Orlukh Ancient)
    and orlukh (Namira's Shroud) are enemies; the quests open to both (Raenor's Revenge) are common.
    none = no check; unaligned = only the vanilla quests open to any bloodline, no goal;
    tamriel_rebuilt_unaligned = only the Tamriel Rebuilt common quests, no goal.
    You must really join that clan in game. A Cure for Vampirism is not a check and is disabled in
    game as soon as a clan goal is selected (curing yourself would make the final quest of your
    clan impossible)."""
    display_name = "Vampire Clan"
    option_none = 0
    option_unaligned = 1
    option_aundae = 2
    option_berne = 3
    option_quarra = 4
    option_baluath = 5
    option_orlukh = 6
    option_tamriel_rebuilt_unaligned = 7
    default = 0


class Traps(DefaultOnToggle):
    """Include trap items (Damage, Bounty, Steal Gold, Drain Fatigue / Magicka, summoned
    Scamp / Flame Atronach / Clannfear / Cliff Racers) in the item pool. Disabled: no trap is
    generated, the slots are filled with the regular filler."""
    display_name = "Traps"


class TrapPercentage(Range):
    """Percentage of the filler slots replaced by traps (only if `traps` is enabled).
    The rest of the filler is a varied mix (gold, potions, soul gems, arrows, lockpicks,
    probes, food, drinks) instead of gold only."""
    display_name = "Trap Percentage"
    range_start = 0
    range_end = 100
    default = 5


class QuestRewards(Toggle):
    """Randomize quest rewards: the UNIQUE items (named weapons, armor, rings,
    books...) given by quests that are not needed for progression become
    Archipelago checks (the vanilla reward is removed when you would receive
    it) and their items go into the pool. Gold and consumables are ignored.
    Only quests whose checks are enabled (goal, expansion or Tamriel Rebuilt
    group) have randomized rewards. Requires data/quest_rewards.yaml
    (tools/gen_quest_rewards.py)."""
    display_name = "Quest Rewards"
    default = True


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
    attribute_strength: AttributeStrength = AttributeStrength.default
    attribute_intelligence: AttributeIntelligence = AttributeIntelligence.default
    attribute_willpower: AttributeWillpower = AttributeWillpower.default
    attribute_agility: AttributeAgility = AttributeAgility.default
    attribute_speed: AttributeSpeed = AttributeSpeed.default
    attribute_endurance: AttributeEndurance = AttributeEndurance.default
    attribute_personality: AttributePersonality = AttributePersonality.default
    attribute_luck: AttributeLuck = AttributeLuck.default
    skill_acrobatics: SkillAcrobatics = SkillAcrobatics.default
    skill_alchemy: SkillAlchemy = SkillAlchemy.default
    skill_alteration: SkillAlteration = SkillAlteration.default
    skill_armorer: SkillArmorer = SkillArmorer.default
    skill_athletics: SkillAthletics = SkillAthletics.default
    skill_axe: SkillAxe = SkillAxe.default
    skill_block: SkillBlock = SkillBlock.default
    skill_bluntweapon: SkillBluntweapon = SkillBluntweapon.default
    skill_conjuration: SkillConjuration = SkillConjuration.default
    skill_destruction: SkillDestruction = SkillDestruction.default
    skill_enchant: SkillEnchant = SkillEnchant.default
    skill_handtohand: SkillHandtohand = SkillHandtohand.default
    skill_heavyarmor: SkillHeavyarmor = SkillHeavyarmor.default
    skill_illusion: SkillIllusion = SkillIllusion.default
    skill_lightarmor: SkillLightarmor = SkillLightarmor.default
    skill_longblade: SkillLongblade = SkillLongblade.default
    skill_marksman: SkillMarksman = SkillMarksman.default
    skill_mediumarmor: SkillMediumarmor = SkillMediumarmor.default
    skill_mercantile: SkillMercantile = SkillMercantile.default
    skill_mysticism: SkillMysticism = SkillMysticism.default
    skill_restoration: SkillRestoration = SkillRestoration.default
    skill_security: SkillSecurity = SkillSecurity.default
    skill_shortblade: SkillShortblade = SkillShortblade.default
    skill_sneak: SkillSneak = SkillSneak.default
    skill_spear: SkillSpear = SkillSpear.default
    skill_speechcraft: SkillSpeechcraft = SkillSpeechcraft.default
    skill_unarmored: SkillUnarmored = SkillUnarmored.default
    tribunal_main_quest: TribunalMainQuest = TribunalMainQuest.default
    tribunal_side_quests: TribunalSideQuests = TribunalSideQuests.default
    bloodmoon_main_quest: BloodmoonMainQuest = BloodmoonMainQuest.default
    bloodmoon_side_quests: BloodmoonSideQuests = BloodmoonSideQuests.default
    tamriel_rebuilt_main_quest: TamrielRebuiltMainQuest = TamrielRebuiltMainQuest.default
    tamriel_rebuilt_side_quests: TamrielRebuiltSideQuests = TamrielRebuiltSideQuests.default
    tamriel_rebuilt_factions: TamrielRebuiltFactions = TamrielRebuiltFactions.default
    tamriel_rebuilt_daedric_quests: TamrielRebuiltDaedricQuests = TamrielRebuiltDaedricQuests.default
    vampire_clan: VampireClan = VampireClan.default
    project_cyrodiil_side_quests: ProjectCyrodiilSideQuests = ProjectCyrodiilSideQuests.default
    skyrim_side_quests: SkyrimSideQuests = SkyrimSideQuests.default
    traps: Traps = Traps.default
    trap_percentage: TrapPercentage = TrapPercentage.default
    quest_rewards: QuestRewards = QuestRewards.default
    death_link: DeathLink = DeathLink.default


# Starting bonuses (options attribute_<id> / skill_<id>): ids match the OpenMW
# Lua stat ids (scripts/ap/start_boost.lua).
ATTRIBUTE_KEYS = ('strength', 'intelligence', 'willpower', 'agility', 'speed', 'endurance', 'personality', 'luck')
SKILL_KEYS = ('acrobatics', 'alchemy', 'alteration', 'armorer', 'athletics', 'axe', 'block', 'bluntweapon', 'conjuration', 'destruction', 'enchant', 'handtohand', 'heavyarmor', 'illusion', 'lightarmor', 'longblade', 'marksman', 'mediumarmor', 'mercantile', 'mysticism', 'restoration', 'security', 'shortblade', 'sneak', 'spear', 'speechcraft', 'unarmored')


def start_bonuses(options) -> tuple:
    """({attribute id: bonus}, {skill id: bonus}), only the non-zero bonuses."""
    def collect(prefix, keys):
        out = {}
        for k in keys:
            v = int(getattr(getattr(options, f"{prefix}_{k}"), "value", 0))
            if v > 0:
                out[k] = v
        return out
    return collect("attribute", ATTRIBUTE_KEYS), collect("skill", SKILL_KEYS)


def start_option_groups() -> list:
    """Web UI groups for the attribute / skill bonus options."""
    from Options import OptionGroup
    mod = globals()
    return [
        OptionGroup("Starting attribute bonuses", [mod[f"Attribute{''.join(w.capitalize() for w in k.split('_'))}"] for k in ATTRIBUTE_KEYS]),
        OptionGroup("Starting skill bonuses", [mod[f"Skill{''.join(w.capitalize() for w in k.split('_'))}"] for k in SKILL_KEYS]),
    ]


def selected_goals(options) -> list:
    """Goals to complete: the main quest (if enabled, by default) +
    the chosen great house + the chosen guilds and factions (several allowed) + the
    daedric quests (if enabled) + the main quest of each expansion whose
    `<expansion>_main_quest` option is enabled (tribunal, bloodmoon)."""
    goals = []
    main = getattr(options, "main_quest", None)
    if getattr(main, "value", True if main is None else main):
        goals.append("main_quest")
    house = _clan_key(options, "great_house")
    if house != "none":
        goals.append(house)
    goals += _selected_keys(options, "guild", GUILD_KEYS)
    goals += _selected_keys(options, "faction", FACTION_KEYS)
    if getattr(options.daedric_quests, "value", options.daedric_quests):
        goals.append("daedric_quests")
    for exp in EXPANSIONS:
        if _enabled(options, f"{exp}_main_quest"):
            goals.append(exp)
    # Tamriel Rebuilt main quest: only integrated into the main quest goal.
    if "main_quest" in goals and _enabled(options, "tamriel_rebuilt_main_quest"):
        goals.append(TR_MAIN_GOAL)
    # Vampire clan (vanilla or Tamriel Rebuilt): a player belongs to ONE clan; its final quest is a goal.
    clan = _clan_key(options, "vampire_clan")
    if clan in VAMPIRE_CLANS or clan in TR_VAMPIRE_CLANS:
        goals.append(f"vampire_{clan}")
    return goals


# Quest group (tools/quest_groups.py) -> goal key (data/goals.yaml).
# House / guild / faction groups carry the name of their goal.
GROUP_GOALS = {"main": "main_quest", "daedric": "daedric_quests"}

# Tamriel Rebuilt (TR_Mainland.esm). Each TR quest belongs to ONE group:
#   tr_main      main quest (Foul Murder) -> goal TR_MAIN_GOAL, only with main_quest
#   tr_daedric   TR Daedric quests        -> goal daedric_quests
#   tr_<faction> TR quests of a house / guild / faction -> goal <faction>
#                (east_empire_company covers the TR EEC questline too: it is
#                enabled only when the `faction` option is east_empire_company)
#   tr_side      everything else          -> free checks
# Must stay in sync with tools/quest_groups.py (checked by tools/test_tamriel_rebuilt.py).
TR_MAIN_GOAL = "tamriel_rebuilt_main"
TR_FACTION_KEYS = (
    "hlaalu", "redoran", "telvanni", "indoril",
    "fighters_guild", "mages_guild", "thieves_guild",
    "imperial_cult", "imperial_legion", "temple", "morag_tong",
    "ja_natta_syndicate", "east_empire_company", "ordinators",
)
TR_VAMPIRE_CLANS = ("baluath", "orlukh")
TR_VAMPIRE_GROUPS = ("tr_vampire",) + tuple(f"tr_vampire_{c}" for c in TR_VAMPIRE_CLANS)
TR_GROUPS = ("tr_main", "tr_side", "tr_daedric") + TR_VAMPIRE_GROUPS + tuple(f"tr_{k}" for k in TR_FACTION_KEYS)

# Goals whose game data (faction id / rank) are not confirmed against the TR ESM:
# generation logs a warning (tools/list_tr.py --factions to check them).
# T_Mw_HouseIndoril / T_Mw_JaNattaSyndicate are verified (10 ranks each). The Ordinators
# faction id / rank count are NOT: run `python tools/set_goal_faction.py ordinators
# tamriel_data.json`, which reads them from the ESM and clears this line.
UNVERIFIED_GOALS = ("ordinators",)


# Project Cyrodiil (Cyr_Main.esm). Its factions are goals like the vanilla ones: the quests of a
# PC faction carry the group named after the goal key (PC_FACTION_KEYS, same as the guild / faction
# option choices), so they follow the usual goal logic (checks only if that faction is chosen).
# Every other PC quest is in the free group `pc_side` (option project_cyrodiil_side_quests).
# Must stay in sync with tools/quest_groups.py (checked by tools/test_project_cyrodiil.py).
PC_SIDE_GROUP = "pc_side"
PC_FACTION_KEYS = (
    "kingdom_of_anvil", "itinerant_priests",
    "cyrodiil_fighters_guild", "cyrodiil_mages_guild", "cyrodiil_thieves_guild",
)
PC_GROUPS = (PC_SIDE_GROUP,) + PC_FACTION_KEYS

# Skyrim: Home of the Nords (Sky_Main.esm): same scheme as Project Cyrodiil (guild groups named after the
# goal key, everything else in the free group `sky_side`). Keep in sync with tools/quest_groups.py.
SKY_SIDE_GROUP = "sky_side"
SKY_FACTION_KEYS = ("skyrim_fighters_guild", "skyrim_mages_guild", "hammerfell_mages_guild", "skyrim_thieves_guild")
SKY_GROUPS = (SKY_SIDE_GROUP,) + SKY_FACTION_KEYS


# Expansions and their quest categories (the East Empire Company faction is not
# here: it is the `faction` option). Each expansion quest belongs to ONE
# group "<expansion>_<category>" (tools/quest_groups.py); each group is
# enabled by its own option "<expansion>_<option suffix>".
EXPANSIONS = ("tribunal", "bloodmoon")
EXPANSION_CATEGORY_OPTIONS = {"main": "main_quest", "side": "side_quests"}
EXPANSION_GROUPS = tuple(f"{e}_{c}" for e in EXPANSIONS for c in EXPANSION_CATEGORY_OPTIONS)

# Quest groups that give checks without being a goal: Miscellaneous quests
# (always) and expansion quests (if the option of their group is enabled).
# Standalone quest category (not a goal, not a faction): the vanilla vampire clans. A player belongs
# to ONE clan, so each clan has its own group (enabled only if it is the chosen clan) next to the
# group of the quests open to any bloodline. The TR counterpart (tr_vampire*) is a TR group enabled
# by vampire_clan (baluath / orlukh / tamriel_rebuilt_unaligned).
VAMPIRE_CLANS = ("aundae", "berne", "quarra")
CATEGORY_GROUPS = ("vampire",) + tuple(f"vampire_{c}" for c in VAMPIRE_CLANS)

FREE_GROUPS = (("misc", "tr_side", PC_SIDE_GROUP, SKY_SIDE_GROUP) + TR_VAMPIRE_GROUPS + CATEGORY_GROUPS + EXPANSION_GROUPS)


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


def _selected_keys(options, name, order) -> list:
    """Keys chosen in a set option (guild, faction), in the fixed order of `order`."""
    chosen = {str(k) for k in (getattr(getattr(options, name, None), "value", None) or ())}
    return [k for k in order if k in chosen]


def _clan_key(options, name) -> str:
    opt = getattr(options, name, None)
    return str(getattr(opt, "current_key", "none") or "none")


def selected_category_groups(options) -> list:
    """Enabled vanilla vampire groups: the common one + the chosen clan's, e.g.
    ["vampire", "vampire_berne"]. Nothing if vampire_clan is none or a Tamriel Rebuilt clan."""
    key = _clan_key(options, "vampire_clan")
    if key != "unaligned" and key not in VAMPIRE_CLANS:
        return []
    return ["vampire"] + ([f"vampire_{key}"] if key in VAMPIRE_CLANS else [])


def selected_tr_groups(options) -> list:
    """Enabled Tamriel Rebuilt groups, e.g. ["tr_side", "tr_hlaalu"]."""
    goals = selected_goals(options)
    out = []
    if _enabled(options, "tamriel_rebuilt_side_quests"):
        out.append("tr_side")
    if TR_MAIN_GOAL in goals:
        out.append("tr_main")
    if "daedric_quests" in goals and _enabled(options, "tamriel_rebuilt_daedric_quests"):
        out.append("tr_daedric")
    clan = _clan_key(options, "vampire_clan")
    if clan in TR_VAMPIRE_CLANS or clan == "tamriel_rebuilt_unaligned":
        out.append("tr_vampire")
        if clan in TR_VAMPIRE_CLANS:
            out.append(f"tr_vampire_{clan}")
    if _enabled(options, "tamriel_rebuilt_factions"):
        out += [f"tr_{g}" for g in goals if g in TR_FACTION_KEYS]
    return out


def selected_pc_groups(options) -> list:
    """Enabled Project Cyrodiil groups that are NOT goal groups: ["pc_side"] or []."""
    return [PC_SIDE_GROUP] if _enabled(options, "project_cyrodiil_side_quests") else []


def selected_sky_groups(options) -> list:
    """Enabled Skyrim groups that are NOT goal groups: ["sky_side"] or []."""
    return [SKY_SIDE_GROUP] if _enabled(options, "skyrim_side_quests") else []


def group_enabled(options, group) -> bool:
    """True if a quest group is enabled in the seed.

    Used by quest locks that depend on more than their goal (e.g. the TR
    Daedric princes, group `tr_daedric`, need both `daedric_quests` and
    `tamriel_rebuilt_daedric_quests`). A lock without a group is always
    enabled (its goal alone gates it)."""
    if not group:
        return True
    return (group in selected_expansion_groups(options) or group in selected_tr_groups(options)
            or group in selected_category_groups(options) or group in selected_pc_groups(options)
            or group in selected_sky_groups(options))


def quest_rewards_enabled(options) -> bool:
    return _enabled(options, "quest_rewards")


def group_active(options, group) -> bool:
    """True if the checks of a quest group exist in the seed (free group,
    enabled expansion / Tamriel Rebuilt group, or selected goal)."""
    if group == "misc":
        return True
    if group in EXPANSION_GROUPS or group in TR_GROUPS or group in CATEGORY_GROUPS or group in (PC_SIDE_GROUP, SKY_SIDE_GROUP):
        return group_enabled(options, group)
    return goal_of_group(group) in selected_goals(options)


def goal_of_group(group: str) -> str:
    if group == "tr_main":
        return TR_MAIN_GOAL
    if group == "tr_daedric":
        return "daedric_quests"
    if group.startswith("tr_") and group[3:] in TR_FACTION_KEYS:
        return group[3:]
    return GROUP_GOALS.get(group, group)

class HintCost(Range):
    """Pourcentage du nombre total d'emplacements que coûte un indice."""
    display_name = "Hint Cost"
    range_start = 0
    range_end = 100
    default = 1  # Définir à 1 pour 1%
