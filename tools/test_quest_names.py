#!/usr/bin/env python3
"""Test des noms lisibles des quetes (locations Archipelago).

Depuis la racine du depot :
    python3 tools/test_quest_names.py
"""
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quest_names import derive_name, load_names, quest_name, unique_names  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
names = load_names(ROOT / 'data' / 'quest_names.yaml')
rows = yaml.safe_load((ROOT / 'data' / 'quest_completions.yaml').read_text(encoding='utf-8')) or []
mapped = unique_names(rows, names)

fails = 0


def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f'FAIL {name}: got {got!r}, want {want!r}')
    else:
        print(f'ok   {name}')


check('nombre de locations', len(mapped), len(rows))
check('noms uniques', len(set(mapped.values())), len(rows))

for qid, location in mapped.items():
    # Aucun nom ne doit etre l'ID de journal brut (avec ou sans suffixe).
    low = location.lower()
    if low == qid or low.startswith(qid + ' '):
        check(f'nom lisible pour {qid}', location, 'un nom humain')

check('nom UESP', mapped['a1_1_findspymaster'], 'Report to Caius Cosades')
check('nom UESP avec sous-quete', mapped['a1_10_mehramilo'], 'Vivec Informants - Mehra Milo')
check('ID sans separateur', mapped['a1_7huleeyainformant'], 'Vivec Informants - Huleeya Informant')
check('nom simple', mapped['ms_fargothring'], "Fargoth's Ring")
check('variante en echec', mapped['ic2_muck_not'], 'Gathering Muck - failed')
check('sous-quete', mapped['a1_sleepers_alvura'], 'Sleepers Awake - Alvura')

check('repli camelCase', derive_name('A1_7HuleeyaInformant'), 'Huleeya Informant')
check('repli prefixe faction', derive_name('MT_S_BalancedArmor'), 'Balanced Armor')
check('repli prefixe ville', derive_name('town_Sadrith'), 'Sadrith')
check('repli chiffre', derive_name('A2_1_Supplies2'), 'Supplies 2')
check('table prioritaire', quest_name('MS_FargothRing', names), "Fargoth's Ring")

if fails:
    print(f'{fails} failure(s)')
    sys.exit(1)
print('all quest name tests passed')
