# Morrowind Archipelago (OpenMW)

Archipelago mod to play Morrowind under OpenMW as an Archipelago world.

## Components

- `apworld/`: Archipelago generation package (`morrowind_openmw`)
- `mod/`: OpenMW mod (Lua, unsandboxed build via LuaJIT)
- `bridge/`: Python client/relay (websocket <-> JSONL files)
- `data/`: location/item lists (source of truth)
- `tools/`: ESM extraction, data generation

## Compatibility

- **Mods that add or modify game quests: not compatible.** Quests, their stages and their
  journal IDs are extracted from `Morrowind.esm`; a mod that adds a quest, moves a stage or
  changes the ending of an existing quest can prevent the corresponding check from triggering
  or skew the objective.
- **Tamriel Rebuilt: optional** (`tamriel_rebuilt_*` options, see below).
- **Tribunal / Bloodmoon: optional** (`tribunal_*` / `bloodmoon_*` options, see below).
- **Mods that modify gameplay: compatible**, as long as they do not touch the quest journal
  (balancing, items, magic, travel, UI, etc.). For example
  [Carry Unlimited](https://www.nexusmods.com/morrowind/mods/27479), which increases carrying
  capacity, is recommended.

## Requirements

- OpenMW 0.52+ with unsandboxed LuaJIT (`unsandboxed` variant)
- Archipelago 0.6.8+
- Python 3.12+ with `websockets`, `pyyaml`

## Data extraction (ESM)

```sh
tes3conv Morrowind.esm morrowind.json
tes3conv Tribunal.esm  tribunal.json     # optional (tribunal_* options)
tes3conv Bloodmoon.esm bloodmoon.json    # optional (bloodmoon_* options)

# 1. quests (existing IDs are kept, new ones are added). The JSON file names must
#    contain "tribunal" / "bloodmoon": the group of a journal comes from the ESM
#    that defines it (data/quest_sources.yaml).
python tools/extract.py morrowind.json tribunal.json bloodmoon.json --out data/
# 2. completion stage for new quests (existing entries are kept)
python tools/gen_quest_finals.py morrowind.json tribunal.json bloodmoon.json
#    -> check data/quest_review.txt (quests with multiple endings: add overrides/fail)
# 2b. quest items for other objectives (candidates to review: data/quest_items_candidates.yaml)
#    bloodmoon.json is needed for the East Empire Company items (faction: east_empire_company);
#    tribunal.json is not (no Tribunal goal has quest items). Without bloodmoon.json it still runs,
#    but that faction then has no items.
python tools/gen_quest_items.py morrowind.json bloodmoon.json --apply
# 3. groups (main / factions / daedric / misc ...) + report data/quest_groups_report.txt
python tools/classify_quests.py
# 3b. canonical quest tree (see the section below): update it with the new extraction
python tools/rebase_quest_tree.py
# 4. Lua tables (quest_completions.lua, goals.lua, ...) + data/*.yaml from the tree
python tools/gen_lua.py
# 5. apworld
python tools/install_apworld.py
```

Quest locations carry the readable quest name (`data/quest_names.yaml` table,
UESP page titles). Quests missing from the table get a name derived from their ID.

Location IDs are stable: re-running extraction breaks neither seeds nor
existing Lua tables. Remember to regenerate the seed after updating.

## Canonical quest tree (`data/quest_tree.json`)

`data/quest_tree.json` is the single source of truth for the quests, their
faction/group, their **successful and failing** endings, and the quest items /
unique rewards. It is built from the UESP quest tree
(`tools/scrape_uesp_quest_tree.py`) and enriched with the ESM extraction
(`data/*.yaml`) plus the manual `data/quest_groups_override.yaml`.

```sh
# 1. rebuild the canonical tree from a raw UESP scrape (first time / new scrape)
python tools/rebase_quest_tree.py --from-raw
#    ... or update it in place after a new ESM extraction (default when
#    data/quest_tree.json exists)
python tools/rebase_quest_tree.py
# 2. derive data/*.yaml and the Lua tables from the canonical tree
python tools/gen_lua.py --tree data/quest_tree.json --tree-sync-yaml
# 3. apworld
python tools/install_apworld.py
```

`tools/gen_lua.py` defaults to `data/quest_tree.json` when it exists
(`--no-tree` restores the legacy YAML-only pipeline). `--tree-sync-yaml` writes
`quest_completions.yaml`, `quest_finals.yaml`, `quest_items.yaml` and
`quest_rewards.yaml` from the tree, so the apworld and the Lua always agree.
The readable names stay in the curated `data/quest_names.yaml` (they are copied
into the tree as `loc_names`). `python tools/gen_data_from_tree.py --check`
validates the tree without writing anything.

| Tree field | Meaning |
|---|---|
| `ids` | journals attached to a UESP page |
| `completion_stages[journal]` | successful ending stages (UESP; the tree wins) |
| `fail[journal]` | failing stages (ESM, `quest_finals.yaml`) |
| `groups[journal]` | faction / group: override > UESP faction line > journal prefix |
| `loc_ids`, `loc_names`, `regions` | stable Archipelago location identity |
| `needs_item_meta` | progression item rows (all goal variants of a record) |
| `rewards_meta` | unique reward rows (one per quest using a shared record) |

Journals known to the ESM but absent from UESP are stored under the
`_esm_only` line, so no existing check disappears when switching to the tree.
The generated `quest_completions/finals/items/rewards.yaml` are not committed;
`quest_tree.json` and the curated files (`quest_names.yaml`, goals, locks,
overrides) are. Archipelago ids stay stable across re-runs.

## Objective and checks

The default objective is the **main quest** (death of Dagoth Ur). In the player YAML
(see `Morrowind-OpenMW.example.yaml`) you can remove it and/or add, each optional:

```yaml
Morrowind OpenMW:
  main_quest: true             # false = the main quest is no longer an objective
  great_house: hlaalu          # none | hlaalu | redoran | telvanni | indoril (Tamriel Rebuilt)
  guild: mages_guild           # none | fighters_guild | mages_guild | thieves_guild
  faction: temple              # none | imperial_cult | imperial_legion | temple | morag_tong | east_empire_company | ja_natta_syndicate
  daedric_quests: true         # adds the 7 vanilla Daedric quests to the objective
  traps: true                  # false = no trap items in the pool
  attribute_strength: 0        # 0-100: starting bonus per attribute (see below)
  skill_longblade: 0           # 0-100: starting bonus per skill (see below)
  tribunal_main_quest: false       # true = Tribunal main quest: checks + goal
  tribunal_side_quests: false      # true = other Tribunal quests give checks
  bloodmoon_main_quest: false      # same two options for Bloodmoon
  bloodmoon_side_quests: false
```

Victory requires the main quest (if `main_quest` is enabled) **and** each chosen house / guild /
faction (and, if enabled, the 7 vanilla Daedric quests) to be completed. With `main_quest: false`, at
least one other objective is required, otherwise generation stops with an error message; the main
quest remains freely playable, without Archipelago items or checks. For a house, guild or faction,
this means reaching rank 10 (leader): the mod prints
`AP: rank <faction> = N` in the OpenMW log on every rank change. A completed objective stays
completed (remembered in the save). Conditions are set in `data/goals.yaml`
(then `python tools/gen_lua.py`).

**Checks.** Each "Miscellaneous" quest (UESP) gives a check at its end. With the option
`goal_quest_checks` (default `true`), **completing each quest of the chosen objectives** (main
quest, house / guild / faction, Daedric quests) also gives a check. Quests of unchosen
objectives, vampires, etc. remain ignored.

```yaml
  goal_quest_checks: true      # true | false
```

- `false`: only Miscellaneous quests give checks.
- `true`: these checks can contain progression, which makes it possible to choose several
  objectives. To stay feasible: each check requires **all** the items of its objective (the mod
  removes quest items until the AP item is received; we do not know which one is used for which
  quest), and quests with an exclusive ending (`fail` in `data/quest_finals.yaml`) never contain
  important items. The items of the smallest objective must fit in the Miscellaneous quests,
  then each completed objective unlocks its own checks for the next one.

## Starting attribute and skill bonuses (options `attribute_<id>` and `skill_<id>`)

Each of the 8 attributes and 27 skills has its own option, from 0 to 100 (default 0 = vanilla):

- attributes: `attribute_strength`, `attribute_intelligence`, `attribute_willpower`,
  `attribute_agility`, `attribute_speed`, `attribute_endurance`, `attribute_personality`,
  `attribute_luck`;
- skills: `skill_acrobatics`, `skill_alchemy`, `skill_alteration`, `skill_armorer`,
  `skill_athletics`, `skill_axe`, `skill_block`, `skill_bluntweapon`, `skill_conjuration`,
  `skill_destruction`, `skill_enchant`, `skill_handtohand`, `skill_heavyarmor`, `skill_illusion`,
  `skill_lightarmor`, `skill_longblade`, `skill_marksman`, `skill_mediumarmor`,
  `skill_mercantile`, `skill_mysticism`, `skill_restoration`, `skill_security`,
  `skill_shortblade`, `skill_sneak`, `skill_spear`, `skill_speechcraft`, `skill_unarmored`.

The value is a **bonus** added to the stat chosen by the character (race, class, birthsign), not
an absolute value. Once the tutorial is over, i.e. when the journal reaches `A1_1_FindSpymaster`
index 1 (Sellus Gravius gave the package, race, class and birthsign are final), the mod applies
**once** per save `new value = min(100, base + bonus)` to every stat with a non-zero bonus (a
value already above 100 is not lowered). The log shows `AP: starting bonuses applied`.

Existing saves that are already past the tutorial receive the bonuses the first time the mod
connects. The character level is **not** changed (the old `starting_level` option is removed), and
neither is the health. `Level Up (+10)` and skill items remain additional.

## Expansions (`tribunal_*` and `bloodmoon_*` options)

Each expansion has **two independent options**:

| Option | Effect |
|---|---|
| `<expansion>_main_quest` | Checks for the main quest **and** the main quest becomes a goal (like the great house or guild goals), so an expansion alone is enough to have a goal, even with `main_quest: false` |
| `<expansion>_side_quests` | Checks for every other quest of the expansion (never a goal) |

Tribunal has no faction quests. The only Bloodmoon faction, the **East Empire Company**
(Raven Rock colony), is chosen with `faction: east_empire_company` like the other factions: goal =
rank **Factor** (`east empire company`, rank 9 in `data/goals.yaml`), its quests give checks, and
it requires `Bloodmoon.esm`. With `tamriel_rebuilt_factions`, the same choice also enables the
Tamriel Rebuilt East Empire Company questline (group `tr_east_empire_company`).

Goal quest of each `<expansion>_main_quest`:

| Option | Goal quest | Reached when |
|---|---|---|
| `tribunal_main_quest` | The Mad God (`TR_SothaSil`) | stage 100: Almalexia is dead |
| `bloodmoon_main_quest` | Hircine's Hunt (`BM_WildHunt`) | stage 100: the Hunter is defeated |

IDs and stages are in `data/goals.yaml` (then `python tools/gen_lua.py`). No quest item is
provided by Archipelago for these goals, and expansion quests never gate an item: the logic
does not model access to Mournhold or Solstheim, so these checks are considered always reachable.

- `Tribunal.esm` / `Bloodmoon.esm` must be loaded in `openmw.cfg` for the quests to exist. Enabling
  an option without its DLC makes the seed impossible to complete: the goal never triggers.
- Disabled (default): no location, no goal, and the mod ignores the quests of that category, even
  if the DLC is loaded.
- Category of a quest (`tools/quest_groups.py`, `data/expansion_categories.yaml`): Bloodmoon EEC
  quests -> group `east_empire_company`; listed main quests -> `<expansion>_main`; the rest ->
  `<expansion>_side`. `quest_groups_override.yaml` accepts `tribunal_main`, `bloodmoon_side`... to move
  an exception.
- Quests with an exclusive ending (`fail` in `data/quest_finals.yaml`) and mutually exclusive journals
  (`data/quest_exclusive.yaml`, candidates: `tools/list_variants.py`) never hold an important item.
- Data: a journal belongs to an expansion if it is **defined** by its ESM (`data/quest_sources.yaml`,
  written by `tools/extract.py`); `quest_groups_override.yaml` can still move an exception. After
  updating the data, run `classify_quests.py`, `gen_lua.py`, `install_apworld.py`, then
  regenerate the seed. Location IDs of existing quests do not change.
- The log shows `AP: expansion groups = tribunal_main, bloodmoon_side...` and `AP: goals = ...` once connected.

The only unsupported side quest is **"Ahnassi, a Special Friend"** (`Romance_Ahnassi`),
because its progression depends on the character's gender (*gender gated*), which prevents
reliable detection of its completion. It remains playable, but gives no check.

There is no longer a check per journal stage (old `quest_granularity: stage` option, removed),
nor a `safe` mode (`goal_quest_checks: safe` is now `true`, which corresponds to the old `full`).

If the seed cannot be filled (too many progression items for the available locations),
generation stops with a message suggesting `goal_quest_checks: true` or fewer objectives.
The mod only sends an objective quest check if the option is enabled and the objective chosen
(`mod/scripts/ap/goal_checks.lua`).

A quest's group is determined by its prefix
(`tools/quest_groups.py`); exceptions go in `data/quest_groups_override.yaml`.
Daedric quests only contribute to the objective and checks when `daedric_quests` is enabled.

## Daedric quests (option `daedric_quests`)

When the option is enabled, the 7 vanilla Daedric quests (`da_azura`, `da_boethiah`,
`da_malacath`, `da_mehrunes`, `da_mephala`, `da_molagbal`, `da_sheogorath`) are added to the
objective. Each is **locked by an Archipelago item** (`Daedric Quest: <prince>`, see
`data/quest_locks.yaml`): until it is received, the mod resets the quest's journal to zero (log
`AP: locked quest reset: ...`), so it can neither advance nor be completed. The 7 items are
progression, required for victory. If the log shows `unable to lock`, the OpenMW API in your
version does not allow modifying `quest.stage` from the player script.

With `tamriel_rebuilt_daedric_quests` also enabled, four Tamriel Rebuilt princes join the
objective and are locked the same way (`Daedric Quest: Clavicus Vile`, `Sanguine`, `Meridia`,
`Namira`; group `tr_daedric`). Their locks and items only exist when **both** options are
enabled. The Namira sub-journals (`tr_m7_da_nam_*`) are not locked separately: the sanctuary
script gates them behind the main `tr_m7_da_namira` journal.

## Tamriel Rebuilt (`tamriel_rebuilt_*` options)

Requires `Tamriel_Data.esm` and `TR_Mainland.esm` in `openmw.cfg`. All options are disabled by
default; a disabled option means no location, no goal, and the mod ignores those quests.

| Option | Effect |
|---|---|
| `tamriel_rebuilt_main_quest` | The TR main quest (*Foul Murder*, epilogue of the Morrowind main quest) is added to the main quest goal: checks **and** it must be completed to win. Ignored if `main_quest: false` |
| `tamriel_rebuilt_side_quests` | Checks for the TR miscellaneous quests (never a goal) |
| `tamriel_rebuilt_factions` | Checks for the TR quests of the `great_house` / `guild` / `faction` you chose (unchosen ones are ignored). They require the quest items of that goal, like the vanilla quests of the same faction |
| `tamriel_rebuilt_daedric_quests` | Checks for the TR Daedric quests, added to the Daedric goal. Ignored if `daedric_quests: false`. Each prince is **locked by an AP item** (`Daedric Quest: <prince>`) when both options are enabled |

New choices: `great_house: indoril` and `faction: ja_natta_syndicate` (`ja-natta_syndicate` is also
accepted). Goal: rank 10 (`data/goals.yaml`). The faction IDs are verified in `Tamriel_Data.esm`:
`T_Mw_HouseIndoril` (High Councilor) and `T_Mw_JaNattaSyndicate` (Boss), 10 ranks each.

The main-quest goal is the last journal of *Foul Murder*: `TR_NecMQ_3` at stage 200 (keeping the
truth about Nerevar). The earlier journals (`TR_NecMQ_2` / `TR_NecMQ_2Path`, the ringlet quests)
are mutually exclusive branches; requiring them all, as the old `tr_main` group goal did, made the
goal impossible. Stage 200 is the only successful ending: stages 190/195 are the Simine/Alvu-death
softlocks. All the `tr_main` quests still give checks.

**Status: data still to generate.** TR quests are not shipped in `data/`: IDs come from the ESM.

```sh
tes3conv Tamriel_Data.esm tamriel_data.json
tes3conv TR_Mainland.esm  tr_mainland.json     # the file name must contain "tr_mainland"
python tools/extract.py morrowind.json tribunal.json bloodmoon.json tr_mainland.json --out data/
# then gen_quest_finals.py / classify_quests.py / gen_lua.py / install_apworld.py as above
python tools/list_tr.py tr_mainland.json --factions --grep indoril   # faction id + ranks
python tools/list_tr.py tr_mainland.json --journals                  # check the groups
```

1. **Classification.** A journal `TR_m<N>_...` is a TR quest. Its group (`tools/quest_groups.py`):
   `tr_main` / `tr_daedric` (IDs listed in `data/tr_categories.yaml`), `tr_<faction>` (faction token
   in the ID: `HH` Hlaalu, `HT` Telvanni, `TT` Temple, `JNS` Ja-Natta, `EEC` East Empire Company
   confirmed on UESP; `HR`, `FG`, `MG`, `TG`, `IL`, `IC`, `MT` assumed), else `tr_side`. A faction
   token may carry a number and a variant letter (`IC1`, `MG01`, `TG1`, `MG07a`). The Foul Murder
   journals are recognised by the `tr_necmq_` prefix (`main_prefixes` in `data/tr_categories.yaml`).
2. **Goals.** The faction ids/ranks of `indoril` / `ja_natta_syndicate` are verified against
   `Tamriel_Data.esm` (see above), so generation no longer warns about them. The main-quest goal is
   `TR_NecMQ_3` stage 200, not the whole `tr_main` group.
3. No TR quest item is provided by Archipelago (like Tribunal).
4. **Failure-only journals.** Some TR journals only ever record a failure (the alternate *The Star
   Wound* journal `TR_m1_FW_IC6_LoreFail`, and `TR_m3_Aim_Dreugh1b` for *Finding Jelyn the Sailor*).
   They are listed in `FAIL_ONLY` (`tools/gen_quest_finals.py`), written with `fail_only: true`
   (stage 0, no completion stage) and produce **no check**: a location that can never fire is
   dropped by `locations.py` and `gen_lua.py` skips them. `TR_m4_Bal0_Troubles_A` (*Troubles on the
   Road*) is a real alternate ending (stage 200) and is treated as a normal completion.

Tests: `python3 tools/test_tamriel_rebuilt.py`.

## Quest rewards (option `quest_rewards`)

When enabled, the **unique items** given as quest rewards (named weapons, armor, rings, books...)
that are not needed for progression are randomized:

- each reward is an Archipelago **location** (`Reward: <item> @ <quest>`) and an **item** of the pool
  (`Reward: <item>`, *useful*), in the same group as its quest: the quest's goal, expansion or
  Tamriel Rebuilt group must be enabled, and the location uses the same logic as the quest's checks;
- when the vanilla reward reaches your inventory (its quest has reached the stage that gives it),
  the mod **removes** it and sends the check (log `AP: quest reward randomized: <record>`). The item
  is given back when the matching Archipelago item is received, wherever it was placed;
- gold, consumables (potions, ingredients, lights) and items that can also be obtained outside the
  quest (carried by an NPC / container / leveled list, or placed in a cell) are ignored; so are
  items required by a quest (handed over, required by a dialogue, counted) and the progression
  items of `data/quest_items.yaml`. A quest with a failure branch never holds an important item.

Detection is based on the inventory (increase of the reward's count): an increase is confirmed at
the next poll (`poll_interval`) so that a copy given by Archipelago is not taken for the vanilla one.
Once the check is sent, the item is no longer watched.

Data: `data/quest_rewards.yaml` (empty by default), generated from the ESMs:

```
python tools/gen_quest_rewards.py morrowind.json tribunal.json bloodmoon.json tr_mainland.json        # dry run
python tools/gen_quest_rewards.py morrowind.json tribunal.json bloodmoon.json tr_mainland.json --apply
python tools/gen_lua.py            # mod/scripts/ap/quest_rewards.lua
python tools/install_apworld.py    # copies the data into the apworld
```

Existing ids are kept when the file is regenerated. Test: `python3 tools/test_quest_rewards.py`.

## Quest items given by Archipelago

For the main quest (if `main_quest` is enabled) and the chosen house / guild / faction, **all
their quest items are Archipelago items** (progression) placed in the Miscellaneous quests. The
mod removes the copies that the quests would give (`suppress`) until the AP item is received,
then gives the item (`give`) upon receipt. Victory requires being able to obtain all of them.

**No duplicates.** If the AP item is received *before* the copy lying in the world is picked up
(the AP copy is then already in the inventory), the vanilla copy is no longer suppressed. The mod
therefore limits the inventory to the quantity given by Archipelago for every received quest item
(checked twice a second): the excess is removed (`AP: duplicate of <record> removed` in the log).
The items of unchosen houses / guilds / factions are neither in the pool nor removed.

They are described in `data/quest_items.yaml` (`main_quest` is filled in; houses, guilds and
factions are generated from the ESM with `tools/gen_quest_items.py`, then `gen_lua.py` and
`install_apworld.py`). The goal is only known to the mod once connected to the server:
suppression only starts at that point (the config is then remembered in the save).

## In-game notifications

Each Archipelago item **received** or **sent** by your slot displays an in-game message:

- `Archipelago: Bob sends you Ebony Dagger [Progression]` (item received from another player)
- `Archipelago: Mothwing Cloak [Useful] (Fargoth's Ring) obtained -> Bob` (item from your world for another player)
- `Archipelago: Ebony Dagger (Fargoth's Ring) obtained` (item from your world for you)

When the message corresponds to a quest check, the quest name is displayed in parentheses.
Archipelago locations use this readable name (UESP page title, `data/quest_names.yaml` table)
instead of the journal ID (`MS_FargothRing`). For quests without a UESP page, a name is derived
from the ID. Homonyms (several IDs for the same page) receive a readable suffix.

The tag indicates the item's class (`[Progression]`, `[Useful]`, `[Trap]`). Messages are spaced
2 s apart and also written to the OpenMW log (`AP notification: ...`). The **Item notifications**
setting (Archipelago page of the options menu) disables them.

How it works: the bridge receives the `PrintJSON` `ItemSend` / `ItemCheat` messages from the
server, resolves item and location names with the datapackage (cached in `datapackage.json` of
the `data_dir`) and writes a `{"t":"notify",...}` line to `in.jsonl`. `global.lua` filters it
(increasing id remembered in the save, nothing older than 10 min) then relays it to the player
script (`AP_Notify`). Items received while the game was closed are applied as before but without
notification.

Tests: `python3 tools/test_bridge_notify.py` and `luajit tools/test_notify.lua`.

## Connection configuration

All settings are in `mod/scripts/ap/config.lua` (host, port, slot,
password, data_dir, auto_start_bridge, deathlink). The Python bridge also reads
the environment variables `AP_HOST`, `AP_PORT`, `AP_SLOT`, `AP_PASSWORD`,
`AP_DATA_DIR`, `AP_DEATHLINK`.

## Quick installation

1. Copy `mod/` into the OpenMW mods folder and enable `archipelago.omwscripts`.
2. Install the apworld: `python3 tools/install_apworld.py`.
3. Generate a seed with a player YAML `game: Morrowind OpenMW`.
4. Start the Archipelago server with the generated multidata.
5. Start OpenMW: the mod automatically starts the Python bridge.
