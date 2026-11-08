#!/usr/bin/env python3
"""Quest REWARDS (unique items) extracted from the ESM, for randomization.

A reward is an item given to the player by a quest dialogue (AddItem in a
DialogueInfo result that also sets a journal stage) which is:
  - NOT needed for progression (never handed over / required / counted by a
    quest, and not in the progression whitelist of gen_quest_items.py,
    nor already in data/quest_items.yaml);
  - UNIQUE: a non-consumable item (weapon, armor, clothing, book, misc...)
    that is neither carried by an NPC / container / leveled list nor placed
    in a cell (otherwise it could be obtained outside the quest);
  - tied to a quest that has a completion check (apworld quest_completions),
    which gives its group (goal / expansion / TR group) and region.

Each reward produces ONE Archipelago location (sent when the vanilla item
reaches the player's inventory: the mod then removes it) and ONE item of the
pool (which gives the item when received). Gold and consumables are ignored.

Usage:
  python tools/gen_quest_rewards.py morrowind.json [tribunal.json] [bloodmoon.json] [tr.json] [--apply]

  Without --apply: only prints the candidates. With --apply: writes
  data/quest_rewards.yaml (ids already assigned are kept stable).
"""
import argparse
import json
import pathlib
import re
import sys
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_quest_items as gqi  # noqa: E402

REWARD_ITEM_BASE, REWARD_ITEM_LIMIT = 7704000, 7705000
REWARD_LOC_BASE, REWARD_LOC_LIMIT = 7730000, 7740000

# Journal command WITH its stage: Journal "quest", 40  /  Journal quest 40
PAT_JOURNAL_STAGE = re.compile(
    r'(?<![A-Za-z])Journal[ \t]*,?[ \t]*(?:"([^"\r\n]+)"|([A-Za-z_][A-Za-z0-9_\-]*))[ \t]*,?[ \t]*(\d+)',
    re.I)

# Reward items: unique non-consumable item types only.
REWARD_TYPES = set(gqi.ITEM_TYPES) - set(gqi.CONSUMABLE_TYPES)


def whitelisted_any(item, name):
    """True if the item is a progression item of ANY goal (whitelist / patterns)."""
    goals = set(gqi.QUEST_ITEMS_BY_GOAL) | set(gqi.QUEST_ITEM_PATTERNS_BY_GOAL) - {None}
    return gqi.is_whitelisted(None, item, name) or any(
        gqi.is_whitelisted(g, item, name) for g in goals)


def journal_stages(text):
    """List of (quest, stage) set by Journal commands, in order of appearance."""
    out = []
    for m in PAT_JOURNAL_STAGE.finditer(text or ''):
        q = (m.group(1) or m.group(2)).strip().lower()
        out.append((q, int(m.group(3))))
    return out


def _strings(entry):
    """All lowercase strings of an inventory / reference / leveled-list entry
    (the export format varies: [count, id], [id, level], {'id': ...})."""
    out = []
    if isinstance(entry, str):
        out.append(entry.lower())
    elif isinstance(entry, dict):
        for v in entry.values():
            if isinstance(v, str):
                out.append(v.lower())
    elif isinstance(entry, (list, tuple)):
        for v in entry:
            if isinstance(v, str):
                out.append(v.lower())
    return out


def load_completions(path):
    """quest (lowercase) -> {group, region, name} from quest_completions.yaml."""
    data = yaml.safe_load(pathlib.Path(path).read_text(encoding='utf-8')) or []
    out = {}
    for q in data:
        qid = str((q.get('trigger') or {}).get('quest', '')).lower()
        if qid:
            out[qid] = {'group': q.get('group', 'misc'),
                        'region': q.get('region') or 'Seyda Neen',
                        'name': q.get('name', qid)}
    return out


def scan(records, completions, known_progression):
    """Returns (rewards, stats). `records`: ESM records (list of dicts)."""
    item_rec = {}
    journal_ids = set()
    for r in records:
        t = str(r.get('type', '')).lower()
        if t in gqi.ITEM_TYPES and r.get('id'):
            item_rec[str(r['id']).lower()] = (t, r.get('name') or r['id'])
        elif t == 'dialogue' and str(r.get('dialogue_type', '')).lower() == 'journal':
            journal_ids.add(str(r.get('id', '')).lower())

    needed = set(known_progression)   # progression items (never rewards)
    cands = {}                        # (quest, item) -> {stage, count}

    def handle(text, info, qs_extra=()):
        stages = [(q, s) for q, s in journal_stages(text) if not journal_ids or q in journal_ids]
        quests = [q for q, _ in stages] + [q for q in qs_extra if q not in {x for x, _ in stages}]
        if not quests:
            return
        # Progression: handed over / required / counted by a quest.
        for m in gqi.PAT_REMOVE.finditer(text or ''):
            needed.add(m.group(1).lower())
        for m in gqi.PAT_COUNT.finditer(text or ''):
            needed.add(m.group(1).lower())
        if info is not None:
            for it in gqi.filter_items(info):
                needed.add(it)
        # Rewards: AddItem in the result of a dialogue that sets a stage.
        if not stages:
            return
        quest, stage = stages[0]
        for m in gqi.PAT_ADD.finditer(text or ''):
            item = m.group(1).lower()
            if item.startswith('gold_'):
                continue
            rec = item_rec.get(item)
            if rec is None or rec[0] not in REWARD_TYPES:
                continue
            count = int(m.group(2) or 1)
            key = (quest, item)
            e = cands.setdefault(key, {'stage': stage, 'count': count})
            e['stage'] = min(e['stage'], stage)
            e['count'] = max(e['count'], count)

    for r in records:
        t = str(r.get('type', ''))
        if t == 'DialogueInfo':
            handle(r.get('script_text') or '', r, gqi.filter_journals(r))
        elif t == 'Script':
            handle(r.get('script_text') or r.get('text') or '', None)

    # Items obtainable outside the quest: inventories, containers, leveled
    # lists, cell references.
    wanted = {item for (_, item) in cands}
    elsewhere = set()
    for r in records:
        for field in ('inventory', 'items', 'leveled_items', 'list', 'references'):
            for e in gqi._records_field(r, field):
                for s in _strings(e):
                    if s in wanted:
                        elsewhere.add(s)

    rewards, stats = [], {'candidates': len(cands), 'progression': 0, 'not_unique': 0,
                          'no_completion': 0}
    for (quest, item), e in sorted(cands.items()):
        if item in needed or whitelisted_any(item, item_rec[item][1]):
            stats['progression'] += 1
            continue
        if item in elsewhere:
            stats['not_unique'] += 1
            continue
        comp = completions.get(quest)
        if comp is None:
            stats['no_completion'] += 1
            continue
        rewards.append({'quest': quest, 'record': item, 'item_name': item_rec[item][1],
                        'count': e['count'], 'stage': e['stage'],
                        'group': comp['group'], 'region': comp['region']})
    return rewards, stats


def assign(rewards, existing):
    """Item / location ids and unique names (ids of the existing file are kept)."""
    by_key = {(str(e['quest']).lower(), str(e['record']).lower()): e for e in existing}
    next_item = max([REWARD_ITEM_BASE - 1] + [e['item_id'] for e in existing]) + 1
    next_loc = max([REWARD_LOC_BASE - 1] + [e['loc_id'] for e in existing]) + 1
    names_used = {e['name'] for e in existing}
    out = []
    for r in rewards:
        key = (r['quest'], r['record'])
        old = by_key.get(key)
        if old:
            out.append(old)
            continue
        name = f"Reward: {r['item_name']}"
        if name in names_used:
            name = f"Reward: {r['item_name']} ({r['quest']})"
        names_used.add(name)
        if next_item >= REWARD_ITEM_LIMIT or next_loc >= REWARD_LOC_LIMIT:
            raise SystemExit('too many rewards: widen the id ranges')
        out.append({'name': name, 'item_id': next_item, 'loc_id': next_loc,
                    'record': r['record'], 'count': r['count'], 'quest': r['quest'],
                    'stage': r['stage'], 'group': r['group'], 'region': r['region']})
        next_item += 1
        next_loc += 1
    return out


def dump(entries):
    lines = ['# Quest rewards (unique items), generated by tools/gen_quest_rewards.py --apply',
             '# One location (loc_id) + one item (item_id) per reward.']
    for e in entries:
        lines.append('- {name: %s, item_id: %d, loc_id: %d, record: %s, count: %d, quest: %s, '
                     'stage: %d, group: %s, region: %s}' % (
                         json.dumps(e['name']), e['item_id'], e['loc_id'], json.dumps(e['record']),
                         e['count'], json.dumps(e['quest']), e['stage'], json.dumps(e['group']),
                         json.dumps(e['region'])))
    if not entries:
        lines.append('[]')
    return '\n'.join(lines) + '\n'


def known_progression_records(data):
    """Records already managed as progression items (quest_items.yaml)."""
    path = data / 'quest_items.yaml'
    out = set()
    if path.exists():
        for e in yaml.safe_load(path.read_text(encoding='utf-8')) or []:
            for x in e.get('suppress', []) or []:
                out.add(str(x).lower())
            if e.get('give'):
                out.add(str(e['give'][0]).lower())
    for goal in gqi.QUEST_ITEMS_BY_GOAL.values():
        out |= {str(x).lower() for x in goal}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('esm_json', nargs='+')
    ap.add_argument('--data', default='data')
    ap.add_argument('--completions', default='apworld/morrowind_openmw/data/quest_completions.yaml')
    ap.add_argument('--apply', action='store_true', help='writes data/quest_rewards.yaml')
    args = ap.parse_args()
    data = pathlib.Path(args.data)

    records = list(gqi.load(args.esm_json))
    completions = load_completions(args.completions)
    rewards, stats = scan(records, completions, known_progression_records(data))
    out_path = data / 'quest_rewards.yaml'
    existing = []
    if out_path.exists():
        existing = yaml.safe_load(out_path.read_text(encoding='utf-8')) or []
    entries = assign(rewards, existing)

    for e in entries:
        print(f"{e['quest']:<32} stage>={e['stage']:<4} {e['record']:<32} x{e['count']}  [{e['group']}]")
    print(f"\n{len(entries)} rewards; ignored: {stats['progression']} progression, "
          f"{stats['not_unique']} not unique, {stats['no_completion']} without completion check")
    if args.apply:
        out_path.write_text(dump(entries), encoding='utf-8')
        print('written:', out_path)
    else:
        print('(dry run: use --apply to write data/quest_rewards.yaml)')


if __name__ == '__main__':
    main()
