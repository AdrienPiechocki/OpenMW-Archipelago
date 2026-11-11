#!/usr/bin/env python3
"""Builds a full quest tree (JSON) from the UESP quest pages.

Output (quest_tree.json):

  { "<origin>": {                 # Morrowind | Tribunal | Bloodmoon | Tamriel Rebuilt
      "<quest_line>": {           # main_quest | side_quest | <faction slug> | ...
          "<quest name>": {
              "ids": ["journal_id", ...],
              "completion_stages": {"journal_id": [100, 110]},
              "region": "Region Name",
              "triggers": {"other_journal_id": [stage, ...]},
              "needs_item": ["item_id"],
              "rewards": {"item_id": [stage, ...]}
          }}}}

Where each field comes from (UESP has no script data, so some are heuristics):
  ids / completion_stages  "Quest Stages" tables (journal ids, "Finishes quest").
  origin                   page namespace + page categories (Tribunal / Bloodmoon).
  quest_line               page categories ("Morrowind-Fighters Guild Quests"...).
  region                   quest header "Region" row, else the region of the
                           linked "Location" page.
  triggers                 (a) links to another quest page inside a journal text
                               -> stages where the link appears;
                           (b) quest header "Prerequisite"/"Next quest" rows
                               -> stages = completion stages of the earlier quest.
  needs_item               links in quest header rows such as "Items needed".
  rewards                  links in the quest header "Reward" row; the stages are
                           the quest's completion stages (UESP does not say at
                           which stage the reward is given).
  item ids                 read from the item page infobox ("ID"/"Item ID"...),
                           otherwise a slug of the page title (listed in the report).

Usage:
  pip install requests beautifulsoup4
  python scrape_uesp_quest_tree.py                 # -> uesp_tree_out/quest_tree.json
  python scrape_uesp_quest_tree.py --limit 20      # quick test on 20 pages
  python scrape_uesp_quest_tree.py --no-resolve    # do not fetch item/place pages

Also written: quest_tree_report.txt (what is missing / guessed) and
uesp_labels_seen.txt (every header label and category met, to tune the
constants below if a field comes out empty).
"""
import argparse
import json
import pathlib
import re
import sys
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

BASE = 'https://en.uesp.net/w/api.php'
UA = 'quest-tree-scraper/1.0 (personal Archipelago apworld; polite, cached)'

# (category, accepted namespace prefixes of the quest pages)
CATEGORIES = [
    ('Category:Morrowind-Quests', ('Morrowind:',)),
    ('Category:Tribunal-Quests', ('Tribunal:', 'Morrowind:')),
    ('Category:Bloodmoon-Quests', ('Bloodmoon:', 'Morrowind:')),
    ('Category:Tamriel Rebuilt-Quests', ('Tamriel Rebuilt:',)),
]
SKIP_SUFFIX = ('(person)', '(book)', '(place)', '(item)', '(creature)', '(npc)',
               '(armor)', '(weapon)', '(spell)', '(ingredient)', '(faction)')
SKIP_PARTS = ('Special:', 'File:', 'Category:', 'Template:', 'Talk:', 'User:', 'Help:')

# ---- header labels (lowercase, without ':') -- tune with uesp_labels_seen.txt
REGION_LABELS = {'region', 'regions', 'region(s)'}
# rows of a place page that point to the parent place (dungeon -> town/area)
PARENT_LABELS = {'located in', 'location', 'location(s)', 'entrance', 'entrances',
                 'part of', 'area', 'nearest town', 'cell'}
# vanilla regions: used when a page names its region in plain prose
KNOWN_REGIONS = ['Ascadian Isles', 'Ashlands', "Azura's Coast", 'Bitter Coast', 'Grazelands',
                 'Molag Amur', 'Red Mountain', 'Sheogorad', 'West Gash', 'Felsaad Coast',
                 'Hirstaang Forest', 'Moesring Mountains', 'Isinfier Plains']
LOCATION_LABELS = {'location', 'locations', 'location(s)', 'start location', 'starting location'}
REWARD_LABELS = {'reward', 'rewards'}
ITEM_LABELS = {'item needed', 'items needed', 'required item', 'required items',
               'item required', 'items required', 'needed items', 'needs', 'item', 'items'}
PREREQ_LABELS = {'prerequisite', 'prerequisites', 'requires', 'requirement', 'requirements',
                 'prior quest', 'prior quests', 'preceded by', 'follows', 'previous quest',
                 'previous quests', 'prev'}   # 'prev'/'next' = nav rows (chains only)
FOLLOW_LABELS = {'next', 'next quest', 'next quests', 'followed by', 'leads to', 'continues in',
                 'follow-up', 'follow-up quest', 'follow up', 'sequel'}
ID_LABELS = {'id', 'item id', 'base id', 'editor id', 'object id', 'form id'}

# ---- quest line naming (category text without game prefix / "Quests")
LINE_ALIASES = {
    'main': 'main_quest', 'main quest': 'main_quest', 'main quests': 'main_quest',
    'miscellaneous': 'side_quest', 'misc': 'side_quest', 'side': 'side_quest',
}
GENERIC_LINES = {'', 'quest', 'quests'}
NOT_ITEMS = {'gold', 'septim', 'septims', 'drake', 'drakes'}

ID_RE = re.compile(r'\(([A-Za-z0-9_\-\' ]+)\)\s*$')
GAME_PREFIX = re.compile(r'^(?:Morrowind|Tribunal|Bloodmoon|Tamriel Rebuilt)[- :]+', re.I)


def clean(t):
    return ' '.join((t or '').split())


def slug(name):
    name = name.split(':', 1)[-1] if re.match(r'^[A-Za-z ]+:', name) else name
    name = re.sub(r'\s*\([^)]*\)\s*$', '', name)
    return re.sub(r'[^a-z0-9]+', '_', name.lower().replace("'", '')).strip('_')


def strip_ns(title):
    return re.sub(r'^(?:Morrowind|Tribunal|Bloodmoon|Tamriel Rebuilt):', '', title).strip()


# ---------------------------------------------------------------- wiki access
class Wiki:
    def __init__(self, cache, delay, refresh):
        self.s = requests.Session()
        self.s.headers['User-Agent'] = UA
        self.cache = pathlib.Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.delay, self.refresh = delay, refresh
        self.memo = {}

    def _file(self, key):
        return self.cache / (re.sub(r'[^A-Za-z0-9_.-]+', '_', key)[:150] + '.json')

    def _get(self, params, what):
        for attempt in range(4):
            try:
                r = self.s.get(BASE, params=params, timeout=30)
                r.raise_for_status()
                return r.json()
            except (requests.RequestException, ValueError) as e:
                print(f'  retry {what}: {e}', file=sys.stderr)
                time.sleep(2 * (attempt + 1))
        return None

    def category_members(self, cat):
        f = self._file('category_' + cat)
        if f.exists() and not self.refresh:
            return json.loads(f.read_text(encoding='utf-8')).get('members') or []
        members, cont = [], {}
        while True:
            params = {'action': 'query', 'list': 'categorymembers', 'cmtitle': cat,
                      'cmlimit': '500', 'cmtype': 'page', 'format': 'json', **cont}
            data = self._get(params, cat)
            if data is None:
                break
            members += [m['title'] for m in data.get('query', {}).get('categorymembers', [])]
            if 'continue' not in data:
                break
            cont = data['continue']
            time.sleep(self.delay)
        f.write_text(json.dumps({'members': members}), encoding='utf-8')
        time.sleep(self.delay)
        return members

    def page(self, title):
        """{'html': str|None, 'categories': [str]} (cached)."""
        if title in self.memo:
            return self.memo[title]
        f = self._file(title)
        if f.exists() and not self.refresh:
            d = json.loads(f.read_text(encoding='utf-8'))
            if 'categories' in d:
                self.memo[title] = d
                return d
        params = {'action': 'parse', 'page': title, 'prop': 'text|categories', 'format': 'json',
                  'redirects': 1, 'disableeditsection': 1, 'disabletoc': 1}
        data = self._get(params, title)
        d = {'html': None, 'categories': []}
        if data and 'parse' in data:
            d['html'] = data['parse']['text']['*']
            d['categories'] = [c['*'].replace('_', ' ') for c in data['parse'].get('categories', [])]
        f.write_text(json.dumps(d), encoding='utf-8')
        time.sleep(self.delay)
        self.memo[title] = d
        return d


def title_of(href):
    if not href.startswith('/wiki/') or 'action=' in href or 'redlink' in href:
        return None
    t = urllib.parse.unquote(href[len('/wiki/'):]).split('#')[0].replace('_', ' ')
    return t or None


def links_in(node):
    nodes = list(node.find_all('a', href=True))
    if isinstance(node, Tag) and node.name == 'a' and node.get('href'):
        nodes.append(node)
    return [t for t in (title_of(a['href']) for a in nodes) if t]


def is_candidate(title, prefixes):
    for p in prefixes:
        if title.startswith(p) and title != p:
            rest = title[len(p):]
            if rest.startswith('Quests') or rest.lower().endswith(SKIP_SUFFIX):
                return False
            return not any(x in title for x in SKIP_PARTS)
    return False


def crawl(wiki, limit=None):
    pages = {}
    for cat, prefixes in CATEGORIES:
        members = wiki.category_members(cat)
        print(f'category {cat}: {len(members)} pages', file=sys.stderr)
        for t in members:
            if is_candidate(t, prefixes):
                pages.setdefault(t, True)
    titles = sorted(pages)
    return titles[:limit] if limit else titles


# ------------------------------------------------------------- HTML parsing
def is_stage_table(table):
    rows = table.find_all('tr')
    return any('index' in [c.get_text(' ', strip=True).lower() for c in tr.find_all(['th', 'td'])]
               for tr in rows[:3])


def parse_stage_tables(html):
    """[(journal id (lowercase), {stage: (finishes, text, [linked titles])})]."""
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    for table in soup.find_all('table'):
        if not is_stage_table(table):
            continue
        rows = table.find_all('tr')
        cur_id, stages = None, {}

        def flush():
            if cur_id and stages:
                out.append((cur_id, dict(stages)))

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
                if cur_id is None:
                    prev = table.find_previous(string=ID_RE)
                    m = ID_RE.search(str(prev).strip()) if prev else None
                    cur_id = m.group(1).strip().lower() if m else None
                continue
            if len(cells) == 1:
                m = ID_RE.search(texts[0])
                if m:
                    flush()
                    cur_id, stages = m.group(1).strip().lower(), {}
                continue
            if len(cells) < 2 or cur_id is None or not texts[0].isdigit():
                continue
            line = tr.get_text(' ', strip=True)
            fin = 'finishes quest' in line.lower() or 'finishes' in cells[1].get_text().lower()
            stages[int(texts[0])] = (fin, texts[-1], links_in(cells[-1]))
        flush()
    return out


def extract_fields(html):
    """{label: [(text, [linked titles])]} for the header rows of a page.

    Reads two-cell table rows, <b>Label:</b> value runs and <dt>/<dd> pairs.
    Stage tables are ignored."""
    soup = BeautifulSoup(html, 'html.parser')
    for t in soup.find_all('table'):
        if is_stage_table(t):
            t.decompose()
    fields = {}

    def add(label, text, links):
        label = clean(label).rstrip(':').strip().lower()
        text = clean(text).lstrip(':').strip()
        if label and len(label) <= 40:
            fields.setdefault(label, []).append((text, links))

    for tr in soup.find_all('tr'):
        cells = tr.find_all(['th', 'td'], recursive=False)
        if len(cells) == 2:
            add(cells[0].get_text(' ', strip=True), cells[1].get_text(' ', strip=True),
                links_in(cells[1]))
    for b in soup.find_all(['b', 'strong']):
        label = clean(b.get_text(' ', strip=True))
        nxt = b.next_sibling
        first = str(nxt) if isinstance(nxt, NavigableString) else ''
        if not (label.endswith(':') or first.lstrip().startswith(':')):
            continue
        parts, links = [], []
        for sib in b.next_siblings:
            if isinstance(sib, Tag):
                if sib.name in ('b', 'strong', 'br', 'p', 'ul', 'ol', 'div', 'table'):
                    break
                parts.append(sib.get_text(' ', strip=True))
                links += links_in(sib)
            else:
                parts.append(str(sib))
        add(label, ' '.join(parts), links)
    for dt in soup.find_all('dt'):
        dd = dt.find_next_sibling('dd')
        if dd:
            add(dt.get_text(' ', strip=True), dd.get_text(' ', strip=True), links_in(dd))
    return fields


def norm_label(lab):
    lab = lab.strip('\u2190\u2192 ').strip()
    if lab == 'prev' or lab.startswith('previous'):
        return 'prev'
    if lab.startswith('next'):
        return 'next'
    return lab


def labeled(fields):
    for lab, vs in fields.items():
        for text, links in vs:
            yield norm_label(lab), text, links


def values(fields, labels):
    return [(t, l) for lab, t, l in labeled(fields) if lab in labels]


# ------------------------------------------------------ origin / quest line
def origin_of(title, cats):
    if title.startswith('Tamriel Rebuilt:') or any('Tamriel Rebuilt' in c for c in cats):
        return 'Tamriel Rebuilt'
    if title.startswith('Bloodmoon:') or any(re.match(r'Bloodmoon\b', c) for c in cats):
        return 'Bloodmoon'
    if title.startswith('Tribunal:') or any(re.match(r'Tribunal\b', c) for c in cats):
        return 'Tribunal'
    return 'Morrowind'


LINE_CAT = re.compile(r'^(?:Morrowind|Tribunal|Bloodmoon|Tamriel Rebuilt)-Quests-(.+)$')


def line_of(cats):
    """Quest line from categories like "Bloodmoon-Quests-East Empire Company Quests"."""
    found = []
    for c in cats:
        m = LINE_CAT.match(c)
        if not m:
            continue
        rest = re.sub(r'\bquests?$', '', m.group(1).strip().lower()).strip()
        if rest in GENERIC_LINES:
            continue
        found.append(LINE_ALIASES.get(rest, slug(rest)))
    if not found:
        return 'uncategorized'
    return 'main_quest' if 'main_quest' in found else found[0]


# ------------------------------------------------------- region / item ids
def norm_region(r):
    r = strip_ns(clean(r)).strip(' .,;')
    return re.sub(r'\s+Region$', '', r, flags=re.I) or None


def find_known_region(text):
    best = None
    for r in KNOWN_REGIONS:
        i = text.find(r)
        if i >= 0 and (best is None or i < best[0]):
            best = (i, r)
    return best[1] if best else None


def region_of_place(wiki, title, depth=1):
    """Region of a place page: infobox row, category, lead prose, then the parent place."""
    key = ('region', title)
    if key in wiki.memo:
        return wiki.memo[key]
    d = wiki.page(title)
    region, parents, lead = None, [], ''
    if d['html']:
        fields = extract_fields(d['html'])
        for text, _ in values(fields, REGION_LABELS):
            if text:
                region = norm_region(text)
                break
        if not region:
            for c in d['categories']:
                if re.search(r'\bRegion\b', c):
                    region = norm_region(GAME_PREFIX.sub('', c))
                    break
        soup = BeautifulSoup(d['html'], 'html.parser')
        lead = clean(' '.join(p.get_text(' ') for p in soup.find_all('p')[:3]))
        if not region:
            m = re.search(r"(?:in|of|within|on)\s+the\s+((?:[A-Z][\w'-]*\s)+)[Rr]egion", lead)
            region = norm_region(m.group(1)) if m else None
        if not region:
            region = find_known_region(lead) or find_known_region(
                ' '.join(t for t, _ in values(fields, PARENT_LABELS)))
        if not region and depth > 0:
            parents = [l for _, ls in values(fields, PARENT_LABELS) for l in ls if l != title]
            for l in parents[:3]:
                region = region_of_place(wiki, l, depth - 1)
                if region:
                    break
    if not region:
        wiki.memo.setdefault('place_debug', {})[title] = {
            'cats': d['categories'][:8], 'parents': parents[:3], 'lead': lead[:200]}
    wiki.memo[key] = region
    return region


def region_of_quest(wiki, fields, resolve):
    for text, _ in values(fields, REGION_LABELS):
        if text:
            return norm_region(text)
    locs = values(fields, LOCATION_LABELS)
    for text, _ in locs:           # the location text may already name the region
        r = find_known_region(text)
        if r:
            return r
    if resolve:
        for _, links in locs:
            for l in links:
                r = region_of_place(wiki, l)
                if r:
                    return r
    return None


def item_id(wiki, title, resolve, unresolved):
    key = ('item', title)
    if key in wiki.memo:
        return wiki.memo[key]
    result = None
    if resolve:
        d = wiki.page(title)
        if d['html']:
            fl = extract_fields(d['html'])
            seen = wiki.memo.setdefault('item_labels', {})
            for lab in fl:
                seen[lab] = seen.get(lab, 0) + 1
            for text, _ in values(fl, ID_LABELS):
                m = re.search(r'[A-Za-z0-9_\'\-]+', text)
                if m:
                    result = m.group(0).lower()
                    break
    if not result:
        result = slug(title)
        unresolved.append((title, result))
    wiki.memo[key] = result
    return result


def usable_item(title, quest_titles):
    return (title not in quest_titles and slug(title) not in NOT_ITEMS
            and not title.lower().endswith(('(person)', '(npc)', '(place)', '(faction)', '(creature)')))


# ------------------------------------------------------------------ main
def build(wiki, titles, resolve):
    recs = {}
    for i, t in enumerate(titles, 1):
        d = wiki.page(t)
        if not d['html']:
            continue
        tables = parse_stage_tables(d['html'])
        ids, stages = [], {}
        for qid, st in tables:
            if qid in stages:
                stages[qid].update(st)
            else:
                ids.append(qid)
                stages[qid] = st
        recs[t] = {'title': t, 'cats': d['categories'], 'ids': ids, 'stages': stages,
                   'fields': extract_fields(d['html'])}
        if i % 50 == 0:
            print(f'  {i}/{len(titles)} pages', file=sys.stderr)

    quest_titles = set(recs)
    unresolved, labels = [], {}
    for r in recs.values():
        for lab in r['fields']:
            labels[lab] = labels.get(lab, 0) + 1
    cats_seen = {}
    for r in recs.values():
        for c in r['cats']:
            cats_seen[c] = cats_seen.get(c, 0) + 1

    def completion(r):
        return {q: sorted(s for s, (f, _, _) in r['stages'][q].items() if f and s > 0)
                for q in r['ids']}

    # triggers (a): quest links inside journal texts
    for r in recs.values():
        trig = {}
        for q in r['ids']:
            for s, (_, _, links) in r['stages'][q].items():
                for l in links:
                    if l in quest_titles and l != r['title'] and recs[l]['ids']:
                        trig.setdefault(recs[l]['ids'][0], set()).add(s)
        r['triggers'] = trig
        r['completion'] = completion(r)
        r['line'] = line_of(r['cats'])

    # triggers (b): prerequisite / follow-up rows. The prev/next nav rows only
    # count for chains (main quest, factions): in side_quest they are alphabetical.
    for r in recs.values():
        if not r['ids']:
            continue
        done = (r['completion'].get(r['ids'][-1]) or r['completion'].get(r['ids'][0]) or [])
        for lab, _, links in labeled(r['fields']):
            if lab in ('prev', 'next') and r['line'] in ('side_quest', 'uncategorized'):
                continue
            for l in links:
                if l not in quest_titles or l == r['title'] or not recs[l]['ids']:
                    continue
                prev = recs[l]
                if lab in PREREQ_LABELS:
                    st = (prev['completion'].get(prev['ids'][-1])
                          or prev['completion'].get(prev['ids'][0]) or [])
                    prev['triggers'].setdefault(r['ids'][0], set()).update(st)
                elif lab in FOLLOW_LABELS:
                    r['triggers'].setdefault(prev['ids'][0], set()).update(done)

    tree, no_ids, no_region, region_debug = {}, [], [], []
    for t in sorted(recs):
        r = recs[t]
        all_stages = sorted({s for v in r['completion'].values() for s in v})
        rewards = {}
        for _, links in values(r['fields'], REWARD_LABELS):
            for l in links:
                if usable_item(l, quest_titles):
                    rewards[item_id(wiki, l, resolve, unresolved)] = all_stages
        needs = []
        for _, links in values(r['fields'], ITEM_LABELS):
            for l in links:
                if usable_item(l, quest_titles):
                    iid = item_id(wiki, l, resolve, unresolved)
                    if iid not in needs:
                        needs.append(iid)
        region = region_of_quest(wiki, r['fields'], resolve)
        if not r['ids'] and not re.search(r'(?:Quests|Main Quest)$', strip_ns(t)):
            no_ids.append(t)
        if not region:
            no_region.append(t)
            locs = values(r['fields'], LOCATION_LABELS)
            for text, links in locs:
                dbg = [(l, wiki.memo.get('place_debug', {}).get(l)) for l in links]
                region_debug.append((t, text, dbg))
            if not locs:
                region_debug.append((t, '(no Location row found)', []))
        if not r['ids'] and re.search(r'(?:Quests|Main Quest)$', strip_ns(t)):
            continue   # category / index page, not a quest
        origin, line = origin_of(t, r['cats']), r['line']
        name = strip_ns(t)
        branch = tree.setdefault(origin, {}).setdefault(line, {})
        if name in branch:
            name = f"{name} ({r['ids'][0]})" if r['ids'] else f'{name} (2)'
        branch[name] = {
            'ids': r['ids'],
            'completion_stages': r['completion'],
            'region': region or 'Unknown',
            'triggers': {k: sorted(v) for k, v in sorted(r['triggers'].items())},
            'needs_item': needs,
            'rewards': rewards,
        }
    tree = {o: {l: dict(sorted(q.items())) for l, q in sorted(ls.items())}
            for o, ls in sorted(tree.items())}
    return tree, {'no_ids': no_ids, 'no_region': no_region, 'unresolved': unresolved,
                  'labels': labels, 'cats': cats_seen,
                  'item_labels': wiki.memo.get('item_labels', {}),
                  'region_debug': region_debug}


def write_outputs(outdir, tree, info):
    outdir = pathlib.Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / 'quest_tree.json').write_text(
        json.dumps(tree, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    n = sum(len(q) for ls in tree.values() for q in ls.values())
    rep = [f'{n} quest pages in the tree.', '']
    rep += [f'Pages without any "Quest Stages" table ({len(info["no_ids"])}):']
    rep += [f'    {t}' for t in info['no_ids']]
    rep += ['', f'Quests without a region ({len(info["no_region"])}):']
    rep += [f'    {t}' for t in info['no_region']]
    rep += ['', 'Region debug (location text / linked place page: categories, parents, lead):']
    for t, text, dbg in info['region_debug']:
        rep.append(f'    {t}: location={text!r}')
        for l, d in dbg:
            rep.append(f'        {l}: {d}')
    rep += ['', f'Item ids guessed from the page title ({len(info["unresolved"])}):']
    rep += [f'    {t} -> {s}' for t, s in sorted(set(info['unresolved']))]
    (outdir / 'quest_tree_report.txt').write_text('\n'.join(rep) + '\n', encoding='utf-8')
    seen = ['# Header labels found on the quest pages (count)']
    seen += [f'{c:4d}  {l}' for l, c in sorted(info['labels'].items(), key=lambda x: -x[1])]
    seen += ['', '# Categories found on the quest pages (count)']
    seen += [f'{c:4d}  {l}' for l, c in sorted(info['cats'].items(), key=lambda x: -x[1])]
    seen += ['', '# Labels found on item pages (to find the item id row)']
    seen += [f'{c:4d}  {l}' for l, c in sorted(info['item_labels'].items(), key=lambda x: -x[1])]
    (outdir / 'uesp_labels_seen.txt').write_text('\n'.join(seen) + '\n', encoding='utf-8')
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument('--outdir', default='uesp_tree_out')
    ap.add_argument('--delay', type=float, default=0.3, help='seconds between requests')
    ap.add_argument('--refresh', action='store_true', help='ignore the cache')
    ap.add_argument('--limit', type=int, default=None, help='only the N first pages (test)')
    ap.add_argument('--no-resolve', action='store_true',
                    help='do not fetch place/item pages (no region from Location, ids = slugs)')
    args = ap.parse_args()

    wiki = Wiki(pathlib.Path(args.outdir) / 'uesp_cache', args.delay, args.refresh)
    titles = crawl(wiki, args.limit)
    print(f'{len(titles)} candidate pages', file=sys.stderr)
    tree, info = build(wiki, titles, not args.no_resolve)
    n = write_outputs(args.outdir, tree, info)
    print(f'{n} quests -> {args.outdir}/quest_tree.json (see quest_tree_report.txt)')


if __name__ == '__main__':
    main()
