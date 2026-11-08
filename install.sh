#!/usr/bin/env bash
# Installation du monde Archipelago Morrowind (OpenMW).
# Suit la section « Data extraction (ESM) » du README, puis copie bridge.py
# dans ~/.local/share/openmw/ap/.
#
# Usage :
#   ./install.sh /chemin/vers/Data\ Files [/dossier/TR [/dossier/Tamriel_Data]]
#   MW_DATA="/chemin/vers/Data Files" ./install.sh
#
# Variables optionnelles :
#   MW_DATA        dossier contenant Morrowind.esm (Tribunal.esm / Bloodmoon.esm facultatifs)
#   TD_DATA        dossier contenant Tamriel_Data.esm (défaut : TR_DATA puis MW_DATA), facultatif ; 3e argument équivalent
#   TR_DATA        dossier contenant TR_Mainland.esm (défaut : MW_DATA), facultatif ; 2e argument équivalent
#   TES3CONV       commande tes3conv (défaut : tes3conv)
#   PYTHON         interpréteur Python (défaut : python3)
#   AP_DATA_DIR    dossier de données du bridge (défaut : ~/.local/share/openmw/ap)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

MW_DATA="${1:-${MW_DATA:-}}"
TR_DATA="${2:-${TR_DATA:-$MW_DATA}}"
TD_DATA="${3:-${TD_DATA:-}}"
TES3CONV="${TES3CONV:-tes3conv}"
PYTHON="${PYTHON:-python3}"
AP_DATA_DIR="${AP_DATA_DIR:-$HOME/.local/share/openmw/ap}"
BRIDGE_SRC="$ROOT/bridge/bridge.py"
BRIDGE_DST="$AP_DATA_DIR/bridge.py"
WORK="$ROOT/build"

die() { echo "Erreur : $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }

# --- Vérifications -----------------------------------------------------------
[ -n "$MW_DATA" ] || die "dossier des ESM manquant (argument ou variable MW_DATA)"
[ -f "$MW_DATA/Morrowind.esm" ] || die "Morrowind.esm introuvable dans : $MW_DATA"
command -v "$TES3CONV" >/dev/null 2>&1 || die "tes3conv introuvable (voir https://github.com/Greatness7/tes3conv)"
command -v "$PYTHON" >/dev/null 2>&1 || die "$PYTHON introuvable"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
  || die "Python 3.12+ requis"
"$PYTHON" -c 'import websockets, yaml' 2>/dev/null \
  || die "modules Python manquants : pip install websockets pyyaml"
[ -f "$BRIDGE_SRC" ] || die "bridge/bridge.py introuvable dans $ROOT"

mkdir -p "$WORK"

# --- Conversion ESM -> JSON --------------------------------------------------
# Les noms des JSON doivent contenir « tribunal » / « bloodmoon » / « tr_mainland » (README).
step "Conversion des ESM avec tes3conv"
"$TES3CONV" "$MW_DATA/Morrowind.esm" "$WORK/morrowind.json"
JSONS=("$WORK/morrowind.json")

HAS_TRIBUNAL=0
HAS_BLOODMOON=0
HAS_TR=0
if [ -f "$MW_DATA/Tribunal.esm" ]; then
  "$TES3CONV" "$MW_DATA/Tribunal.esm" "$WORK/tribunal.json"
  JSONS+=("$WORK/tribunal.json")
  HAS_TRIBUNAL=1
else
  echo "(Tribunal.esm absent : options tribunal_* inutilisables)"
fi
if [ -f "$MW_DATA/Bloodmoon.esm" ]; then
  "$TES3CONV" "$MW_DATA/Bloodmoon.esm" "$WORK/bloodmoon.json"
  JSONS+=("$WORK/bloodmoon.json")
  HAS_BLOODMOON=1
else
  echo "(Bloodmoon.esm absent : options bloodmoon_* et East Empire Company inutilisables)"
fi
if [ -f "$TR_DATA/TR_Mainland.esm" ]; then
  "$TES3CONV" "$TR_DATA/TR_Mainland.esm" "$WORK/tr_mainland.json"
  JSONS+=("$WORK/tr_mainland.json")
  HAS_TR=1
  # Les factions TR (Indoril, Ja-Natta...) sont définies dans Tamriel_Data.esm : JSON à part,
  # utilisé seulement par tools/list_tr.py (il ne doit pas être passé à extract.py).
  for d in "${TD_DATA:-}" "$TR_DATA" "$MW_DATA"; do
    if [ -n "$d" ] && [ -f "$d/Tamriel_Data.esm" ]; then
      "$TES3CONV" "$d/Tamriel_Data.esm" "$WORK/tamriel_data.json"
      break
    fi
  done
  [ -f "$WORK/tamriel_data.json" ] || echo "(Tamriel_Data.esm introuvable : définir TD_DATA pour lister les factions TR)"
else
  echo "(TR_Mainland.esm absent : options tamriel_rebuilt_*, great_house: indoril et faction: ja_natta_syndicate inutilisables)"
fi

# --- 1. Quêtes ---------------------------------------------------------------
step "1/5 Extraction des quêtes"
"$PYTHON" tools/extract.py "${JSONS[@]}" --out data/

# --- 2. Stages de fin --------------------------------------------------------
step "2/5 Stages de complétion"
"$PYTHON" tools/gen_quest_finals.py "${JSONS[@]}"
echo "-> vérifier data/quest_review.txt (quêtes à fins multiples : overrides/fail)"

# --- 2b. Objets de quête -----------------------------------------------------
step "2b Objets de quête"
ITEMS_JSONS=("$WORK/morrowind.json")
[ "$HAS_BLOODMOON" -eq 1 ] && ITEMS_JSONS+=("$WORK/bloodmoon.json")
"$PYTHON" tools/gen_quest_items.py "${ITEMS_JSONS[@]}" --apply
echo "-> candidats à relire : data/quest_items_candidates.yaml"

# --- 2c. Récompenses de quêtes (option quest_rewards) -------------------------
# Objets uniques donnés par les quêtes, hors objets de progression : après 2b
# (quest_items.yaml fait partie des exclusions), tous les JSON (TR inclus).
step "2c Récompenses de quêtes"
"$PYTHON" tools/gen_quest_rewards.py "${JSONS[@]}" --completions data/quest_completions.yaml --apply

# --- 3. Groupes --------------------------------------------------------------
step "3/5 Classification des quêtes"
"$PYTHON" tools/classify_quests.py
echo "-> rapport : data/quest_groups_report.txt"

# --- 4. Tables Lua -----------------------------------------------------------
step "4/5 Génération des tables Lua"
"$PYTHON" tools/gen_lua.py

# --- 5. apworld --------------------------------------------------------------
step "5/5 Installation de l'apworld"
"$PYTHON" tools/install_apworld.py

# --- bridge.py ---------------------------------------------------------------
step "Copie de bridge.py"
mkdir -p "$AP_DATA_DIR"
cp -f "$BRIDGE_SRC" "$BRIDGE_DST"
echo "$BRIDGE_SRC -> $BRIDGE_DST"

echo
echo "Installation terminée."
if [ "$HAS_TR" -eq 1 ]; then
  echo "Tamriel Rebuilt : compléter data/tr_categories.yaml (Foul Murder, quêtes daedriques),"
  echo "puis vérifier les factions : $PYTHON tools/list_tr.py $WORK/tamriel_data.json $WORK/tr_mainland.json --factions --grep indoril"
fi
echo "Pense à copier mod/ dans les mods OpenMW, activer archipelago.omwscripts,"
echo "et à régénérer la seed après mise à jour des données."
echo "Récompenses de quêtes randomisées : quest_rewards: true dans le YAML (liste : data/quest_rewards.yaml)."
