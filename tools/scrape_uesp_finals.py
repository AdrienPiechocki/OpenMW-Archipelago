#!/usr/bin/env python3
"""Scrapes UESP quest pages and suggests values for STAGES_OVERRIDES.

Sources (crawled from the two index pages):
  https://en.uesp.net/wiki/Morrowind:Quests
  https://en.uesp.net/wiki/Tamriel_Rebuilt:Quests

Every quest page has "Quest Stages" tables (one per journal id):

    The Haunting (IC16_Haunting)
    Index | Finishes Quest | Journal Entry
    50    | Finishes quest | I reported taking care of the haunted house...

For each journal id the script keeps the stages flagged "Finishes quest",
splits them into likely successes / suspected failures (keywords in the
journal text) and compares them with what gen_quest_finals.py currently
produces.

Outputs (in --outdir):
  uesp_finals_report.txt   human review: every difference, with the journal text
  uesp_overrides.py        paste-ready STAGES_OVERRIDES / FAIL_STAGES suggestions
  uesp_cache/              raw API answers (re-runs are instant, --refresh to redo)

Usage:
  pip install requests beautifulsoup4 pyyaml
  python tools/scrape_uesp_finals.py \\
      --script tools/gen_quest_finals.py \\
      --finals data/quest_finals.yaml \\
      --qc data/quest_completions.yaml
  # high-confidence entries only (no suspected failure, not already overridden):
  python tools/scrape_uesp_finals.py ... --apply

--qc restricts the report to journals your quest_completions.yaml uses;
--finals / --script give the "current" values. Both are optional.
"""
import argparse
import ast
import json
import pathlib
import re
import sys
import time
import urllib.parse

import requests
import yaml
from bs4 import BeautifulSoup

BASE = 'https://en.uesp.net/w/api.php'
UA = 'quest-finals-scraper/1.0 (personal Archipelago apworld; polite, cached)'

# (index page, namespace prefix of the quest pages)
ROOTS = [
    ('Morrowind:Quests', 'Morrowind:'),
    ('Tamriel Rebuilt:Quests', 'Tamriel Rebuilt:'),
]

# Page suffixes that are never quests.
SKIP_SUFFIX = ('(person)', '(book)', '(place)', '(item)', '(creature)', '(npc)',
               '(armor)', '(weapon)', '(spell)', '(ingredient)', '(faction)')
SKIP_PARTS = ('Special:', 'File:', 'Category:', 'Template:', 'Talk:', 'User:', 'Help:')

# Journal texts that look like a failure / refusal rather than a success.
# Only a hint: everything flagged is listed for manual review.
FAIL_HINTS = re.compile(
    r"\b(failed|fail(?:ure)?|refus(?:ed|al)|declin(?:ed|e)|would not be able|"
    r"will not be able|unable to|too late|ran out of time|time (?:ran|is) out|"
    r"gave up|abandon(?:ed)?|no longer (?:need|require|want)|"
    r"is dead|was dead|has died|have died|had died|died before|was killed before|"
    r"dead before|lost the|lost my chance|never (?:be able|got|found)|"
    r"does not need|doesn't need|no longer interested)\b", re.I)


class Wiki:
    def __init__(self, cache, delay, refresh):
        self.s = requests.Session()
        self.s.headers['User-Agent'] = UA
        self.cache = pathlib.Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.refresh = refresh

    def html(self, title):
        """Rendered HTML of a page (None if missing)."""
        key = re.sub(r'[^A-Za-z0-9_.-]+', '_', title)[:150]
        f = self.cache / f'{key}.json'
        if f.exists() and not self.refresh:
            return json.loads(f.read_text(encoding='utf-8')).get('html')
        params = {'action': 'parse', 'page': title, 'prop': 'text', 'format': 'json',
                  'redirects': 1, 'disableeditsection': 1, 'disabletoc': 1}
        html = None
        for attempt in range(4):
            try:
                r = self.s.get(BASE, params=params, timeout=30)
                r.raise_for_status()
                data = r.json()
                if 'parse' in data:
                    html = data['parse']['text']['*']
                break
            except (requests.RequestException, ValueError) as e:
                print(f'  retry {title}: {e}', file=sys.stderr)
                time.sleep(2 * (attempt + 1))
        f.write_text(json.dumps({'html': html}), encoding='utf-8')
        time.sleep(self.delay)
        return html


def wiki_links(html):
    """Titles of the internal links found in the content of a page."""
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if not href.startswith('/wiki/') or 'action=' in href or 'redlink' in href:
            continue
        title = urllib.parse.unquote(href[len('/wiki/'):]).split('#')[0].replace('_', ' ')
        if title:
            out.append(title)
    return out


def is_quest_candidate(title, prefix):
    if not title.startswith(prefix) or title == prefix:
        return False
    rest = title[len(prefix):]
    if rest.startswith('Quests') or rest.lower().endswith(SKIP_SUFFIX):
        return False
    return not any(p in title for p in SKIP_PARTS)


def crawl(wiki, limit=None):
    """All candidate quest pages reachable from the two index pages."""
    pages = {}
    for root, prefix in ROOTS:
        seen, todo = set(), [(root, 0)]
        while todo:
            title, depth = todo.pop(0)
            if title in seen:
                continue
            seen.add(title)
            html = wiki.html(title)
            if not html:
                continue
            print(f'index {title}', file=sys.stderr)
            for t in wiki_links(html):
                if t.startswith(prefix + 'Quests') and depth < 3:
                    todo.append((t, depth + 1))
                elif is_quest_candidate(t, prefix):
                    pages.setdefault(t, prefix)
    titles = sorted(pages)
    return titles[:limit] if limit else titles


ID_RE = re.compile(r'\(([A-Za-z0-9_\-\' ]+)\)\s*$')


def parse_stage_tables(html):
    """[(journal id (lowercase), {stage: (finishes, text)})] of a quest page.

    A page can hold SEVERAL journal ids, either in separate tables or in ONE
    table: a one-cell title row "Quest name (JOURNAL_ID)" then starts a new
    section in the middle of the table (e.g. TR_m1_FG_Past / TR_m1_FG_Past2),
    without a new "Index | Finishes Quest" header. Each section is parsed on
    its own: merging them would mix the stages of two different journals.
    """
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if not any(
            'index' in [c.get_text(' ', strip=True).lower() for c in tr.find_all(['th', 'td'])]
            for tr in rows[:3]
        ):
            continue
        cur_id, stages = None, {}

        def flush():
            if cur_id and stages:
                out.append((cur_id, dict(stages)))

        # title given by a <caption> or by the text before the table
        cap = table.find('caption')
        if cap:
            m = ID_RE.search(cap.get_text(' ', strip=True))
            if m:
                cur_id = m.group(1).strip().lower()
        for tr in rows:
            cells = tr.find_all(['td', 'th'])
            texts = [c.get_text(' ', strip=True) for c in cells]
            low = [t.lower() for t in texts]
            if 'index' in low and any('journal' in t for t in low):
                if cur_id is None:   # no title row/caption yet: text before the table
                    prev = table.find_previous(string=ID_RE)
                    m = ID_RE.search(str(prev).strip()) if prev else None
                    cur_id = m.group(1).strip().lower() if m else None
                continue
            if len(cells) == 1:      # one-cell row: title of a (new) journal id
                m = ID_RE.search(texts[0])
                if m:
                    flush()
                    cur_id, stages = m.group(1).strip().lower(), {}
                continue
            if len(cells) < 2 or cur_id is None or not texts[0].isdigit():
                continue
            line = tr.get_text(' ', strip=True)
            fin = 'finishes quest' in line.lower() or 'finishes' in cells[1].get_text().lower()
            stages[int(texts[0])] = (fin, texts[-1])
        flush()
    return out


def load_current(script, finals, qc):
    """Current overrides (parsed, not imported: gen_quest_finals needs quest_groups)."""
    cur = {'STAGES_OVERRIDES': {}, 'FAIL_STAGES': {}}
    if script:
        tree = ast.parse(pathlib.Path(script).read_text(encoding='utf-8'))
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name in cur:
                    cur[name] = {k.lower(): v for k, v in ast.literal_eval(node.value).items()}
    stages = {}
    if finals and pathlib.Path(finals).exists():
        for row in yaml.safe_load(open(finals, encoding='utf-8')) or []:
            stages[str(row['quest']).lower()] = sorted(row.get('stages') or [])
    wanted = None
    if qc and pathlib.Path(qc).exists():
        wanted = {str(q['trigger']['quest']).strip().lower()
                  for q in yaml.safe_load(open(qc, encoding='utf-8')) or []}
    return cur, stages, wanted


def snippet(text, n=110):
    text = ' '.join(text.split())
    return text if len(text) <= n else text[:n] + '...'


def analyse(quests, cur, finals_stages, wanted):
    """quests: {qid: {stage: (fin, text)}} -> (diffs, no_finish, matches)."""
    diffs, no_finish, matches = [], [], 0
    for qid in sorted(quests):
        if wanted is not None and qid not in wanted:
            continue
        stages = quests[qid]
        fin = sorted(s for s, (f, _) in stages.items() if f and s > 0)
        if not fin:
            no_finish.append(qid)
            continue
        success = [s for s in fin if not FAIL_HINTS.search(stages[s][1])]
        suspects = [s for s in fin if s not in success]
        now = cur['STAGES_OVERRIDES'].get(qid) or finals_stages.get(qid)
        known_fail = set(cur['FAIL_STAGES'].get(qid, []))
        success = [s for s in success if s not in known_fail]
        suspects = sorted(set(suspects) | (set(fin) & known_fail))
        if now is not None and sorted(now) == success:
            matches += 1
            continue
        diffs.append({
            'quest': qid, 'now': now, 'overridden': qid in cur['STAGES_OVERRIDES'],
            'known_fail': sorted(known_fail),
            'uesp': fin, 'success': success, 'suspects': suspects,
            'texts': {s: stages[s][1] for s in fin},
        })
    return diffs, no_finish, matches


def write_outputs(outdir, diffs, no_finish, matches, scanned):
    outdir = pathlib.Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    rep = [f'UESP quest pages scanned: {scanned} journal ids; {matches} already match; '
           f'{len(diffs)} differ; {len(no_finish)} without any "Finishes quest" stage.', '']
    for d in diffs:
        tag = ' (already in STAGES_OVERRIDES: manual value kept)' if d['overridden'] else ''
        rep.append(f"{d['quest']}: now={d['now']}  uesp_finishes={d['uesp']}  "
                   f"suggested={d['success']}{tag}")
        for s in d['uesp']:
            mark = '? FAIL?' if s in d['suspects'] else '  ok   '
            rep.append(f"    {mark} {s}: {snippet(d['texts'][s])}")
    if no_finish:
        rep += ['', 'No "Finishes quest" stage on UESP (check by hand):']
        rep += [f'    {q}' for q in no_finish]
    (outdir / 'uesp_finals_report.txt').write_text('\n'.join(rep) + '\n', encoding='utf-8')

    sure = [d for d in diffs if not d['overridden'] and d['success'] and not d['suspects']]
    unsure = [d for d in diffs if not d['overridden'] and d['success'] and d['suspects']]
    fails = [d for d in diffs if d['suspects'] and not d['overridden']]
    py = ['# Generated by tools/scrape_uesp_finals.py -- review before pasting.',
          '', 'STAGES_OVERRIDES_UESP = {']
    for d in sure:
        py.append(f"    {d['quest']!r}: {d['success']},")
    py.append('}')
    py += ['', '# Mixed endings: UESP flags failure-looking stages as "Finishes quest" too.',
           '# Check each one in uesp_finals_report.txt (success list shown, suspects commented).',
           'STAGES_OVERRIDES_UESP_REVIEW = {']
    for d in unsure:
        py.append(f"    {d['quest']!r}: {d['success']},  # suspects: {d['suspects']}")
    py.append('}')
    py += ['', '# Failure stages to add to FAIL_STAGES if the suspects are real failures.',
           'FAIL_STAGES_UESP_REVIEW = {']
    for d in fails:
        py.append(f"    {d['quest']!r}: {d['suspects']},")
    py.append('}')
    (outdir / 'uesp_overrides.py').write_text('\n'.join(py) + '\n', encoding='utf-8')
    return sure


BEGIN, END = '# BEGIN UESP OVERRIDES (tools/scrape_uesp_finals.py)', '# END UESP OVERRIDES'
BEGIN_MIXED = '# BEGIN UESP MIXED OVERRIDES (tools/scrape_uesp_finals.py)'
END_MIXED = '# END UESP MIXED OVERRIDES'


def uesp_updates(diffs, early=0.5):
    """What to write for every journal whose stages differ from UESP.

    Once the tables are parsed per journal id, UESP is the reference: the
    completion stages of a journal are ALL its "Finishes quest" stages (the
    failure-looking ones too: a lost duel still closes the quest, so it must
    still give its check; only the FAIL_STAGES known to the generator are
    left out). The current stages are NOT merged in: they may come from the
    generator's guess ("highest stage") or from an earlier, mis-parsed run,
    and would keep early stages that fire the check when the quest starts.

    A journal with a UESP stage far below its own last one (< early * max) is
    not written: UESP sometimes flags an early stage by mistake and the check
    would fire as soon as the quest starts. It is returned in `review`.
    Hand-written STAGES_OVERRIDES (d['overridden']) are never touched.
    """
    out, review = {}, {}
    for d in diffs:
        if d['overridden']:
            continue
        known = set(d.get('known_fail') or [])
        target = sorted(set(d['uesp']) - known)
        if not target or target == sorted(d['now'] or []):
            continue
        top = max(target)
        if any(st < early * top for st in target):
            review[d['quest']] = target
        else:
            out[d['quest']] = target
    return out, review


def _drop_block(lines, begin, end):
    if any(l.strip() == begin for l in lines):
        a = next(i for i, l in enumerate(lines) if l.strip() == begin)
        b = next(i for i, l in enumerate(lines) if l.strip() == end)
        del lines[a:b + 1]
    return lines


def apply_to_script(script, updates):
    """Writes the updates as ONE block right after the STAGES_OVERRIDES dict.

    Idempotent: the blocks written by a previous run (also the two-block
    layout of older versions of this script) are removed first.
    """
    path = pathlib.Path(script)
    lines = path.read_text(encoding='utf-8').split('\n')
    for begin, end in ((BEGIN, END), (BEGIN_MIXED, END_MIXED)):
        lines = _drop_block(lines, begin, end)
    src = '\n'.join(lines)
    tree = ast.parse(src)
    end = next(n.end_lineno for n in tree.body
               if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
               and n.targets[0].id == 'STAGES_OVERRIDES')
    block = [BEGIN, '# Completion stages = every UESP "Finishes quest" stage of the journal.',
             '# Not overridden by hand. Delete a line here and move it up to keep a manual value.',
             'STAGES_OVERRIDES.update({']
    block += [f"    {q!r}: {v}," for q, v in sorted(updates.items())]
    block += ['})', END]
    lines = src.split('\n')
    lines[end:end] = [''] + block
    path.write_text('\n'.join(lines), encoding='utf-8')
    print(f'{len(updates)} entries written into {script}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument('--script', default='tools/gen_quest_finals.py')
    ap.add_argument('--finals', default='data/quest_finals.yaml')
    ap.add_argument('--qc', default='data/quest_completions.yaml')
    ap.add_argument('--outdir', default='uesp_out')
    ap.add_argument('--delay', type=float, default=0.3, help='seconds between requests')
    ap.add_argument('--refresh', action='store_true', help='ignore the cache')
    ap.add_argument('--limit', type=int, default=None, help='only the N first pages (test)')
    ap.add_argument('--apply', action='store_true',
                    help='write the high-confidence entries into --script')
    args = ap.parse_args()

    wiki = Wiki(pathlib.Path(args.outdir) / 'uesp_cache', args.delay, args.refresh)
    titles = crawl(wiki, args.limit)
    print(f'{len(titles)} candidate pages', file=sys.stderr)

    quests = {}
    for i, t in enumerate(titles, 1):
        html = wiki.html(t)
        if not html:
            continue
        for qid, stages in parse_stage_tables(html):
            if qid in quests and quests[qid] != stages:
                print(f'  duplicate journal id {qid} ({t}): merged', file=sys.stderr)
                quests[qid].update(stages)
            else:
                quests[qid] = stages
        if i % 50 == 0:
            print(f'  {i}/{len(titles)} pages, {len(quests)} journal ids', file=sys.stderr)

    cur, finals_stages, wanted = load_current(args.script, args.finals, args.qc)
    diffs, no_finish, matches = analyse(quests, cur, finals_stages, wanted)
    sure = write_outputs(args.outdir, diffs, no_finish, matches, len(quests))
    print(f'{len(quests)} journal ids on UESP, {matches} match, {len(diffs)} differ '
          f'({len(sure)} high-confidence). See {args.outdir}/uesp_finals_report.txt')
    updates, review = uesp_updates(diffs)
    if review:
        (pathlib.Path(args.outdir) / 'uesp_to_review.txt').write_text(
            'Not applied (a UESP finishing stage is far below the last one):\n'
            + '\n'.join(f'{q}: {v}' for q, v in sorted(review.items())) + '\n', encoding='utf-8')
    print(f'{len(updates)} journal(s) to write, {len(review)} to review by hand '
          f'(see {args.outdir}/uesp_to_review.txt)')
    if args.apply and updates:
        apply_to_script(args.script, updates)


if __name__ == '__main__':
    main()
