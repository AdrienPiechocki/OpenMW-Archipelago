#!/usr/bin/env python3
"""Test for readable quest names (Archipelago locations).

From the repository root:
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


check('location count', len(mapped), len(rows))
check('unique names', len(set(mapped.values())), len(rows))

for qid, location in mapped.items():
    # No name must be the raw journal ID (with or without suffix).
    low = location.lower()
    if low == qid or low.startswith(qid + ' '):
        check(f'readable name for {qid}', location, 'a human name')

check('UESP name', mapped['a1_1_findspymaster'], 'Report to Caius Cosades')
check('UESP name with sub-quest', mapped['a1_10_mehramilo'], 'Vivec Informants - Mehra Milo')
check('ID without separator', mapped['a1_7huleeyainformant'], 'Vivec Informants - Huleeya Informant')
check('simple name', mapped['ms_fargothring'], "Fargoth's Ring")
check('failed variant', mapped['ic2_muck_not'], 'Gathering Muck - failed')
check('sub-quest', mapped['a1_sleepers_alvura'], 'Sleepers Awake - Alvura')

check('camelCase fallback', derive_name('A1_7HuleeyaInformant'), 'Huleeya Informant')
check('faction prefix fallback', derive_name('MT_S_BalancedArmor'), 'Balanced Armor')
check('town prefix fallback', derive_name('town_Sadrith'), 'Sadrith')
check('digit fallback', derive_name('A2_1_Supplies2'), 'Supplies 2')
check('priority table', quest_name('MS_FargothRing', names), "Fargoth's Ring")

if fails:
    print(f'{fails} failure(s)')
    sys.exit(1)
print('all quest name tests passed')
