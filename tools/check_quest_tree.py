#!/usr/bin/env python3
"""Sanity checks on uesp_tree_out/quest_tree.json.

Verifies:
  - every needs_item / rewards key resolves to a real ESM item ID
    (case-insensitive lookup against the ESM dumps);
  - no quest has empty completion_stages (should be gone after the merge);
  - no reward key looks like a *display name* (space, parenthesis, comma...).
    NOTE: uppercase letters are allowed and expected — ESM record IDs are
    case-sensitive ('BM_Mace_Aevar_UNI', 'Caius_pants', ...), so a regex
    that rejects uppercase would flag every valid ID as a slug.

FIX (vs the previous version):
  The old SLUG_RE = re.compile(r'\\s|[A-Z]|[^a-z0-9_\\-\\'\\.]') matched every
  uppercase letter, so all 186 canonical IDs produced by the case-preserving
  merge were falsely reported as slugs. The new BAD_ID_RE only rejects
  characters that never appear in an ESM record ID but do appear in a
  UESP display name or header label.

Usage:
  python tools/check_quest_tree.py \\
      --tree uesp_tree_out/quest_tree.json \\
      --esm-json build/morrowind.json build/tribunal.json build/bloodmoon.json \\
                 build/tr_mainland.json build/tamriel_data.json

  # CI mode: exit 1 on any problem
  python tools/check_quest_tree.py --strict ...

Exit code:
  0 if every check passes (or --strict is not set and only warnings remain),
  1 if a check fails (or --strict is set and any warning remains).
"""
import argparse
import json
import pathlib
import re
import sys

# ESM item record types (lowercase, as used by tes3conv JSON dumps).
ITEM_TYPES = {'book', 'miscitem', 'misc', 'weapon', 'armor', 'clothing',
              'apparatus', 'lockpick', 'probe', 'repair', 'repairitem',
              'light', 'alchemy', 'ingredient'}

# FIX: an ESM record ID never contains whitespace, parentheses or commas.
# It MAY contain uppercase, digits, underscores, hyphens, apostrophes and
# dots (e.g. "BM_Mace_Aevar_UNI", "Caius_pants", "fisherman's_amulet",
# "TR_m1_HT_Nu1_almalexias_grace"). Anything matching BAD_ID_RE is a UESP
# display name (e.g. "rewards 35 and 20 gold", "optional", "amulet (unique)").
BAD_ID_RE = re.compile(r'[\s(),]')


def load_esm_item_ids(paths):
    """Return {lower_id: canonical_id} for every item-type record."""
    by_lower = {}
    for p in paths:
        try:
            with open(p, encoding='utf-8') as f:
                for r in json.load(f):
                    if str(r.get('type', '')).lower() in ITEM_TYPES and r.get('id'):
                        rid = str(r['id'])
                        by_lower.setdefault(rid.lower(), rid)
        except FileNotFoundError:
            print(f'WARNING: ESM JSON not found: {p}', file=sys.stderr)
    return by_lower


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', default='uesp_tree_out/quest_tree.json')
    ap.add_argument('--esm-json', nargs='+', required=True)
    ap.add_argument('--strict', action='store_true',
                    help='exit 1 if any warning is reported')
    args = ap.parse_args()

    tree = json.loads(pathlib.Path(args.tree).read_text(encoding='utf-8'))
    esm = load_esm_item_ids(args.esm_json)
    print(f'loaded {len(esm)} item IDs from ESM dumps')

    bad_needs, bad_rewards, empty_stages, bad_stage_attach = [], [], [], []
    # Separate "not in ESM" from "looks like a display name": both used to
    # land in `bad_rewards`, which made the report unreadable.
    not_in_esm_rewards, display_name_rewards = [], []
    n_needs = n_rewards = 0

    for origin, lines in tree.items():
        for line, quests in lines.items():
            for qname, q in quests.items():
                stages = sorted({s for v in q['completion_stages'].values() for s in v})
                if not stages:
                    empty_stages.append((origin, line, qname))
                    continue

                for it in q['needs_item']:
                    n_needs += 1
                    if it.lower() not in esm:
                        bad_needs.append((origin, line, qname, it))

                for it, st in q['rewards'].items():
                    n_rewards += 1
                    if it.lower() not in esm:
                        not_in_esm_rewards.append((origin, line, qname, it))
                    if BAD_ID_RE.search(it):
                        display_name_rewards.append((origin, line, qname, it))
                    for s in st:
                        if s not in stages:
                            bad_stage_attach.append((origin, line, qname, it, s))

                bad_rewards.extend(not_in_esm_rewards)
                bad_rewards.extend(display_name_rewards)

    print(f'\n{n_needs} needs_item, {n_rewards} rewards')

    print(f'\n{len(bad_needs)} needs_item not in ESM:')
    for x in bad_needs[:40]:
        print('  ', '/'.join(x))

    print(f'\n{len(not_in_esm_rewards)} rewards not in ESM:')
    for x in not_in_esm_rewards[:40]:
        print('  ', '/'.join(x))

    print(f'\n{len(display_name_rewards)} rewards that look like display names '
          f'(whitespace / parenthesis / comma):')
    for x in display_name_rewards[:40]:
        print('  ', '/'.join(x))

    print(f'\n{len(empty_stages)} quests with empty completion_stages:')
    for x in empty_stages[:40]:
        print('  ', '/'.join(x))

    print(f'\n{len(bad_stage_attach)} rewards attached to a non-completion stage:')
    for x in bad_stage_attach[:40]:
        print('  ', '/'.join(str(v) for v in x))

    has_problem = bool(bad_needs or not_in_esm_rewards or display_name_rewards
                       or empty_stages or bad_stage_attach)
    if not has_problem:
        print('\nAll checks passed.')
        return 0
    if args.strict:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
