# Morrowind Archipelago (OpenMW)

Mod Archipelago pour jouer à Morrowind sous OpenMW comme un monde Archipelago.

## Composants

- `apworld/` : package de génération Archipelago (`morrowind_openmw`)
- `mod/` : mod OpenMW (Lua, build non sandboxé via LuaJIT)
- `bridge/` : client/relais Python (websocket <-> fichiers JSONL)
- `data/` : listes de locations/items (source de vérité)
- `tools/` : extraction ESM, génération de données

## Prérequis

- OpenMW 0.52+ avec LuaJIT non sandboxé (variante `unsandboxed`)
- Archipelago 0.6.8+
- Python 3.12+ avec `websockets`, `pyyaml`

## Extraction des données (ESM)

```sh
tes3conv Morrowind.esm morrowind.json

# 1. quêtes (les IDs existants sont conservés, les nouveaux s'ajoutent)
python tools/extract.py morrowind.json --out data/
# 2. stage de complétion des nouvelles quêtes (les entrées existantes sont conservées)
python tools/gen_quest_finals.py morrowind.json
#    -> vérifier data/quest_review.txt (quêtes à plusieurs fins : ajouter overrides/fail)
# 2b. objets de quête des autres objectifs (candidats à relire : data/quest_items_candidates.yaml)
python tools/gen_quest_items.py morrowind.json --apply
# 3. groupes (main / factions / daedric / misc ...) + rapport data/quest_groups_report.txt
python tools/classify_quests.py
# 4. tables Lua (quest_completions.lua, goals.lua, ...)
python tools/gen_lua.py
# 5. apworld
python tools/install_apworld.py
```

Les locations de quête portent le nom lisible de la quête (table `data/quest_names.yaml`,
titres des pages UESP). Les quêtes absentes de la table reçoivent un nom déduit de leur ID.

Les IDs de locations sont stables : relancer l'extraction ne casse ni les seeds ni
les tables Lua existantes. Pense à régénérer la seed après mise à jour.

## Objectif et checks

L'objectif par défaut est la **quête principale** (mort de Dagoth Ur). Dans le YAML joueur
(voir `Morrowind-OpenMW.example.yaml`) tu peux la retirer et/ou y ajouter, chacun optionnel :

```yaml
Morrowind OpenMW:
  main_quest: true             # false = la quête principale n'est plus un objectif
  great_house: hlaalu          # none | hlaalu | redoran | telvanni
  guild: mages_guild           # none | fighters_guild | mages_guild | thieves_guild
  faction: temple              # none | imperial_cult | imperial_legion | temple | morag_tong
  daedric_quests: true         # ajoute les 7 quêtes daedriques à l'objectif
```

La victoire exige que la quête principale (si `main_quest` est activé) **et** chaque maison / guilde /
faction choisie (et, si activé, les 7 quêtes daedriques) soient accomplies. Avec `main_quest: false`, il
faut au moins un autre objectif, sinon la génération s'arrête avec un message d'erreur ; la quête
principale reste jouable librement, sans objets ni checks Archipelago. Pour une maison, guilde ou faction, c'est atteindre le rang 10 (chef) : le mod affiche
`AP: rang <faction> = N` dans le log OpenMW à chaque changement de rang. Un objectif accompli le
reste (mémorisé dans la sauvegarde). Les conditions se règlent dans `data/goals.yaml`
(puis `python tools/gen_lua.py`).

**Checks.** Chaque quête « Miscellaneous » (UESP) donne un check à sa fin. Avec l'option
`goal_quest_checks` (défaut `true`), **la complétion de chaque quête des objectifs choisis** (quête
principale, maison / guilde / faction, quêtes daedriques) donne aussi un check. Les quêtes des
objectifs non choisis, vampires, des extensions, etc. restent ignorées.

```yaml
  goal_quest_checks: true      # true | false
```

- `false` : seules les quêtes Miscellaneous donnent des checks.
- `true` : ces checks peuvent contenir de la progression, ce qui permet de choisir plusieurs
  objectifs. Pour rester faisable : chaque check exige **tous** les items de son objectif (le mod
  retire les objets de quête tant que l'item AP n'est pas reçu ; on ne sait pas lequel sert à quelle
  quête), et les quêtes à fin exclusive (`fail` dans `data/quest_finals.yaml`) ne contiennent jamais
  d'item important. Les objets de l'objectif le plus petit doivent tenir dans les quêtes
  Miscellaneous, puis chaque objectif accompli débloque ses propres checks pour le suivant.

Il n'y a plus de check par étape de journal (ancienne option `quest_granularity: stage`, retirée), ni
de mode `safe` (`goal_quest_checks: safe` est maintenant `true`, qui correspond à l'ancien `full`).

Si la seed ne peut pas être remplie (trop d'items de progression pour les locations disponibles),
la génération s'arrête avec un message qui propose `goal_quest_checks: true` ou moins d'objectifs.
Le mod n'envoie un check de quête d'objectif que si l'option est active et l'objectif choisi
(`mod/scripts/ap/goal_checks.lua`).

Le groupe d'une quête est déterminé par son préfixe
(`tools/quest_groups.py`) ; les exceptions se mettent dans `data/quest_groups_override.yaml`.
Les quêtes daedriques ne servent à l'objectif et aux checks que quand `daedric_quests` est activé.

## Quêtes daedriques (option `daedric_quests`)

Quand l'option est activée, les 7 quêtes daedriques (`da_azura`, `da_boethiah`, `da_malacath`,
`da_mehrunes`, `da_mephala`, `da_molagbal`, `da_sheogorath`) s'ajoutent à l'objectif. Chacune est
**verrouillée par un item Archipelago** (`Daedric Quest: <prince>`, voir `data/quest_locks.yaml`) :
tant qu'il n'est pas reçu, le mod remet le journal de la quête à zéro (log `AP: quete verrouillee
remise a zero : ...`), donc elle ne peut ni avancer ni être terminée. Les 7 items sont de la
progression, requis pour la victoire. Si le log affiche `impossible de verrouiller`, l'API OpenMW de
ta version ne permet pas de modifier `quest.stage` depuis le script joueur.

## Objets de quête donnés par Archipelago

Pour la quête principale (si `main_quest` est activé) et la maison / guilde / faction choisies, **tous leurs objets de quête sont des items Archipelago** (progression)
placés dans les quêtes Miscellaneous. Le mod retire les copies que les quêtes donneraient
(`suppress`) tant que l'item AP n'est pas reçu, puis donne l'objet (`give`) à la réception.
La victoire exige de pouvoir tous les obtenir. Les objets des maisons / guildes / factions non choisies ne
sont ni dans le pool ni supprimés.

Ils sont décrits dans `data/quest_items.yaml` (`main_quest` est rempli ; les maisons, guildes et factions
se génèrent depuis l'ESM avec `tools/gen_quest_items.py`, puis `gen_lua.py` et
`install_apworld.py`). Le goal n'est connu du mod qu'une fois connecté au serveur : la
suppression ne commence qu'à ce moment (la config est ensuite mémorisée dans la sauvegarde).

## Notifications en jeu

Chaque item Archipelago **reçu** ou **envoyé** par ton slot affiche un message en jeu :

- `Archipelago : Bob vous envoie Ebony Dagger [Progression]` (item reçu d'un autre joueur)
- `Archipelago : Mothwing Cloak [Utile] (Fargoth's Ring) obtenu [check complété] -> Bob` (item de ton monde pour un autre joueur)
- `Archipelago : Ebony Dagger (Fargoth's Ring) obtenu [check complété]` (item de ton monde pour toi)

Quand le message correspond à un check de quête, le nom de la quête est affiché entre parenthèses.
Les locations Archipelago utilisent ce nom lisible (titre de la page UESP, table
`data/quest_names.yaml`) au lieu de l'ID de journal (`MS_FargothRing`). Pour les quêtes
sans page UESP, un nom est déduit de l'ID. Les homonymes (plusieurs IDs pour une même
page) reçoivent un suffixe lisible.

Le tag indique la classe de l'item (`[Progression]`, `[Utile]`, `[Piège]`). Les messages sont
espacés de 2 s et aussi écrits dans le log OpenMW (`AP notification: ...`). Le réglage
**Item notifications** (page Archipelago du menu des options) les désactive.

Fonctionnement : le bridge reçoit les `PrintJSON` `ItemSend` / `ItemCheat` du serveur, résout les noms
d'items et de locations avec le datapackage (mis en cache dans `datapackage.json` du `data_dir`) et écrit
une ligne `{"t":"notify",...}` dans `in.jsonl`. `global.lua` la filtre (id croissant mémorisé dans la
sauvegarde, rien de plus vieux que 10 min) puis la relaie au script joueur (`AP_Notify`).
Les items reçus pendant que le jeu était fermé sont appliqués comme avant mais sans notification.

Tests : `python3 tools/test_bridge_notify.py` et `luajit tools/test_notify.lua`.

## Configuration de la connexion

Tous les paramètres sont dans `mod/scripts/ap/config.lua` (host, port, slot,
password, data_dir, auto_start_bridge, deathlink). Le bridge Python lit aussi
les variables d'environnement `AP_HOST`, `AP_PORT`, `AP_SLOT`, `AP_PASSWORD`,
`AP_DATA_DIR`, `AP_DEATHLINK`.

## Installation rapide

1. Copier `mod/` dans le dossier de mods OpenMW et activer `archipelago.omwscripts`.
2. Installer l'apworld : `python3 tools/install_apworld.py`.
3. Générer une seed avec un YAML joueur `game: Morrowind OpenMW`.
4. Lancer le serveur Archipelago avec le multidata généré.
5. Lancer OpenMW : le mod démarre automatiquement le bridge Python.

## Protocole

Voir `Design Archipelago pour OpenMW.md` section 3.
