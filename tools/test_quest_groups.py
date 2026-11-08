#!/usr/bin/env python3
"""Checks the quest -> group classification (blades_* count as main)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quest_groups import classify, VALID_GROUPS  # noqa: E402

CASES = {
    'blades_elone': 'main', 'blades_tyermaillin2': 'main',
    'a1_1_findspymaster': 'main', 'c3_destroydagoth': 'main',
    'va_vampblood': 'vampire', 'da_azura': 'daedric', 'ms_fargoth': 'misc',
}
bad = [(q, classify(q), g) for q, g in CASES.items() if classify(q) != g]
for q, got, want in bad:
    print(f'FAIL {q}: {got} (expected {want})')
assert 'blades' not in VALID_GROUPS, "'blades' must no longer be a group"
if bad:
    sys.exit(1)
print('quest groups tests passed')
