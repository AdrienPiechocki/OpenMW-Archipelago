#!/usr/bin/env python3
"""Applies gen_quest_finals.GUILD_FIXES (stage / stages / fail) to apworld/.../quest_finals.yaml and
regenerates mod/scripts/ap/quest_completions.lua. Text edit of the matching rows only (the 9000-line
file is not re-dumped). Usage: python3 tools/apply_guild_fixes.py"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import gen_quest_finals as gqf  # noqa: E402
import gen_lua  # noqa: E402

FINALS = ROOT / 'apworld/morrowind_openmw/data/quest_finals.yaml'


def render(q, main, stages, fail):
    def lst(key, vals):
        return f'  {key}: []\n' if not vals else f'  {key}:\n' + ''.join(f'  - {v}\n' for v in vals)
    return (f'- quest: {q}\n  stage: {main}\n' + lst('stages', stages) + lst('fail', fail))


def main():
    t = FINALS.read_text(encoding='utf-8')
    changed = 0
    for q, (m, stages, fail) in gqf.GUILD_FIXES.items():
        pat = re.compile(r'- quest: %s\n  stage: \d+\n  stages:\n(?:  - \d+\n)+  fail:(?: \[\]\n|\n(?:  - \d+\n)+)' % re.escape(q))
        mt = pat.search(t)
        if not mt:
            sys.exit(f'row not found / unexpected format: {q}')
        new = render(q, m, sorted(stages), sorted(fail))
        if mt.group(0) != new:
            t = t[:mt.start()] + new + t[mt.end():]
            changed += 1
    FINALS.write_text(t, encoding='utf-8')
    gen_lua.gen_quest_completions(str(FINALS), str(ROOT / 'mod/scripts/ap/quest_completions.lua'))
    print(f'{changed} row(s) updated')


if __name__ == '__main__':
    main()
