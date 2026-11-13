#!/usr/bin/env python3
"""Fills the faction id / leader rank of a faction goal (data/goals.yaml) from the ESM dump,
and clears the goal from UNVERIFIED_GOALS (apworld options.py).

  python tools/set_goal_faction.py ordinators tamriel_data.json [tr_mainland.json]
  python tools/set_goal_faction.py ordinators tamriel_data.json --match ordinator --pick T_Mw_Ordinators

Looks for Faction records whose id or name matches --match (default: the goal key with
underscores removed). If several match, lists them and stops: re-run with --pick <id>.
rank = number of ranks of the faction (the last rank is the leader), like the other goals.
Then: python tools/gen_lua.py && python tools/install_apworld.py
"""
import argparse, json, pathlib, re, sys

ap = argparse.ArgumentParser()
ap.add_argument('goal')
ap.add_argument('esm_json', nargs='+')
ap.add_argument('--match', default=None)
ap.add_argument('--pick', default=None, help='exact faction id when several factions match')
ap.add_argument('--rank', type=int, default=None, help='force the rank (default: number of ranks)')
ap.add_argument('--data', default=str(pathlib.Path(__file__).resolve().parent.parent / 'data'))
ap.add_argument('--options', default=str(pathlib.Path(__file__).resolve().parent.parent
                                         / 'apworld/morrowind_openmw/options.py'))
args = ap.parse_args()

records = []
for p in args.esm_json:
    records += json.load(open(p, encoding='utf-8'))
pat = re.compile((args.match or args.goal.replace('_', '')), re.I)
cands = []
for r in records:
    if r.get('type') != 'Faction':
        continue
    fid, name = str(r.get('id', '')), str(r.get('name', ''))
    if pat.search(fid.replace('_', '')) or pat.search(name):
        ranks = r.get('rank_names') or r.get('ranks') or []
        cands.append((fid, name, len(ranks)))
if args.pick:
    cands = [c for c in cands if c[0].lower() == args.pick.lower()]
if len(cands) != 1:
    print(f'{len(cands)} faction(s) match /{pat.pattern}/:')
    for fid, name, n in cands:
        print(f'  {fid} | {name} | {n} ranks')
    sys.exit('Pick exactly one with --pick <id> (or refine --match).' if cands else 'No faction found.')
fid, name, n = cands[0]
rank = args.rank or n
if rank < 1:
    sys.exit(f'{fid} has no rank list in the dump: pass --rank N')

goals = pathlib.Path(args.data) / 'goals.yaml'
txt = goals.read_text(encoding='utf-8')
block = re.compile(rf'(^{re.escape(args.goal)}:\n(?:[ \t]+.*\n)*?)([ \t]+faction:).*\n([ \t]+rank:).*\n', re.M)
m = block.search(txt)
if not m:
    sys.exit(f'goal {args.goal} not found in {goals}')
new = f'{m.group(1)}{m.group(2)} {fid}\n{m.group(3)} {rank}                                        # {name}: leader\n'
txt = txt[:m.start()] + new + txt[m.end():]
txt = re.sub(r'# UNVERIFIED placeholder:.*\n# Tamriel_Data\.esm:.*\n', f'# faction id / ranks read from the ESM by tools/set_goal_faction.py\n', txt)
goals.write_text(txt, encoding='utf-8')

opt = pathlib.Path(args.options)
s = opt.read_text(encoding='utf-8')
m2 = re.search(r'^UNVERIFIED_GOALS = \((.*)\)$', s, re.M)
if m2:
    keys = [k.strip().strip('"\'') for k in m2.group(1).split(',') if k.strip()]
    keys = [k for k in keys if k != args.goal]
    tup = '(' + ''.join(f'"{k}", ' for k in keys).rstrip(', ') + (',' if len(keys) == 1 else '') + ')'
    s = s[:m2.start()] + f'UNVERIFIED_GOALS = {tup}' + s[m2.end():]
    opt.write_text(s, encoding='utf-8')
print(f'{args.goal}: faction {fid} ({name}), rank {rank} -> {goals}; UNVERIFIED_GOALS updated')
print('Next: python tools/gen_lua.py && python tools/install_apworld.py')
