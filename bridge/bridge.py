"""Bridge Archipelago <-> OpenMW (websocket <-> JSONL files).

Fixes compared to the previous version:
  * 'connected' is only set when Connected is received (before, checks sent
    before authentication were lost for good);
  * on each connection, all known checks are resent (the server
    deduplicates them);
  * single-instance lock (flock): no more double connection;
  * heartbeat independent of the connection;
  * inactivity watchdog that works even when the connection is open;
  * reads out.jsonl in binary (correct offsets, partial lines).
"""
import asyncio
import fcntl
import json
import os
import pathlib
import sys
import time
import uuid

try:
    import websockets
except Exception as e:  # pragma: no cover
    websockets = None
    print('websockets import error:', e, flush=True)

DIR = pathlib.Path(os.getenv('AP_DATA_DIR') or (pathlib.Path.home() / '.local/share/openmw/ap'))
DIR.mkdir(parents=True, exist_ok=True)
OUT = DIR / 'out.jsonl'
INP = DIR / 'in.jsonl'
STATE = DIR / 'state.json'
HEARTBEAT = DIR / 'bridge.heartbeat'
LOCK = DIR / 'bridge.lock'
DATAPKG = DIR / 'datapackage.json'

HOST = os.getenv('AP_HOST', '127.0.0.1')
PORT = int(os.getenv('AP_PORT', '38281'))
SLOT = os.getenv('AP_SLOT', 'TestMW')
PASSWORD = os.getenv('AP_PASSWORD', '')
DEATHLINK = os.getenv('AP_DEATHLINK', '1') not in ('0', 'false', 'False', '')
INACTIVITY_TIMEOUT = float(os.getenv('AP_INACTIVITY', '60'))

DEFAULT_VERSION = {'major': 0, 'minor': 6, 'build': 8, 'class': 'Version'}

last_activity = time.time()
state = {
    'checked': set(),
    'goal_sent': False,
    'seed_name': None,
}

# Current session state (not persisted), used for item notifications: slot
# number, player names, game of each slot, datapackage checksums announced by
# the server, PrintJSON waiting for the datapackage.
session = {
    'slot': None,
    'players': {},       # slot -> alias / name
    'games': {},         # slot -> game name
    'checksums': {},     # game -> checksum (RoomInfo)
    'ready': False,      # datapackage available for all needed games
    'buffer': [],        # PrintJSON received before 'ready'
    'last_id': 0,        # last notification id emitted
}
# game -> {'checksum': str, 'items': {id: name}, 'locations': {id: name}}
names = {}


# --------------------------------------------------------------------------
# Single-instance lock
# --------------------------------------------------------------------------
def acquire_lock():
    f = open(LOCK, 'a+')
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print('BRIDGE: another instance is already running, stopping.', flush=True)
        sys.exit(0)
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    return f  # keep the reference: the lock is held as long as the file is open


# --------------------------------------------------------------------------
# Persistent state
# --------------------------------------------------------------------------
def load_state():
    try:
        if STATE.exists():
            d = json.loads(STATE.read_text())
            state['checked'] = set(int(x) for x in d.get('checked', []))
            state['goal_sent'] = bool(d.get('goal_sent', False))
            state['seed_name'] = d.get('seed_name')
    except Exception as e:
        print('state load error:', e, flush=True)


def save_state():
    try:
        tmp = STATE.with_suffix('.tmp')
        tmp.write_text(json.dumps({
            'checked': sorted(state['checked']),
            'goal_sent': state['goal_sent'],
            'seed_name': state['seed_name'],
        }))
        tmp.replace(STATE)
    except Exception as e:
        print('state save error:', e, flush=True)


def load_datapackage_cache():
    try:
        if DATAPKG.exists():
            d = json.loads(DATAPKG.read_text())
            for game, g in d.items():
                names[game] = {
                    'checksum': g.get('checksum'),
                    'items': {int(v): k for k, v in g.get('item_name_to_id', {}).items()},
                    'locations': {int(v): k for k, v in g.get('location_name_to_id', {}).items()},
                }
    except Exception as e:
        print('datapackage load error:', e, flush=True)


def save_datapackage_cache():
    try:
        out = {}
        for game, g in names.items():
            out[game] = {
                'checksum': g.get('checksum'),
                'item_name_to_id': {v: k for k, v in g['items'].items()},
                'location_name_to_id': {v: k for k, v in g['locations'].items()},
            }
        tmp = DATAPKG.with_suffix('.tmp')
        tmp.write_text(json.dumps(out))
        tmp.replace(DATAPKG)
    except Exception as e:
        print('datapackage save error:', e, flush=True)


def missing_games(games, checksums):
    """Games whose datapackage is not (or no longer) cached."""
    out = []
    for game in sorted(g for g in games if g):
        cached = names.get(game)
        want = checksums.get(game)
        if cached is None or (want is not None and cached.get('checksum') != want):
            out.append(game)
    return out


def build_notify(msg, my_slot, players, games, names_by_game):
    """PrintJSON ItemSend / ItemCheat -> 'notify' message for the mod.

    Returns None if the message does not concern this slot (neither received
    nor sent).
    dir: 'recv' (received from another player), 'send' (sent to another player),
    'self' (item from our world for us). An item's name is resolved in the
    game of the player receiving it, a location's name in the game of the
    player who owns it.
    """
    kind = msg.get('type')
    if kind not in ('ItemSend', 'ItemCheat'):
        return None
    item = msg.get('item')
    receiving = msg.get('receiving')
    if not isinstance(item, dict) or receiving is None or my_slot is None:
        return None
    owner = item.get('player')  # slot whose location contained the item
    mine_recv = receiving == my_slot
    mine_send = kind == 'ItemSend' and owner == my_slot
    if not (mine_recv or mine_send):
        return None

    item_id = item.get('item')
    loc_id = item.get('location')
    item_name = names_by_game.get(games.get(receiving), {}).get('items', {}).get(item_id)
    loc_name = names_by_game.get(games.get(owner), {}).get('locations', {}).get(loc_id)

    out = {
        't': 'notify',
        'item': item_name or f'item #{item_id}',
        'flags': int(item.get('flags') or 0),
    }
    if mine_recv and mine_send:
        out['dir'] = 'self'
    elif mine_recv:
        out['dir'] = 'recv'
        if kind == 'ItemSend' and owner in players:
            out['player'] = players[owner]
    else:
        out['dir'] = 'send'
        out['player'] = players.get(receiving, f'player {receiving}')
    if loc_name:
        out['location'] = loc_name
    return out


def next_notify_id():
    """Strictly increasing id (Unix ms): the mod uses it to never display a
    notification twice when it re-reads in.jsonl."""
    session['last_id'] = max(session['last_id'] + 1, int(time.time() * 1000))
    return session['last_id']


def emit_notify(msg):
    n = build_notify(msg, session['slot'], session['players'], session['games'], names)
    if n:
        n['id'] = next_notify_id()
        n['ts'] = int(time.time())
        write_in(n)
        print('BRIDGE: notify', n, flush=True)


def flush_buffered_prints():
    buf, session['buffer'] = session['buffer'], []
    for m in buf:
        emit_notify(m)


# --------------------------------------------------------------------------
# Files to the mod
# --------------------------------------------------------------------------
def write_sync():
    """Replaces in.jsonl with a synchronization marker."""
    try:
        with open(INP, 'w') as f:
            f.write(json.dumps({'t': 'sync', 'id': int(time.time() * 1000)}) + '\n')
            f.flush()
    except Exception as e:
        print('sync write error:', e, flush=True)


def write_in(obj):
    try:
        with open(INP, 'a') as f:
            f.write(json.dumps(obj) + '\n')
            f.flush()
    except Exception as e:
        print('write_in error:', e, flush=True)


async def ws_send(ws, cmds):
    await ws.send(json.dumps(cmds))


# --------------------------------------------------------------------------
# Background tasks
# --------------------------------------------------------------------------
async def heartbeat_loop():
    """Heartbeat read by the mod: independent of the connection state."""
    while True:
        try:
            HEARTBEAT.write_text(str(time.time()))
        except Exception:
            pass
        await asyncio.sleep(1)


async def watchdog_loop():
    """Stops the bridge when the game stops responding."""
    while True:
        await asyncio.sleep(5)
        if time.time() - last_activity > INACTIVITY_TIMEOUT:
            print('BRIDGE: inactivity detected, stopping.', flush=True)
            try:
                if INP.exists():
                    INP.unlink()
            except Exception:
                pass
            try:
                HEARTBEAT.unlink()
            except Exception:
                pass
            os._exit(0)


async def tail_out(ws_ref, connected_event):
    """Reads new lines from out.jsonl and processes them."""
    global last_activity
    offset = 0
    while True:
        try:
            if OUT.exists():
                size = OUT.stat().st_size
                if size < offset:  # file truncated
                    offset = 0
                if size > offset:
                    with open(OUT, 'rb') as f:
                        f.seek(offset)
                        data = f.read()
                    last_activity = time.time()
                    # only consume complete lines
                    end = data.rfind(b'\n')
                    if end >= 0:
                        offset += end + 1
                        chunk = data[:end].decode('utf-8', errors='replace')
                        for line in chunk.split('\n'):
                            line = line.strip()
                            if line:
                                await handle_out(line, ws_ref, connected_event)
        except Exception as e:
            print('tail error:', repr(e), flush=True)
        await asyncio.sleep(0.5)


async def handle_out(line, ws_ref, connected_event):
    try:
        msg = json.loads(line)
    except Exception:
        return
    t = msg.get('t')
    ws = ws_ref['ws']
    online = connected_event.is_set() and ws is not None

    if t == 'check':
        try:
            cid = int(msg['id'])
        except Exception:
            return
        if cid in state['checked']:
            return
        # Always remember: if not yet authenticated, the check will be sent
        # by the 'Connected' handler.
        state['checked'].add(cid)
        save_state()
        if online:
            print('BRIDGE: sending check', cid, flush=True)
            await ws_send(ws, [{'cmd': 'LocationChecks', 'locations': [cid]}])
    elif t == 'death':
        if online and DEATHLINK:
            await ws_send(ws, [{
                'cmd': 'Bounce',
                'tags': ['DeathLink'],
                'data': {'time': time.time(), 'source': SLOT, 'cause': msg.get('cause', '')},
            }])
    elif t == 'goal':
        if not state['goal_sent']:
            state['goal_sent'] = True
            save_state()
        if online:
            await ws_send(ws, [{'cmd': 'StatusUpdate', 'status': 30}])
    # 'hello' and 'heartbeat': only for last_activity


# --------------------------------------------------------------------------
# Server reception
# --------------------------------------------------------------------------
async def recv_loop(ws, connected_event):
    async for raw in ws:
        try:
            msgs = json.loads(raw)
        except Exception:
            continue
        if not isinstance(msgs, list):
            msgs = [msgs]
        for m in msgs:
            cmd = m.get('cmd')
            if cmd == 'Connected':
                print('BRIDGE connected to server, slot', m.get('slot'), flush=True)
                sd = m.get('slot_data') or {}
                options = sd.get('options', {})
                if 'goal' in sd:
                    options = dict(options)
                    options['goal'] = sd.get('goal')
                # New session: replaces in.jsonl.
                write_sync()
                write_in({'t': 'config', 'goal': sd.get('goal'), 'options': options})
                connected_event.set()
                # Item notifications: slot identity and datapackage.
                session['slot'] = m.get('slot')
                session['players'] = {
                    p.get('slot'): (p.get('alias') or p.get('name'))
                    for p in (m.get('players') or [])
                }
                session['games'] = {}
                for k, info in (m.get('slot_info') or {}).items():
                    try:
                        session['games'][int(k)] = info.get('game')
                    except (TypeError, ValueError):
                        pass
                session['buffer'] = []
                todo = missing_games(set(session['games'].values()), session['checksums'])
                session['ready'] = not todo
                if todo:
                    await ws_send(ws, [{'cmd': 'GetDataPackage', 'games': todo}])
                # Resend all known checks (the server deduplicates).
                if state['checked']:
                    await ws_send(ws, [{'cmd': 'LocationChecks',
                                        'locations': sorted(state['checked'])}])
                if state['goal_sent']:
                    await ws_send(ws, [{'cmd': 'StatusUpdate', 'status': 30}])
            elif cmd == 'ConnectionRefused':
                print('BRIDGE: connection refused:', m.get('errors'), flush=True)
            elif cmd == 'ReceivedItems':
                idx = m.get('index', 0)
                for i, it in enumerate(m.get('items', [])):
                    write_in({'t': 'item', 'idx': idx + i, 'id': it.get('item')})
            elif cmd == 'Bounce':
                if 'DeathLink' in (m.get('tags') or []) and DEATHLINK:
                    data = m.get('data') or {}
                    src = data.get('source')
                    if src and src != SLOT:
                        write_in({'t': 'deathlink', 'from': src})
            elif cmd == 'DataPackage':
                games = ((m.get('data') or {}).get('games')) or {}
                for game, g in games.items():
                    names[game] = {
                        'checksum': g.get('checksum') or session['checksums'].get(game),
                        'items': {int(v): k for k, v in (g.get('item_name_to_id') or {}).items()},
                        'locations': {int(v): k for k, v in (g.get('location_name_to_id') or {}).items()},
                    }
                save_datapackage_cache()
                session['ready'] = True
                flush_buffered_prints()
            elif cmd == 'PrintJSON':
                if m.get('type') in ('ItemSend', 'ItemCheat'):
                    if session['ready']:
                        emit_notify(m)
                    elif len(session['buffer']) < 200:
                        session['buffer'].append(m)
            elif cmd == 'InvalidPacket':
                print('BRIDGE: InvalidPacket:', m, flush=True)


# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------
async def run_once():
    scheme = 'wss' if HOST not in ('127.0.0.1', 'localhost') else 'ws'
    uri = f'{scheme}://{HOST}:{PORT}'
    ws_ref = {'ws': None}
    connected_event = asyncio.Event()  # set only on 'Connected'

    async with websockets.connect(uri, max_size=None) as ws:
        ws_ref['ws'] = ws
        version = None
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            msgs = json.loads(raw)
            if not isinstance(msgs, list):
                msgs = [msgs]
            for m in msgs:
                if m.get('cmd') == 'RoomInfo':
                    version = m.get('version')
                    session['checksums'] = m.get('datapackage_checksums') or {}
                    seed_name = m.get('seed_name')
                    if seed_name is not None and seed_name != state['seed_name']:
                        print('BRIDGE: new seed detected, resetting checks', flush=True)
                        state['checked'] = set()
                        state['goal_sent'] = False
                        state['seed_name'] = seed_name
                        save_state()
        except Exception as e:
            print('BRIDGE: no RoomInfo:', repr(e), flush=True)

        await ws_send(ws, [{
            'cmd': 'Connect',
            'game': 'Morrowind OpenMW',
            'name': SLOT,
            'password': PASSWORD,
            'uuid': str(uuid.uuid4()),
            'version': version or DEFAULT_VERSION,
            'items_handling': 7,
            'tags': (['DeathLink'] if DEATHLINK else []),
            'slot_data': True,
        }])

        recv_task = asyncio.create_task(recv_loop(ws, connected_event))
        tail_task = asyncio.create_task(tail_out(ws_ref, connected_event))
        done, pending = await asyncio.wait({recv_task, tail_task},
                                           return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        for t in done:
            if t.exception():
                raise t.exception()


async def main():
    load_state()
    load_datapackage_cache()
    OUT.touch(exist_ok=True)
    asyncio.create_task(heartbeat_loop())
    asyncio.create_task(watchdog_loop())
    backoff = 1
    while True:
        try:
            await run_once()
            print('BRIDGE: connection closed', flush=True)
            backoff = 1
        except Exception as e:
            print('BRIDGE connection error:', repr(e), flush=True)
        print(f'reconnecting in {backoff}s...', flush=True)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30)


if __name__ == '__main__':
    if websockets is None:
        sys.exit('websockets missing: pip install websockets')

    # Auto-daemonization when launched by the OpenMW mod.
    if os.getenv('AP_DAEMON') == '1':
        try:
            if os.fork() > 0:
                os._exit(0)
        except OSError:
            pass
        os.setsid()

    # Lock BEFORE redirecting the log: a 2nd instance must not overwrite
    # the first one's log.
    _lock = acquire_lock()

    if os.getenv('AP_DAEMON') == '1':
        try:
            fd = os.open(str(DIR / 'bridge.log'), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            os.dup2(fd, 1)
            os.dup2(fd, 2)
            os.close(fd)
        except Exception:
            pass
        try:
            devnull = os.open(os.devnull, os.O_RDONLY)
            os.dup2(devnull, 0)
            os.close(devnull)
        except Exception:
            pass

    asyncio.run(main())
