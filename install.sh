#!/usr/bin/env bash
# Installation du monde Archipelago Morrowind (OpenMW).
# Suit la section « Data extraction (ESM) » du README, puis copie bridge.py
# dans ~/.local/share/openmw/ap/.
#
# Usage :
#   ./install.sh /chemin/vers/Data\ Files
#   MW_DATA="/chemin/vers/Data Files" ./install.sh
#
# Variables optionnelles :
#   MW_DATA        dossier contenant Morrowind.esm (Tribunal.esm / Bloodmoon.esm facultatifs)
#   TES3CONV       commande tes3conv (défaut : tes3conv)
#   PYTHON         interpréteur Python (défaut : python3)
#   AP_DATA_DIR    dossier de données du bridge (défaut : ~/.local/share/openmw/ap)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

MW_DATA="${1:-${MW_DATA:-}}"
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
# Les noms des JSON doivent contenir « tribunal » / « bloodmoon » (README).
step "Conversion des ESM avec tes3conv"
"$TES3CONV" "$MW_DATA/Morrowind.esm" "$WORK/morrowind.json"
JSONS=("$WORK/morrowind.json")

HAS_TRIBUNAL=0
HAS_BLOODMOON=0
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
echo "Pense à copier mod/ dans les mods OpenMW, activer archipelago.omwscripts,"
echo "et à régénérer la seed après mise à jour des données."
