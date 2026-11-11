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

Item IDs (needs_item / rewards) are resolved against the ESM JSON dumps
produced by tes3conv + extract.py (see --esm-json). UESP links that point
to a spell / faction / skill / user page are rejected instead of being
slugged into a fake ID. Without --esm-json the scraper falls back to the
UESP item-page infobox, then to a page-title slug (logged as "guessed").

An item that appears both in "needs" and in "rewards" is treated as a
needs_item only (UESP sometimes lists in "Reward" an object the player
must bring). Such cases are listed in quest_tree_anomalies.txt, along with
"find-type" quests that have rewards but no needs. If UESP mislabels the
fetch item as a reward without ever listing it as a need, the anomaly
report shows both the resolved ESM ID and the original UESP link so you
can either fix the scraper (extend ITEM_LABELS) or the JSON manually.

Where each field comes from:
  ids / completion_stages  "Quest Stages" tables (journal ids, "Finishes quest").
  origin                   page namespace + page categories (Tribunal / Bloodmoon).
  quest_line               page categories ("Morrowind-Fighters Guild Quests"...).
  region                   quest header "Region" row, else the region of the
                           linked "Location" page.
  triggers                 (a) links to another quest page inside a journal text
                               -> stages where the link appears;
                           (b) quest header "Prerequisite"/"Next quest" rows
                               -> stages = completion stages of the earlier quest.
  needs_item               links in quest header rows such as "Items needed",
                           plus any reward-link that also appears as a need.
  rewards                  links in the quest header "Reward" row, MINUS any
                           link already counted as a need; the stages are
                           the quest's completion stages.
  item ids                 resolved from the ESM JSON dumps (--esm-json), then
                           from the UESP item page infobox ("ID"/"Item ID"...),
                           otherwise a slug of the page title (listed in the report).

Usage:
  pip install requests beautifulsoup4
  python scrape_uesp_quest_tree.py --esm-json morrowind.json tribunal.json \
      bloodmoon.json tr_mainland.json tamriel_data.json
  python scrape_uesp_quest_tree.py --limit 20      # quick test on 20 pages
  python scrape_uesp_quest_tree.py --no-resolve    # do not fetch item/place pages

Also written: quest_tree_report.txt (missing / guessed / rejected),
quest_tree_anomalies.txt (needs∩rewards overlaps, suspicious fetch titles)
and uesp_labels_seen.txt (every header label and category met).
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
REGION_LABELS = {'region', 'regions'}
LOCATION_LABELS = {'location', 'locations', 'location(s)', 'start location', 'starting location'}

REWARD_LABELS = {
    'reward', 'rewards',
    # extended: UESP sometimes lists received objects under these labels
    'item received', 'items received',
    'item gained', 'items gained',
    'item obtained', 'items obtained',
    'items given', 'item given',
    'loot', 'loots',
}

ITEM_LABELS = {
    'item needed', 'items needed', 'required item', 'required items',
    'item required', 'items required', 'needed items', 'needs',
    'item', 'items',
    # extended: UESP sometimes uses these for quest items to bring
    'item to find', 'items to find',
    'item to bring', 'items to bring',
    'item to deliver', 'items to deliver',
    'item to return', 'items to return',
    'items to retrieve', 'item to retrieve',
    'items to recover', 'item to recover',
    'items to look for', 'item to look for',
    'find item', 'find items',
    'bring', 'deliver', 'return', 'retrieve', 'recover',
    'required', 'requirements',
    'quest item', 'quest items',
}

GIVER_LABELS = {'quest giver', 'quest givers', 'given by', 'added by'}
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

# ---- ESM record types (from tes3conv JSON dumps)
ESM_ITEM_TYPES = {
    'Weapon', 'Armor', 'Clothing', 'Book', 'Ingredient', 'Potion',
    'MiscItem', 'Lockpick', 'Probe', 'RepairItem', 'Apparatus',
    'Ammunition', 'Light',
}
ESM_NON_ITEM_TYPES = {
    'Spell', 'Faction', 'Skill', 'Birthsign', 'Race', 'Class',
    'Dialogue', 'DialogueInfo', 'Script', 'Region', 'Cell',
    'NPC', 'Creature', 'Container', 'Door', 'Activator',
    'Static', 'Landscape', 'Sound', 'MagicEffect', 'Enchantment',
    'Repair', 'Bodypart', 'SoundGen', 'StartScript', 'GameSetting',
}

ID_RE = re.compile(r'\(([A-Za-z0-9_\-\' ]+)\)\s*$')
GAME_PREFIX = re.compile(r'^(?:Morrowind|Tribunal|Bloodmoon|Tamriel Rebuilt)[- :]+', re.I)

# Titles that strongly suggest a "fetch/bring X" quest. Deliberately NARROW:
# "rescue", "missing", "stolen", "lost" are EXCLUDED because they usually
# name the *target* (an NPC or a place) rather than an item to bring, and
# the rewards of such quests are legitimate. Only explicit fetch verbs count.
FIND_TITLE_RE = re.compile(
    r'\b(find|search\s+for|recover|retrieve|return|bring|deliver|'
    r'fetch|locate|seek)\b', re.I)

# Titles that, despite containing a fetch verb, are actually about
# rescuing/avenging an NPC or place -> not a fetch item.
NON_FETCH_TITLE_RE = re.compile(
    r'\b(rescue|avenge|avenging|save|defend|protect|escort|kill|slay|'
    r'missing|stolen|lost|home|house|family|friend|brother|sister|son|daughter|'
    r'wife|husband|father|mother)\b', re.I)


def clean(t):
    return ' '.join((t or '').split())


def slug(name):
    name = name.split(':', 1)[-1] if re.match(r'^[A-Za-z ]+:', name) else name
    name = re.sub(r'\s*\([^)]*\)\s*$', '', name)
    return re.sub(r'[^a-z0-9]+', '_', name.lower().replace("'", '')).strip('_')


def strip_ns(title):
    return re.sub(r'^(?:Morrowind|Tribunal|Bloodmoon|Tamriel Rebuilt):', '', title).strip()


def display_name(title):
    """'Morrowind:Amulet of Unity (item)' -> 'amulet of unity' (lowercase key)."""
    name = title.split(':', 1)[-1] if ':' in title else title
    name = re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()
    return name.lower()


def is_fetch_title(title):
    """True if the title looks like 'fetch X' and NOT 'rescue/save NPC'."""
    name = strip_ns(title)
    if not FIND_TITLE_RE.search(name):
        return False
    if NON_FETCH_TITLE_RE.search(name):
        return False
    return True


# ---------------------------------------------------------------- ESM index
def load_esm_items(paths):
    """Build two indexes from the tes3conv JSON dumps.

    items_by_name     : {display_name_lower: record_id}      (item types only)
    non_items_by_name : {display_name_lower: set(record_types)}  (spell/faction/...)

    Only the first definition of a name wins, so a later ESM (e.g. Tamriel_Data)
    does not silently override a vanilla item with an unrelated one.
    """
    items, non_items = {}, {}
    for p in paths:
        path = pathlib.Path(p)
        if not path.exists():
            print(f'WARNING: ESM JSON not found: {p}', file=sys.stderr)
            continue
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f'WARNING: cannot read {p}: {e}', file=sys.stderr)
            continue
        for r in data:
            t = r.get('type')
            rid = r.get('id')
            name = r.get('name') or rid
            if not rid or not name:
                continue
            key = name.strip().lower()
            if t in ESM_ITEM_TYPES:
                items.setdefault(key, rid)
            elif t in ESM_NON_ITEM_TYPES:
                non_items.setdefault(key, set()).add(t)
    return items, non_items


def resolve_item_id(title, items_by_name, non_items_by_name):
    """Map a UESP link title to a real ESM item ID.

    Returns (record_id, reason) where reason is 'item', 'non-item' or 'unknown'.
    """
    candidates = []
    if ':' in title:
        candidates.append(title.split(':', 1)[1])
    candidates.append(title)
    seen = set()
    for cand in candidates:
        for variant in (cand, re.sub(r'\s*\([^)]*\)\s*$', '', cand).strip()):
            key = variant.lower()
            if key in seen:
                continue
            seen.add(key)
            if key in items_by_name:
                return items_by_name[key], 'item'
            if key in non_items_by_name:
                return None, 'non-item'
    return None, 'unknown'


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
        d = {'html': None, 'categories': [], 'redirect': None}
        if data and 'parse' in data:
            d['html'] = data['parse']['text']['*']
            d['categories'] = [c['*'].replace('_', ' ') for c in data['parse'].get('categories', [])]
            red = data['parse'].get('redirects')
            if red:
                d['redirect'] = red[0].get('to')
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
        if t.attrs is None:   # nested table already destroyed with its decomposed parent
            continue
        if is_stage_table(t) or 'questNavBar-grid' in (t.get('class') or []):
            t.decompose()
    fields = {}

    def add(label, text, links):
        label = clean(label).rstrip(':').strip().lower()
        text = clean(text).lstrip(':').strip()
        if label and len(label) <= 40:
            fields.setdefault(label, []).append((text, links))

    for tr in soup.find_all('tr'):
        cells = tr.find_all(['th', 'td'], recursive=False)
        if len(cells) == 2 and not cells[0].find('a'):
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
def region_of_place(wiki, title):
    key = ('region', title)
    if key in wiki.memo:
        return wiki.memo[key]
    d = wiki.page(title)
    region = None
    if d['html']:
        for text, links in values(extract_fields(d['html']), REGION_LABELS):
            if text:
                region = strip_ns(text)
                break
        if not region:
            for c in d['categories']:
                if re.search(r'\bRegion\b', c):
                    region = strip_ns(GAME_PREFIX.sub('', c))
                    break
        if not region:
            soup = BeautifulSoup(d['html'], 'html.parser')
            for tr in soup.find_all('tr'):
                cells = tr.find_all(['td', 'th'], recursive=False)
                if len(cells) != 1:
                    continue
                m = re.match(r"^([A-Z][\w' ]*?)\s*,\s*\[-?\d+\s*,\s*-?\d+\]"
                             r"(?:\s*-\s*\[-?\d+\s*,\s*-?\d+\])*\s*$",
                             cells[0].get_text(' ', strip=True))
                if m and m.group(1):
                    region = strip_ns(m.group(1))
                    break
        if not region:
            soup = BeautifulSoup(d['html'], 'html.parser')
            for p in soup.find_all('p'):
                m = re.search(r"(?:in|of) the ((?:[A-Z][\w'-]*\s)+)[Rr]egion",
                              p.get_text(' '))
                if m:
                    region = m.group(1).strip()
                    break
    wiki.memo[key] = region
    return region


def place_region(wiki, title):
    r = region_of_place(wiki, title)
    if r:
        return r
    base = title.split(',', 1)[0].strip()
    if base and base != title:
        return region_of_place(wiki, base)
    return None


def region_of_quest(wiki, fields, resolve, title=None):
    for text, _ in values(fields, REGION_LABELS):
        if text:
            return strip_ns(text)
    ns = title.split(':', 1)[0] if title and ':' in title else None
    if resolve:
        for _, links in values(fields, LOCATION_LABELS):
            for l in links:
                r = place_region(wiki, l)
                if r:
                    return r
        for _, links in values(fields, GIVER_LABELS):
            for l in links:
                r = place_region(wiki, l)
                if r:
                    return r
        if ns:
            for labels in (LOCATION_LABELS, GIVER_LABELS):
                for text, links in values(fields, labels):
                    if links:
                        continue
                    base = text.split(',', 1)[0].strip()
                    if base and base[0].isupper() and len(base) <= 40:
                        r = place_region(wiki, f'{ns}:{base}')
                        if r:
                            return r
    if title and title.startswith('Tribunal:'):
        return 'Mournhold'
    return None


# ------------------------------------------------------- item id resolution
def item_id(wiki, title, items_by_name, non_items_by_name, resolve, unresolved):
    """Resolve a UESP item link to a real ESM ID.

    Returns (record_id, reason) where reason is 'esm', 'infobox', 'slug' or
    'non-item'. Returns (None, reason) for non-items.
    """
    key = ('item', title)
    if key in wiki.memo:
        return wiki.memo[key]

    rid, reason = resolve_item_id(title, items_by_name, non_items_by_name)
    if rid:
        wiki.memo[key] = (rid, 'esm')
        return rid, 'esm'
    if reason == 'non-item':
        wiki.memo[key] = (None, 'non-item')
        return None, 'non-item'

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
        wiki.memo[key] = (result, 'slug')
        return result, 'slug'

    wiki.memo[key] = (result, 'infobox')
    return result, 'infobox'


def usable_item(title, quest_titles, non_items_by_name=None):
    if title in quest_titles:
        return False
    name = display_name(title)
    if name in NOT_ITEMS:
        return False
    if non_items_by_name and name in non_items_by_name:
        return False
    if title.lower().endswith(('(person)', '(npc)', '(place)', '(faction)', '(creature)')):
        return False
    return True


# ------------------------------------------------------------------ main
def build(wiki, titles, resolve, why=None, esm_items=None, esm_non_items=None):
    items_by_name = esm_items or {}
    non_items_by_name = esm_non_items or {}
    recs = {}
    for i, t in enumerate(titles, 1):
        d = wiki.page(t)
        if not d['html']:
            continue
        if d.get('redirect') and re.search(r'(?:Quests|Main Quest)$', strip_ns(d['redirect'])):
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

    why_log = []

    def note(src, dst, reason):
        if why and why.lower() in (src['title'] + '|' + dst['title']).lower():
            why_log.append(f"{src['title']} -> {dst['title']}   [{reason}]")

    for r in recs.values():
        trig = {}
        for q in r['ids']:
            for s, (_, _, links) in r['stages'][q].items():
                for l in links:
                    if l in quest_titles and l != r['title'] and recs[l]['ids']:
                        trig.setdefault(recs[l]['ids'][0], set()).add(s)
                        note(r, recs[l], f'journal link in {q} stage {s}')
        r['triggers'] = trig
        r['completion'] = completion(r)
        r['line'] = line_of(r['cats'])

    def nav_links(rec, which):
        return {l for lab, _, ls in labeled(rec['fields']) if lab == which for l in ls}

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
                if lab == 'prev' and r['title'] not in nav_links(prev, 'next'):
                    continue
                if lab == 'next' and r['title'] not in nav_links(prev, 'prev'):
                    continue
                if lab in PREREQ_LABELS:
                    st = (prev['completion'].get(prev['ids'][-1])
                          or prev['completion'].get(prev['ids'][0]) or [])
                    prev['triggers'].setdefault(r['ids'][0], set()).update(st)
                    note(prev, r, f"row '{lab}' on page '{r['title']}' links to '{prev['title']}'")
                elif lab in FOLLOW_LABELS:
                    r['triggers'].setdefault(prev['ids'][0], set()).update(done)
                    note(r, prev, f"row '{lab}' on page '{r['title']}' links to '{prev['title']}'")

    for line in why_log:
        print('WHY', line, file=sys.stderr)

    stats = {'esm': 0, 'infobox': 0, 'slug': 0, 'rejected': {}}
    anomalies = []

    tree, no_ids, no_region = {}, [], []
    for t in sorted(recs):
        r = recs[t]
        all_stages = sorted({s for v in r['completion'].values() for s in v})

        # -------- needs_item
        needs = []
        for _, links in values(r['fields'], ITEM_LABELS):
            for l in links:
                if not usable_item(l, quest_titles, non_items_by_name):
                    continue
                iid, how = item_id(wiki, l, items_by_name, non_items_by_name,
                                   resolve, unresolved)
                if iid is None:
                    stats['rejected'][display_name(l)] = \
                        stats['rejected'].get(display_name(l), 0) + 1
                    continue
                stats[how] = stats.get(how, 0) + 1
                if iid not in needs:
                    needs.append(iid)

        # -------- rewards (minus needs)
        rewards = {}
        for _, links in values(r['fields'], REWARD_LABELS):
            for l in links:
                if not usable_item(l, quest_titles, non_items_by_name):
                    continue
                iid, how = item_id(wiki, l, items_by_name, non_items_by_name,
                                   resolve, unresolved)
                if iid is None:
                    stats['rejected'][display_name(l)] = \
                        stats['rejected'].get(display_name(l), 0) + 1
                    continue
                stats[how] = stats.get(how, 0) + 1
                if iid in needs:
                    anomalies.append(
                        f"{t}: '{iid}' (UESP: '{l}') listed as both needs_item "
                        f"and reward -> kept as needs_item")
                    continue
                rewards[iid] = all_stages

        # -------- anomaly: fetch-type title with rewards but no needs
        if rewards and not needs and is_fetch_title(t):
            reward_desc = ', '.join(f"{iid}" for iid in sorted(rewards))
            anomalies.append(
                f"{t}: fetch-type title, needs=[], rewards=[{reward_desc}] "
                f"(check UESP page: the fetch item may be labeled 'Reward')")

        # -------- region
        region = region_of_quest(wiki, r['fields'], resolve, title=t)
        if not region and resolve:
            ns = t.split(':', 1)[0] if ':' in t else 'Morrowind'
            for c in r['cats']:
                m = re.match(r'^(Morrowind|Tribunal|Bloodmoon|Tamriel Rebuilt)-Quests-(.+)$', c)
                if m and slug(m.group(2)) != r['line']:
                    region = (place_region(wiki, f'{m.group(1)}:{m.group(2)}')
                              or m.group(2))
                    if region:
                        break

        if not r['ids'] and not re.search(r'(?:Quests|Main Quest)$', strip_ns(t)):
            no_ids.append(t)
        if not region and not re.search(r'(?:Quests|Main Quest)$', strip_ns(t)):
            no_region.append(t)
        if not r['ids'] and re.search(r'(?:Quests|Main Quest)$', strip_ns(t)):
            continue
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
                  'stats': stats, 'anomalies': anomalies}


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
    rep += ['', f'Item ids guessed from the page title ({len(info["unresolved"])}):']
    rep += [f'    {t} -> {s}' for t, s in sorted(set(info['unresolved']))]

    stats = info.get('stats') or {}
    rep += ['', 'Item id resolution stats:']
    rep += [f'    resolved from ESM JSON : {stats.get("esm", 0)}']
    rep += [f'    resolved from infobox : {stats.get("infobox", 0)}']
    rep += [f'    guessed (slug)         : {stats.get("slug", 0)}']
    if stats.get('rejected'):
        rep += ['', f'Item links rejected (not in ESM JSON) ({len(stats["rejected"])}):']
        rep += [f'    {name}  x{count}'
                for name, count in sorted(stats['rejected'].items(), key=lambda x: -x[1])]

    (outdir / 'quest_tree_report.txt').write_text('\n'.join(rep) + '\n', encoding='utf-8')

    anomalies = info.get('anomalies') or []
    if anomalies:
        (outdir / 'quest_tree_anomalies.txt').write_text(
            '\n'.join(anomalies) + '\n', encoding='utf-8')
    else:
        (outdir / 'quest_tree_anomalies.txt').write_text(
            '(no anomalies detected)\n', encoding='utf-8')

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
    ap.add_argument('--why', default=None, metavar='TEXT',
                    help='print where each trigger involving a quest title containing TEXT comes from')
    ap.add_argument('--esm-json', nargs='+', default=[], metavar='JSON',
                    help='tes3conv JSON dumps (morrowind.json tribunal.json bloodmoon.json '
                         'tr_mainland.json tamriel_data.json) used to resolve UESP item links '
                         'to real ESM IDs.')
    args = ap.parse_args()

    esm_items, esm_non_items = {}, {}
    if args.esm_json:
        print(f'loading {len(args.esm_json)} ESM JSON dump(s) for item resolution...',
              file=sys.stderr)
        esm_items, esm_non_items = load_esm_items(args.esm_json)
        print(f'  {len(esm_items)} item names, {len(esm_non_items)} non-item names indexed',
              file=sys.stderr)
    else:
        print('WARNING: no --esm-json given; item IDs will be guessed from page titles',
              file=sys.stderr)

    wiki = Wiki(pathlib.Path(args.outdir) / 'uesp_cache', args.delay, args.refresh)
    titles = crawl(wiki, args.limit)
    print(f'{len(titles)} candidate pages', file=sys.stderr)
    tree, info = build(wiki, titles, not args.no_resolve, args.why,
                       esm_items, esm_non_items)
    n = write_outputs(args.outdir, tree, info)
    print(f'{n} quests -> {args.outdir}/quest_tree.json '
          f'(see quest_tree_report.txt, quest_tree_anomalies.txt)')


if __name__ == '__main__':
    main()
