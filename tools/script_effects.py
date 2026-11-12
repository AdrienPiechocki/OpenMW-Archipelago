#!/usr/bin/env python3
"""Block-aware parsing of Morrowind scripts / dialogue results (ported from
enrich_quest_tree.py).

parse_script(script_id, text) -> [(kind, item_id, qty, journal_id|None)]
  kind = 'needed'  : Player->RemoveItem / Player->GetItemCount (item handed over / checked)
         'reward'  : Player->AddItem
Each effect is attributed to the journal modified INSIDE the same if/elseif/else block
(not to every Journal command of the script), so a branch only counts for its own journal.
Only commands on `Player->` are read: a bare RemoveItem in a dialogue result applies to the
speaking NPC, not to the player's quest items.

is_quest_item(id)   : False for generic stock (sc_*, ingred_*, misc_de_*, random lists...).
resolve_journal(..) : journal sub-ids / aliases (TR_M3_AT_DEED_C -> TR_M3_AT_DEED).
"""
from __future__ import annotations
import re

QUIET = True


def _warn(msg):
    if not QUIET:
        import sys
        print(msg, file=sys.stderr)


_warn_script = lambda sid, msg: _warn(msg)  # noqa: E731
# --------------------------------------------------------------- filtres
GENERIC_PREFIXES = (
    'random_', 'l_m_', 'l_n_', 'l_w_', 'l_i_', 'l_b_', 'l_e_', 'l_a_', 'l_c_',
    'p_', 'ingred_', 'misc_com_', 'misc_de_', 'sc_',
    'crate_', 'barrel_', 'urn_', 'com_',
    't_com_', 't_ingmine_', 't_ingflor_', 't_ingcrea_', 't_ingfood_',
    't_ing', 'potion_',
)

GENERIC_WITH_UNIQUE_EXCEPTION = (
    't_com_', 't_ingmine_', 't_ingflor_', 't_ingcrea_', 't_ingfood_',
    't_ing', 'potion_', 'ingred_',
)

TR_GENERIC = re.compile(
    r'^tr_(?:m\d+_)?(?:q_)?(?:ingred|ingr|misc|food|drink|potion)',
    re.I,
)

GOLD_ID = 'gold_001'
QTY_CAP = 5000

TRANSFORM_GROUPS = (
    {'bladepiece_01', 'bladepiece_02', 'bladepiece_03'},
)

JOURNAL_SUFFIXES = ('_C', '_CONT', '_FINAL', '_2', '_END')

MIN_PREFIX_LEN = 12

TRIVIAL_JOURNAL = re.compile(
    r'^(?:IC\d*_|IC_GUIDE|IC0_|BLADES_|BOOK_|A2_\d_|MS_|CO_STOCK|'
    r'CO_\d+[A-Z]?$|ROMANCE_|VA_|MERC_)',
    re.I,
)

UNIQUE_RE = re.compile(r'_(?:unique|uniq|uni|uq)(?:_|$)', re.I)


def _resolve_journal(jid, known_jids, aliases, sorted_known=None):
    jid = jid.upper()
    if jid in aliases:
        jid = aliases[jid]
    if jid in known_jids:
        return jid
    for suf in JOURNAL_SUFFIXES:
        if jid + suf in known_jids:
            return jid + suf
    if sorted_known is None:
        sorted_known = sorted(known_jids, key=len, reverse=True)
    for k in sorted_known:
        if len(k) >= MIN_PREFIX_LEN and jid.startswith(k):
            return k
    return None


def _combine_qty(existing, new, item_id):
    if existing is None:
        return new
    if existing == new:
        return existing
    if UNIQUE_RE.search(item_id):
        return 1
    return max(existing, new)


def is_quest_item(item_id: str) -> bool:
    if not item_id:
        return False
    low = item_id.lower()
    if low == GOLD_ID:
        return True
    if TR_GENERIC.match(low):
        return False
    if re.search(r'_(?:unique|uniq|uni|uq)(?:_|$)', low):
        return True
    if low.startswith('key_'):
        return True
    if low.startswith('bk_'):
        return True
    for pref in GENERIC_WITH_UNIQUE_EXCEPTION:
        if low.startswith(pref):
            return bool(re.search(r'_(?:unique|uniq|uni|uq)(?:_|$)', low))
    if low.startswith(GENERIC_PREFIXES):
        return False
    if not re.search(r'[a-z]', low):
        return False
    return True


# --------------------------------------------------------- regex de script
REMOVE_QUOTED = re.compile(r'Player->RemoveItem\s+"([^"]+)"\s+(-?\d+)', re.I)
REMOVE_BARE   = re.compile(r'Player->RemoveItem\s+([A-Za-z0-9_\'.]+)\s+(-?\d+)', re.I)
ADD_QUOTED    = re.compile(r'Player->AddItem\s+"([^"]+)"\s+(\d+)', re.I)
ADD_BARE      = re.compile(r'Player->AddItem\s+([A-Za-z0-9_\'.]+)\s+(\d+)', re.I)
HAS_CMP       = re.compile(
    r'Player->GetItemCount\s+"?([A-Za-z0-9_\'.]+)"?\s*(>=|<=|==|=|<|>)\s*(\d+)', re.I)
HAS_QUOTED    = re.compile(r'Player->GetItemCount\s+"([^"]+)"', re.I)
HAS_BARE      = re.compile(r'Player->GetItemCount\s+([A-Za-z0-9_\'.]+)', re.I)

JOURNAL_MOD  = re.compile(r'\bJournal\s+([A-Za-z0-9_]+)\s+(\d+)', re.I)
JOURNAL_COND = re.compile(r'GetJournalIndex\s+"?([A-Za-z0-9_]+)"?', re.I)


# --------------------------------------------------------- parseur de blocs
class _Block:
    __slots__ = ('kind', 'cond', 'body', 'branches',
                 'journal_mods', 'journal_conds', 'has_early_return')
    def __init__(self, kind, cond=''):
        self.kind = kind
        self.cond = cond
        self.body = []
        self.branches = []
        self.journal_mods = []
        self.journal_conds = []
        self.has_early_return = False


def _clean_line(line):
    return re.sub(r';.*', '', line).strip()


def _extract_cond(line, kw_len):
    p = line.find('(', kw_len)
    if p < 0:
        return ''
    depth, buf = 0, []
    for ch in line[p:]:
        if ch == '(':
            depth += 1
            if depth > 1:
                buf.append(ch)
        elif ch == ')':
            depth -= 1
            if depth > 0:
                buf.append(ch)
            else:
                break
        else:
            buf.append(ch)
    return ''.join(buf).strip()


def _build_blocks(text, script_id='?'):
    root = _Block('root')
    stack = [root]

    for raw in text.splitlines():
        line = _clean_line(raw)
        if not line:
            continue
        low = line.lower()

        if low.startswith('begin ') or low == 'end':
            continue

        # Forme inline : if (cond) instr endif  (sur une seule ligne)
        m = re.match(r'^if\s*\((.+?)\)\s*(.+?)\s*endif\s*$', line, re.I)
        if m:
            blk = _Block('if', m.group(1))
            blk.body.append(('stmt', m.group(2)))
            stack[-1].body.append(blk)
            for jm in JOURNAL_MOD.finditer(m.group(2)):
                blk.journal_mods.append(jm.group(1).upper())
            continue

        if low.startswith('if ') or low.startswith('if('):
            blk = _Block('if', _extract_cond(line, 2))
            stack[-1].body.append(blk)
            stack.append(blk)
            continue

        if low.startswith('elseif ') or low.startswith('elseif('):
            if len(stack) >= 2 and stack[-1].kind in ('if', 'elseif'):
                prev = stack.pop()
                br = _Block('elseif', _extract_cond(line, 6))
                prev.branches.append(br)
                stack.append(br)
            else:
                _warn_script(script_id,
                             f'!! [{script_id}] elseif orphelin: {line[:80]}')
            continue

        if low == 'else':
            if len(stack) >= 2 and stack[-1].kind in ('if', 'elseif'):
                prev = stack.pop()
                br = _Block('else')
                prev.branches.append(br)
                stack.append(br)
            else:
                _warn_script(script_id,
                             f'!! [{script_id}] else orphelin: {line[:80]}')
            continue

        if low in ('endif', 'endwhile'):
            if len(stack) > 1:
                stack.pop()
            else:
                _warn_script(script_id,
                             f'!! [{script_id}] {line} sans bloc ouvert')
            continue

        if low.startswith('while ') or low.startswith('while('):
            blk = _Block('while', _extract_cond(line, 5))
            stack[-1].body.append(blk)
            stack.append(blk)
            continue

        if low == 'return':
            stack[-1].has_early_return = True
            continue

        stack[-1].body.append(('stmt', line))
        for m2 in JOURNAL_MOD.finditer(line):
            stack[-1].journal_mods.append(m2.group(1).upper())
        for m2 in JOURNAL_COND.finditer(line):
            stack[-1].journal_conds.append(m2.group(1).upper())

    _collect_journal_mods(root)
    return root


def _collect_journal_mods(block):
    for item in block.body:
        if isinstance(item, _Block):
            _collect_journal_mods(item)
            block.journal_mods.extend(item.journal_mods)
    for br in block.branches:
        _collect_journal_mods(br)
        block.journal_mods.extend(br.journal_mods)


def _pick_target_journals(block, inherited, script_id='?'):
    """Retourne la liste des journaux cibles pour ce bloc.

    Un bloc peut modifier plusieurs journaux simultanément (avancer deux
    quêtes en parallèle) ; dans ce cas on duplique les effets pour chacun.
    """
    direct = []
    for item in block.body:
        if isinstance(item, tuple) and item[0] == 'stmt':
            for m in JOURNAL_MOD.finditer(item[1]):
                direct.append(m.group(1).upper())
    if direct:
        unique = sorted(set(direct))
        if len(unique) > 1:
            _warn_script(script_id,
                         f'!! [{script_id}] multi-journal: {unique}')
        return unique
    unique = sorted(set(block.journal_mods))
    if len(unique) == 1:
        return unique
    return [inherited] if inherited else []


def _scan_stmt(v, child, out, script_id='?'):
    for m in REMOVE_QUOTED.finditer(v):
        out.append(('needed', m.group(1), max(1, int(m.group(2))), child))
    for m in REMOVE_BARE.finditer(v):
        out.append(('needed', m.group(1), max(1, int(m.group(2))), child))
    for m in HAS_CMP.finditer(v):
        op, n = m.group(2), int(m.group(3))
        # `GetItemCount x < 1` / `== 0` checks that the player does NOT have the item
        if op in ('<', '<=') or (op in ('==', '=') and n == 0):
            continue
        qty = n if op in ('>=', '==', '=') and n > 0 else 1
        item_id = m.group(1)
        if UNIQUE_RE.search(item_id) and qty > 1:
            qty = 1
        out.append(('needed', item_id, min(qty, QTY_CAP), child))
    seen = {m.group(1).lower() for m in HAS_CMP.finditer(v)}
    for m in HAS_QUOTED.finditer(v):
        if m.group(1).lower() not in seen:
            out.append(('needed', m.group(1), 1, child))
    for m in HAS_BARE.finditer(v):
        if m.group(1).lower() not in seen:
            out.append(('needed', m.group(1), 1, child))
    for m in ADD_QUOTED.finditer(v):
        out.append(('reward', m.group(1), max(1, int(m.group(2))), child))
    for m in ADD_BARE.finditer(v):
        out.append(('reward', m.group(1), max(1, int(m.group(2))), child))


def _flatten_effects(block, inherited_journals, script_id='?'):
    out = []

    if block.has_early_return and not block.journal_mods:
        return out

    inherited = inherited_journals[0] if inherited_journals else None
    children = _pick_target_journals(block, inherited, script_id)
    if not children:
        children = inherited_journals or [None]

    # the block's own condition: `if ( Player->GetItemCount "x" >= 1 )` is where most
    # "player must have the item" checks live (the old scan only read statements)
    if block.cond:
        for child in children:
            _scan_stmt(block.cond, child, out, script_id)

    for item in block.body:
        if isinstance(item, _Block):
            out.extend(_flatten_effects(item, children, script_id))
            continue
        t, v = item
        for child in children:
            _scan_stmt(v, child, out, script_id)

    for br in block.branches:
        out.extend(_flatten_effects(br, children, script_id))

    return out


def parse_script(script_id, text):
    if not text:
        return []
    root = _build_blocks(text, script_id)
    effects = _flatten_effects(root, [None], script_id)

    if effects and all(e[3] is None for e in effects):
        mods = {m.group(1).upper() for m in JOURNAL_MOD.finditer(text)}
        if len(mods) == 1:
            j = mods.pop()
            effects = [(k, i, q, j) for (k, i, q, _) in effects]
    else:
        effects = [e for e in effects if e[3] is not None]

    return effects


