# Morrowind Archipelago (OpenMW)

Play Morrowind under OpenMW as an [Archipelago](https://archipelago.gg) world: quests are the checks,
quest items, levels, faction requirements, filler and traps come from the multiworld.

## Contents

- [Overview](#overview)
- [Compatibility](#compatibility)
- [Requirements](#requirements)
- [Installation](#installation)
- [Player options](#player-options)
- [Objectives and checks](#objectives-and-checks)
- [Gameplay features](#gameplay-features): [starting bonuses](#starting-attribute-and-skill-bonuses) ·
  [filler and traps](#filler-and-traps) · [quest items](#quest-items-given-by-archipelago) ·
  [quest rewards](#quest-rewards-option-quest_rewards) · [Daedric quests](#daedric-quests-option-daedric_quests) ·
  [vampire clans](#vampire-clans-options-vampire_clan--tamriel_rebuilt_vampire_clan) ·
  [notifications](#in-game-notifications)
- [Content packs](#content-packs): [Tribunal / Bloodmoon](#tribunal-and-bloodmoon) ·
  [Tamriel Rebuilt](#tamriel-rebuilt) · [Project Cyrodiil](#project-cyrodiil) ·
  [Skyrim: Home of the Nords](#skyrim-home-of-the-nords)
- [Development](#development): [data generation](#data-generation) · [tests](#tests) · [quest item detection](#quest-item-detection)

## Overview

| Folder | Role |
|---|---|
| `apworld/` | Archipelago generation package (`morrowind_openmw`) |
| `mod/` | OpenMW mod (Lua, unsandboxed build via LuaJIT) |
| `bridge/` | Python client / relay (websocket <-> JSONL files) |
| `data/` | Location and item lists (source of truth) |
| `tools/` | ESM extraction, data generation, tests |

## Compatibility

| Mod | Support |
|---|---|
| Mods that add or modify **quests** | **Not compatible.** Quests, stages and journal IDs are extracted from the ESMs: a mod that adds a quest, moves a stage or changes an ending can prevent a check from triggering or skew an objective |
| Mods that modify gameplay (balancing, items, magic, travel, UI...) | Compatible, as long as they do not touch the quest journal. [Carry Unlimited](https://www.nexusmods.com/morrowind/mods/27479) is recommended |
| Tribunal / Bloodmoon | Optional (`tribunal_*` / `bloodmoon_*` options) |
| Tamriel Rebuilt | Optional (`tamriel_rebuilt_*` options) |
| Project Cyrodiil | Optional (`project_cyrodiil_side_quests`, `guild: cyrodiil_*`, `faction: kingdom_of_anvil / itinerant_priests`) |
| Skyrim: Home of the Nords | Optional (`skyrim_side_quests`, `guild: skyrim_* / hammerfell_mages_guild`) |

## Requirements

- OpenMW 0.52+ with unsandboxed LuaJIT (`unsandboxed` variant)
- Archipelago 0.6.8+
- Python 3.12+ with `websockets` and `pyyaml`

## Installation

1. Extract the game data once (see [Data generation](#data-generation), or run `./install.sh`).
2. Copy `mod/` into the OpenMW mods folder and enable `archipelago.omwscripts`.
3. Install the apworld: `python3 tools/install_apworld.py`.
4. Write a player YAML with `game: Morrowind OpenMW` (see `Morrowind-OpenMW.example.yaml`) and generate a seed.
5. Start the Archipelago server with the generated multidata.
6. Start OpenMW: the mod starts the Python bridge automatically.

**Connection settings** are in `mod/scripts/ap/config.lua` (host, port, slot, password, `data_dir`,
`auto_start_bridge`, deathlink). The bridge also reads `AP_HOST`, `AP_PORT`, `AP_SLOT`, `AP_PASSWORD`,
`AP_DATA_DIR` and `AP_DEATHLINK`.

Remember to **regenerate the seed** after updating the data or the apworld.

## Player options

```yaml
Morrowind OpenMW:
  # Objectives (see "Objectives and checks")
  main_quest: true             # false = the main quest is no longer an objective
  great_house: hlaalu          # none | hlaalu | redoran | telvanni | indoril (Tamriel Rebuilt)
  guild: mages_guild           # none | fighters_guild | mages_guild | thieves_guild
                               #      | cyrodiil_fighters_guild | cyrodiil_mages_guild | cyrodiil_thieves_guild (Project Cyrodiil)
                               #      | skyrim_fighters_guild | skyrim_mages_guild | hammerfell_mages_guild | skyrim_thieves_guild (Skyrim)
  faction: temple              # none | imperial_cult | imperial_legion | temple | morag_tong | east_empire_company (Bloodmoon)
                               #      | ja_natta_syndicate | ordinators (Tamriel Rebuilt) | kingdom_of_anvil | itinerant_priests (Project Cyrodiil)
  daedric_quests: true         # adds the 7 vanilla Daedric quests to the objective
  vampire_clan: none           # none | unaligned | aundae | berne | quarra

  # Expansions
  tribunal_main_quest: false   # Tribunal main quest: checks + goal
  tribunal_side_quests: false  # other Tribunal quests give checks
  bloodmoon_main_quest: false  # same two options for Bloodmoon
  bloodmoon_side_quests: false

  # Tamriel Rebuilt
  tamriel_rebuilt_main_quest: false
  tamriel_rebuilt_side_quests: false
  tamriel_rebuilt_factions: false
  tamriel_rebuilt_daedric_quests: false
  tamriel_rebuilt_vampire_clan: none   # none | unaligned | baluath | orlukh

  # Other content packs
  project_cyrodiil_side_quests: false
  skyrim_side_quests: false

  # Items
  quest_rewards: true          # unique quest rewards become locations + items
  traps: true                  # false = no trap items in the pool
  trap_percentage: 10          # 0-100: % of the filler slots turned into traps (if traps: true)
  death_link: true

  # Starting bonuses, 0-100 each (0 = vanilla): attribute_<id> and skill_<id>
  attribute_strength: 0
  skill_longblade: 0
```

## Objectives and checks

The default objective is the **main quest** (death of Dagoth Ur). The player YAML can remove it and/or add
any of the following, each optional: a great house, a guild, a faction, the Daedric quests, an
expansion main quest, a vampire clan.

**Victory** requires the main quest (if `main_quest` is enabled) **and** every chosen objective. With
`main_quest: false`, at least one other objective is required, otherwise generation stops with an error;
the main quest then stays freely playable, without Archipelago items or checks.

- **House / guild / faction**: reach rank 10 (leader). The mod prints `AP: rank <faction> = N` in the OpenMW
  log on every rank change.
- **Daedric quests**: the 7 vanilla quests (see [below](#daedric-quests-option-daedric_quests)).
- A completed objective stays completed (remembered in the save).
- Conditions live in `data/goals.yaml` (then `python tools/gen_lua.py`).

**Checks**

- Each *Miscellaneous* quest (UESP classification) gives a check at its end.
- **Each quest of the chosen objectives** (main quest, house / guild / faction, Daedric quests) also gives a
  check; quests of unchosen objectives stay ignored. These checks can hold progression, which makes several
  objectives possible. To stay feasible, each check requires **all** the items of its objective (the mod
  removes quest items until the AP item is received), and quests with an exclusive ending (`fail` in
  `data/quest_finals.yaml`) never hold important items. The items of the smallest objective must fit in the
  Miscellaneous quests; each completed objective then unlocks its own checks for the next one.
- A quest's group comes from its prefix (`tools/quest_groups.py`); exceptions go in
  `data/quest_groups_override.yaml`. The group `non_quest` (books, romances, town topics...) gives no check.
- The mod only sends a quest check if its group is enabled and its objective chosen
  (`goalChecks` in `mod/scripts/ap/player.lua`).
- If the seed cannot be filled (too many progression items for the available locations), generation stops
  with a message suggesting fewer objectives.
- There is no per-stage check, and no `goal_quest_checks` option any more: objective quest checks are always on.
- **Unsupported:** *Ahnassi, a Special Friend* (`Romance_Ahnassi`): its progression depends on the
  character's gender, so its completion cannot be detected reliably. It stays playable but gives no check.

## Gameplay features

### Starting attribute and skill bonuses

Each of the 8 attributes and 27 skills has its own option (`attribute_<id>`, `skill_<id>`), from 0 to 100
(default 0 = vanilla).

- Attributes: `strength`, `intelligence`, `willpower`, `agility`, `speed`, `endurance`, `personality`, `luck`.
- Skills: `acrobatics`, `alchemy`, `alteration`, `armorer`, `athletics`, `axe`, `block`, `bluntweapon`,
  `conjuration`, `destruction`, `enchant`, `handtohand`, `heavyarmor`, `illusion`, `lightarmor`, `longblade`,
  `marksman`, `mediumarmor`, `mercantile`, `mysticism`, `restoration`, `security`, `shortblade`, `sneak`,
  `spear`, `speechcraft`, `unarmored`.

The value is a **bonus** added to the stat chosen by the character (race, class, birthsign), not an absolute
value. Once the tutorial is over (journal `A1_1_FindSpymaster` reaches index 1: race, class and birthsign are
final), the mod applies **once** per save `new value = min(100, base + bonus)` to every stat with a non-zero
bonus (a value already above 100 is not lowered). The log shows `AP: starting bonuses applied`. Saves already
past the tutorial receive the bonuses the first time the mod connects.

The character level and health are **not** changed (the old `starting_level` option is removed).
`Level Up (+10)` and the faction `Requirements added` items remain additional.

### Filler and traps

The slots left once the real items are placed are filled by a **weighted random draw** (seeded by the
multiworld):

| Filler | Items |
|---|---|
| Gold | 100, 250 |
| Potions | healing, quality healing, magicka, fatigue |
| Soul gems | common, greater |
| Ammunition / tools | chitin arrows, steel arrows, lockpicks, probes |
| Food and drinks | bread, scrib jelly, comberry wine, local brew |

If `traps` is on, `trap_percentage` % of those slots (default 10) become traps, also drawn with weights:

| Trap | Effect |
|---|---|
| Damage | 90 % of max health, never lethal |
| Bounty | +1000 |
| Steal Gold | up to 250 gold |
| Drain Fatigue / Drain Magicka | stat set to 0 |
| Summon Scamp / Flame Atronach / Clannfear / Cliff Racers (x3) | hostile creatures next to the player |

Weights are in `FILLER` and `TRAPS` (`apworld/morrowind_openmw/items.py`). To add an item: a line in
`FILLER` / `TRAPS`, the matching entry in `GIVE` / `SUMMONS` / `DRAINS` (`mod/scripts/ap/items.lua`, same AP
id), then check that the record ids exist in the ESMs:

```sh
python3 tools/check_filler_records.py morrowind.json tribunal.json bloodmoon.json
```

### Quest items given by Archipelago

For the main quest (if enabled) and the chosen house / guild / faction, **all their quest items are
Archipelago items** (progression) placed in the Miscellaneous quests. The mod removes the copies the quests
would give (`suppress`) until the AP item is received, then gives the item (`give`) on receipt. Victory
requires being able to obtain all of them.

- **No duplicates.** If the AP item arrives *before* the vanilla copy is picked up, the mod limits the
  inventory to the quantity given by Archipelago (checked twice a second); the excess is removed
  (`AP: duplicate of <record> removed` in the log).
- Items of unchosen houses / guilds / factions are neither in the pool nor removed.
- Data: `data/quest_items.yaml` (`main_quest` is filled in; houses, guilds and factions are generated with
  `tools/gen_quest_items.py`, then `gen_lua.py` and `install_apworld.py`). The goal is only known to the mod
  once connected to the server: suppression starts then (the config is remembered in the save).

### Quest rewards (option `quest_rewards`)

When enabled, the **unique items** given as quest rewards (named weapons, armor, rings, books...) that are not
needed for progression are randomized:

- Each reward is an Archipelago **location** (`Reward: <item> @ <quest>`) and an **item** of the pool
  (`Reward: <item>`, *useful*), in the same group as its quest: that group must be enabled, and the location
  uses the same logic as the quest's checks.
- When the vanilla reward reaches your inventory, the mod **removes** it and sends the check
  (`AP: quest reward randomized: <record>`). The item is given back when the matching AP item is received.
- Ignored: gold, consumables (potions, ingredients, lights), items obtainable outside the quest (NPC,
  container, leveled list, cell), items required by a quest, and the progression items of
  `data/quest_items.yaml`. A quest with a failure branch never holds an important item.

Detection relies on the inventory (increase of the reward's count), confirmed at the next poll
(`poll_interval`) so that a copy given by Archipelago is not taken for the vanilla one.

Data: `data/quest_rewards.yaml`, generated from the ESMs:

```sh
python tools/gen_quest_rewards.py morrowind.json tribunal.json bloodmoon.json tr_mainland.json          # dry run
python tools/gen_quest_rewards.py morrowind.json tribunal.json bloodmoon.json tr_mainland.json --apply
python tools/gen_lua.py            # mod/scripts/ap/quest_rewards.lua
python tools/install_apworld.py    # copies the data into the apworld
```

Existing ids are kept when the file is regenerated.

### Daedric quests (option `daedric_quests`)

The 7 vanilla Daedric quests (`da_azura`, `da_boethiah`, `da_malacath`, `da_mehrunes`, `da_mephala`,
`da_molagbal`, `da_sheogorath`) join the objective. Each is **locked by a progression item**
(`Daedric Quest: <prince>`, `data/quest_locks.yaml`): until it is received, the mod resets the quest's
journal to zero (`AP: locked quest reset: ...`) and blocks the shrine activation. The 7 items are required
for victory. If the log shows `unable to lock`, your OpenMW version does not allow writing `quest.stage` from
the player script.

With `tamriel_rebuilt_daedric_quests` also enabled, four Tamriel Rebuilt princes join the objective and are
locked the same way (`Clavicus Vile`, `Sanguine`, `Meridia`, `Namira`; group `tr_daedric`). Their locks and
items only exist when **both** options are enabled. The Namira sub-journals (`tr_m7_da_nam_*`) are not locked
separately: the sanctuary script gates them behind `tr_m7_da_namira`.

### Vampire clans (options `vampire_clan` / `tamriel_rebuilt_vampire_clan`)

The vampire clans are a **category of their own** (not a house, guild or faction). Each quest gives a check
(a quest with a failure branch never holds an important item) and **the final quest of your clan is a goal**.

You belong to **ONE clan only** (vanilla: the clan of the vampire that infected you; Tamriel Rebuilt: Baluath
and Orlukh are enemies). The quests of the other clans are out of reach, so they give no check and are never
a goal. You choose your clan, and you must really join it in game.

| Option | Values | Checks | Goal (final quest) |
|---|---|---|---|
| `vampire_clan` | `none` (default), `unaligned`, `aundae`, `berne`, `quarra` | `vampire`: 7 quests open to any bloodline (`va_vampdust`, `va_shashev`, `va_rimintil`, `va_vampblood2`, `va_vamprich`, `va_vampmarara`, `va_vampcurse`); `vampire_<clan>`: 2 quests of the clan (Berne `va_vampblood`, `va_vampcountess`; Aundae `va_vampchild`, `va_vamphunter`; Quarra `va_vampcult`, `va_vampamulet`) | Aundae *The Vampire Hunter* (`va_vamphunter`), Berne *The Vampire Merta* (`va_vampcountess`), Quarra *The Quarra Amulet* (`va_vampamulet`) |
| `tamriel_rebuilt_vampire_clan` | `none` (default), `unaligned`, `baluath`, `orlukh` | `tr_vampire`: quests open to both (*Raenor's Revenge*); `tr_vampire_<clan>`: quests of the chosen clan | Baluath *Slay Orlukh Ancient* (`tr_m4_bal_killorlukh`), Orlukh *Namira's Shroud* (`tr_m4_va_namira`) |

- `unaligned` keeps only the common quests and adds **no goal**; `none` disables the category.
- A clan goal counts as an objective (`main_quest: false` with only a clan is valid) and is added to the
  other goals: **all** chosen goals must be completed. It is reached under the same condition as the check of
  its quest (alternative endings accepted, never a failure branch).
- The quest rewards of the enabled quests (clan amulets, Orlukh Amulet...) follow the same groups when
  `quest_rewards` is on.
- `TR_m4_VA_BarendrethProtection`, `_IbiNai` and `_VrashMind` are plain miscellaneous TR quests (`tr_side`).
- Independent of `tamriel_rebuilt_factions`.

**A Cure for Vampirism (`ms_vampirecure`) is disabled** as soon as a clan goal is selected (vanilla or Tamriel
Rebuilt): the cure removes the vampirism for good, which would make the final quest of your clan impossible.
The mod holds the quest at stage 0 (journal reset on every check, like a locked Daedric quest) and shows a
message once. The quest is classified `non_quest` (no check). With `unaligned` and no TR clan it stays
available. The list lives in `mod/scripts/ap/quest_forbidden.lua`.

### In-game notifications

Each Archipelago item **received** or **sent** by your slot displays an in-game message:

- `Archipelago: Bob sends you Ebony Dagger [Progression]`: item received from another player
- `Archipelago: Mothwing Cloak [Useful] (Fargoth's Ring) obtained -> Bob`: item from your world for another player
- `Archipelago: Ebony Dagger (Fargoth's Ring) obtained`: item from your world for you

The tag is the item's class (`[Progression]`, `[Useful]`, `[Trap]`). When the message matches a quest check,
the quest name is shown in parentheses. Locations use a readable name (UESP page title,
`data/quest_names.yaml`; derived from the ID when there is no UESP page; homonyms get a suffix) instead of
the journal ID (`MS_FargothRing`). Messages are spaced 2 s apart and also written to the OpenMW log
(`AP notification: ...`). The **Item notifications** setting (Archipelago page of the options menu) disables
them.

How it works: the bridge receives the `PrintJSON` `ItemSend` / `ItemCheat` messages, resolves names with the
datapackage (cached in `datapackage.json` of the `data_dir`) and writes a `{"t":"notify",...}` line to
`in.jsonl`. `global.lua` filters it (increasing id remembered in the save, nothing older than 10 min) and
relays it to the player script (`AP_Notify`). Items received while the game was closed are applied as usual,
without notification.

## Content packs

Everything below is **disabled by default**: a disabled option means no location, no goal, and the mod
ignores those quests. Enabling an option without its ESM loaded in `openmw.cfg` makes the seed impossible
to complete (the goal never triggers).

### Tribunal and Bloodmoon

Each expansion has two independent options:

| Option | Effect |
|---|---|
| `<expansion>_main_quest` | Checks for the main quest **and** it becomes a goal, so an expansion alone is enough to have a goal, even with `main_quest: false` |
| `<expansion>_side_quests` | Checks for every other quest of the expansion (never a goal) |

| Option | Goal quest | Reached when |
|---|---|---|
| `tribunal_main_quest` | The Mad God (`TR_SothaSil`) | stage 100: Almalexia is dead |
| `bloodmoon_main_quest` | Hircine's Hunt (`BM_WildHunt`) | stage 100: the Hunter is defeated |

Tribunal has no faction quests. The only Bloodmoon faction, the **East Empire Company** (Raven Rock colony), is
chosen with `faction: east_empire_company` like the other factions: goal = rank **Factor** (rank 9 in
`data/goals.yaml`), its quests give checks, and it requires `Bloodmoon.esm`. With `tamriel_rebuilt_factions`,
the same choice also enables the Tamriel Rebuilt East Empire Company questline (`tr_east_empire_company`).

- IDs and stages: `data/goals.yaml` (then `python tools/gen_lua.py`). No quest item is provided for these
  goals, and expansion quests never gate an item: the logic does not model access to Mournhold or Solstheim.
- Groups (`tools/quest_groups.py`, `data/expansion_categories.yaml`): Bloodmoon EEC quests ->
  `east_empire_company`; listed main quests -> `<expansion>_main`; the rest -> `<expansion>_side`.
  `quest_groups_override.yaml` accepts `tribunal_main`, `bloodmoon_side`... to move an exception. A journal
  belongs to an expansion if its ESM **defines** it (`data/quest_sources.yaml`, written by `tools/extract.py`).
- Quests with an exclusive ending (`fail`) and mutually exclusive journals (`data/quest_exclusive.yaml`,
  candidates: `tools/list_variants.py`) never hold an important item.
- After updating the data: `classify_quests.py`, `gen_lua.py`, `install_apworld.py`, then regenerate the seed.
  Location IDs of existing quests do not change.
- The log shows `AP: expansion groups = ...` and `AP: goals = ...` once connected.

### Tamriel Rebuilt

Requires `Tamriel_Data.esm` and `TR_Mainland.esm`.

| Option | Effect |
|---|---|
| `tamriel_rebuilt_main_quest` | The TR main quest (*Foul Murder*, epilogue of the Morrowind main quest) joins the main quest goal: checks **and** required to win. Ignored if `main_quest: false` |
| `tamriel_rebuilt_side_quests` | Checks for the TR miscellaneous quests (never a goal) |
| `tamriel_rebuilt_factions` | Checks for the TR quests of the `great_house` / `guild` / `faction` you chose (others ignored). They require the quest items of that goal, like the vanilla quests of the same faction |
| `tamriel_rebuilt_daedric_quests` | Checks for the TR Daedric quests, added to the Daedric goal. Ignored if `daedric_quests: false`. Each prince is locked by an AP item |
| `tamriel_rebuilt_vampire_clan` | See [Vampire clans](#vampire-clans-options-vampire_clan--tamriel_rebuilt_vampire_clan) |

New choices: `great_house: indoril` and `faction: ja_natta_syndicate` (`ja-natta_syndicate` is also accepted).
Goal: rank 10. Faction ids are verified in `Tamriel_Data.esm`: `T_Mw_HouseIndoril` (High Councilor) and
`T_Mw_JaNattaSyndicate` (Boss), 10 ranks each.

**Main quest goal.** The last journal of *Foul Murder*: `TR_NecMQ_3` at stage 200 (keeping the truth about
Nerevar). The earlier journals (`TR_NecMQ_2` / `TR_NecMQ_2Path`, the ringlet quests) are mutually exclusive
branches; requiring them all made the goal impossible. Stage 200 is the only successful ending (190 / 195 are
the Simine / Alvu-death softlocks). All `tr_main` quests still give checks.

**Classification** (`tools/quest_groups.py`, `data/tr_categories.yaml`). A journal `TR_m<N>_...` is a TR quest:
`tr_main` / `tr_daedric` (listed IDs), `tr_<faction>` (faction token in the ID: `HH` Hlaalu, `HT` Telvanni,
`TT` Temple, `JNS` Ja-Natta, `EEC` East Empire Company confirmed on UESP; `HR`, `FG`, `MG`, `TG`, `IL`, `IC`,
`MT` assumed), otherwise `tr_side`. A token may carry a number and a variant letter (`IC1`, `MG01`, `MG07a`).
The Foul Murder journals are recognised by the `tr_necmq_` prefix (`main_prefixes`).

**Other notes**

- No TR quest item is provided by Archipelago (like Tribunal).
- **Failure-only journals** (`TR_m1_FW_IC6_LoreFail`, `TR_m3_Aim_Dreugh1b`) are listed in `FAIL_ONLY`
  (`tools/gen_quest_finals.py`), written with `fail_only: true` and produce **no check**: `locations.py` drops
  them and `gen_lua.py` skips them. `TR_m4_Bal0_Troubles_A` is a real alternate ending (stage 200) and is
  treated as a normal completion.

**Ordinators** (`faction: ordinators`, Poison Song). A joinable faction with three questlines (Watch, War,
Doctrine: `TR_m3_Ord_Watch1-4`, `_War1-4`, `_Doc1-5`, `TR_m4_Ord_Rite`). Group `tr_ordinators` (token `ord`):
checks only with `tamriel_rebuilt_factions`, goal = leader rank, requirement item
`Ordinators Requirements added` (id 7701513); its quest rewards follow the same group.
**The faction id and rank count are not confirmed** (`Tamriel_Data.esm` of Poison Song): the goal ships as a
placeholder and generation logs a warning until you run:

```sh
python tools/list_tr.py tamriel_data.json --factions --grep ordinator
python tools/set_goal_faction.py ordinators tamriel_data.json [--pick <faction id>]
python tools/gen_lua.py && python tools/install_apworld.py
```

### Project Cyrodiil

Requires `Tamriel_Data.esm` and `Cyr_Main.esm` (Project Cyrodiil needs Tribunal, Bloodmoon and OpenMW 0.49+).
It is **not** an extension of Tamriel Rebuilt: its own journals (`PC_m<N>_<TOKEN>_...`), its own factions, and
**no main quest and no Daedric quest**.

| Option / choice | Effect |
|---|---|
| `guild: cyrodiil_fighters_guild` / `cyrodiil_mages_guild` / `cyrodiil_thieves_guild` | The guild becomes a goal (rank 10) and its quests give checks. Separate from the vanilla guilds: `guild` still holds ONE choice |
| `faction: kingdom_of_anvil` / `itinerant_priests` | Same for the Kingdom of Anvil and the Order of Itinerant Priests |
| `project_cyrodiil_side_quests` | Checks for every other Project Cyrodiil quest (never a goal) |

A chosen PC faction always contributes its quests as checks (no `project_cyrodiil_factions` toggle: these
factions have no vanilla counterpart). Each adds its `<faction> Requirements added` item (ids 7701514-7701518).
The goals have no quest items.

- **Classification** (`data/pc_categories.yaml`): the faction token (2nd or 3rd part after `m<N>`) gives the
  group: `ip` -> `itinerant_priests`, `k<N>` -> `kingdom_of_anvil`, `mg` / `fg` / `tg` -> `cyrodiil_*_guild`.
  Anything else (place tokens such as `PC_m1_Anv_WellMet`) is `pc_side`. Complete `faction_tokens` with what
  `list_tr.py --pc --journals` leaves in `pc_side`.
- **Goals**: the 5 faction ids in `data/goals.yaml` are verified in `Tamriel_Data.esm` (`T_Cyr_KingdomAnvil`,
  `T_Cyr_ItinerantPriests`, `T_Cyr_FightersGuild`, `T_Cyr_MagesGuild`, `T_Cyr_ThievesGuild`, 10 ranks each).
- **Generation guard**: selecting a PC goal or `project_cyrodiil_side_quests` while the apworld holds no PC
  quest data stops generation with an explicit message.
- **Mods**: like Tamriel Rebuilt, a patch that edits these quests is not supported. Sub-journals sharing one
  UESP page (`PC_m1_IP_Run1LE`, `..._Run1LV`, `..._Run1TT`...) are separate journals: `gen_quest_finals.py` /
  `data/quest_review.txt` decide which completes the quest, and exclusive branches go in
  `data/quest_exclusive.yaml`. *Culture Shock* has two ids (`..._Als2_LoanBuy` / `..._LoanSteal`): check them in
  `quest_review.txt`.

**Data** is not shipped in `data/` (IDs come from the ESM):

```sh
tes3conv Cyr_Main.esm cyr_main.json            # the file name must contain "cyr_main"
tes3conv Tamriel_Data.esm tamriel_data.json    # if not done yet
python tools/extract.py morrowind.json tribunal.json bloodmoon.json tr_mainland.json cyr_main.json --out data/
# then gen_quest_finals.py / classify_quests.py / gen_lua.py / install_apworld.py as in "Data generation"
python tools/list_tr.py cyr_main.json --pc --journals                         # check groups and tokens
python tools/list_tr.py cyr_main.json tamriel_data.json --factions --grep cyr  # faction ids + ranks
```

`install.sh` converts `Cyr_Main.esm` automatically when found (`PC_DATA=... ./install.sh`).

### Skyrim: Home of the Nords

Requires `Tamriel_Data.esm` and `Sky_Main.esm` (version 23.02 or later). Same scheme as Project Cyrodiil: the
mod has **no main quest and no Daedric quest**; its journals (`Sky_qRe_<place><token><n>[a-d]_Journal`) are
classified by the token after the place (`KW` Karthwasten, `DS` / `DSE` / `DSW` Dragonstar).

| Option / choice | Effect |
|---|---|
| `guild: skyrim_fighters_guild` / `skyrim_mages_guild` / `hammerfell_mages_guild` / `skyrim_thieves_guild` | The guild becomes a goal (rank 10) and its quests give checks. Separate from the vanilla guilds. `hammerfell_mages_guild` is the Dragonstar branch (`DSMG`), `skyrim_mages_guild` the Karthwasten one (`KWMG`) |
| `skyrim_side_quests` | Checks for every other quest: bounties (`KW_B04`, `KWB03`...), the Dragonstar arena (`DSE4`), miscellaneous quests (`KW1`, `KW2`, `KW8`, `DSW2`...) |

Each chosen guild adds its `<guild> Requirements added` item (ids 7701519-7701522).

- **Classification** (`data/sky_categories.yaml`): `^sky_qre_kwmg` -> Skyrim Mages Guild, `^sky_qre_dsmg` ->
  Hammerfell Mages Guild, `^sky_qre_(kw|ds[ew]?)tg` -> Thieves Guild, `^sky_qre_(kw|ds[ew]?)fg` -> Fighters
  Guild, `^sky_mg_` -> Skyrim Mages Guild (`Sky_MG_Advancement`); all verified on the ESM. Everything else is
  `sky_side`. Add patterns under `faction_patterns` for IDs that `list_tr.py --sky --journals` leaves there.
- **Goals**: verified in `Tamriel_Data.esm` (10 ranks, rank 10 = leader): `T_Sky_FightersGuild`,
  `T_Sky_MagesGuild`, `T_Sky_ThievesGuild`, and `T_Ham_MagesGuild` for `hammerfell_mages_guild`.
- **Branches**: lettered sub-journals (`KWMG5a/b/c`, `DSMG4a/b/c`, `KWTG8a/b/c`, `KW1a-d`: Direnni codexes) are
  separate journals: read `data/quest_review.txt` and put the real alternatives in `data/quest_exclusive.yaml`.

**Data** is not shipped in `data/`:

```sh
tes3conv Sky_Main.esm sky_main.json            # the file name must contain "sky_main"
tes3conv Tamriel_Data.esm tamriel_data.json    # if not done yet
python tools/extract.py morrowind.json tribunal.json bloodmoon.json tr_mainland.json cyr_main.json sky_main.json --out data/
python tools/list_tr.py sky_main.json --sky --journals                         # check the groups
python tools/list_tr.py sky_main.json tamriel_data.json --factions --grep sky  # faction ids + ranks
```

`install.sh` converts `Sky_Main.esm` automatically (`SKY_DATA=... ./install.sh`, or 5th argument).

## Development

### Data generation

```sh
tes3conv Morrowind.esm morrowind.json
tes3conv Tribunal.esm  tribunal.json     # optional (tribunal_* options)
tes3conv Bloodmoon.esm bloodmoon.json    # optional (bloodmoon_* options)

# 1. quests (existing IDs are kept, new ones are added). The JSON file names must contain
#    "tribunal" / "bloodmoon": a journal's group comes from the ESM that defines it (data/quest_sources.yaml)
python tools/extract.py morrowind.json tribunal.json bloodmoon.json --out data/
# 2. completion stage of new quests (existing entries are kept)
python tools/gen_quest_finals.py morrowind.json tribunal.json bloodmoon.json
#    -> check data/quest_review.txt (quests with several endings: add overrides / fail)
# 2b. quest items of the other objectives (candidates to review: data/quest_items_candidates.yaml)
#     bloodmoon.json is needed for the East Empire Company items; tribunal.json is not
python tools/gen_quest_items.py morrowind.json bloodmoon.json --apply
# 3. groups (main / factions / daedric / misc ...) + report data/quest_groups_report.txt
python tools/classify_quests.py
# 4. Lua tables (quest_completions.lua, goals.lua, ...)
python tools/gen_lua.py
# 5. apworld
python tools/install_apworld.py
```

Quest locations carry the readable name from `data/quest_names.yaml` (UESP page titles); quests missing from
the table get a name derived from their ID. **Location IDs are stable**: re-running the extraction breaks
neither seeds nor the existing Lua tables.

`./install.sh <Data Files> [TR dir [Tamriel_Data dir [Cyr_Main dir]]]` runs this whole pipeline (optional
variables `MW_DATA`, `TR_DATA`, `TD_DATA`, `PC_DATA`, `SKY_DATA`, `TES3CONV`, `PYTHON`, `AP_DATA_DIR`) and copies
`bridge.py` to `~/.local/share/openmw/ap/`.

### Tests

From the repository root (Python) and from `mod/` (Lua, any Lua 5.3+ or LuaJIT, e.g. `lua ../tools/test_x.lua`):

| Area | Test |
|---|---|
| Quest groups, locks, names | `tools/test_quest_groups.py`, `test_quest_locks.py`, `test_quest_names.py` |
| Goals and options | `tools/test_selected_goals.py`, `test_expansion_options.py` |
| Vampire clans | `tools/test_vampire_options.py`, `test_quest_forbidden.lua` |
| Filler and traps | `tools/test_filler_traps.py`, `test_filler_traps.lua` |
| Tamriel Rebuilt / Project Cyrodiil / Skyrim | `tools/test_tamriel_rebuilt.py`, `test_project_cyrodiil.py`, `test_skyrim.py` |
| Quest rewards, item detection | `tools/test_quest_rewards.py`, `test_script_effects.py` |
| Exclusive branches, Daedric locks, level-up | `tools/test_exclusive.lua`, `test_daedric_lock.lua`, `test_level_up.lua` |
| Notifications, liveness, Census package | `tools/test_bridge_notify.py`, `test_notify.lua`, `test_liveness.lua`, `test_census_package.lua` |
| UESP scraper | `tools/test_scrape_uesp_finals.py` |

### Quest item detection

`tools/gen_quest_items.py` and `tools/script_effects.py` parse scripts and dialogue results **by block**
(`if / elseif / else`): an item handed over in a branch is attributed to the journal changed in that same
branch, and journal sub-ids (`TR_M3_AT_DEED_C`) resolve to their quest. Only `Player->RemoveItem` /
`Player->GetItemCount` (also inside `if (...)` conditions) count; the same commands on an NPC do not.

A required item that is generic stock (`sc_*`, `ingred_*`, `misc_de_*`...) or placed more than
`--max-placements` times in the world is **not** a quest item (any copy would do, and suppressing the record
would remove all of them). `python tools/gen_quest_items.py morrowind.json --prune [--apply]` lists / removes
the existing entries of `data/quest_items.yaml` that fail this test.

Exclusive branches: `tools/gen_variant_exclusive.py` (`_a/_b` naming). UESP pages listing several journals are
usually multi-part quests (all parts complete), NOT branches: the quest tree cannot be used to derive
exclusive groups.
