"""Test for building the bridge's item notifications.

From the repository root:
    python3 tools/test_bridge_notify.py
"""
import os
import sys
import tempfile

os.environ['AP_DATA_DIR'] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bridge'))
import bridge  # noqa: E402

ME, BOB = 1, 2
players = {ME: 'Adrien', BOB: 'Bob'}
games = {ME: 'Morrowind OpenMW', BOB: 'Hollow Knight'}
names = {
    'Morrowind OpenMW': {'items': {10: 'Ebony Dagger'}, 'locations': {500: 'Fargoth Quest'}},
    'Hollow Knight': {'items': {20: 'Mothwing Cloak'}, 'locations': {600: 'Dirtmouth Chest'}},
}

fails = 0


def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f'FAIL {name}: got {got!r}, want {want!r}')
    else:
        print(f'ok   {name}')


def send(receiving, owner, item, loc, flags=0, kind='ItemSend'):
    return {'cmd': 'PrintJSON', 'type': kind, 'receiving': receiving,
            'item': {'item': item, 'location': loc, 'player': owner, 'flags': flags}}


def build(msg):
    return bridge.build_notify(msg, ME, players, games, names)


# Received from another player: item name in OUR game, sender = owner.
check('recv', build(send(ME, BOB, 10, 600, 1)),
      {'t': 'notify', 'item': 'Ebony Dagger', 'flags': 1, 'dir': 'recv',
       'player': 'Bob', 'location': 'Dirtmouth Chest'})

# Sent to another player: item name in THEIR game, location in ours.
check('send', build(send(BOB, ME, 20, 500, 2)),
      {'t': 'notify', 'item': 'Mothwing Cloak', 'flags': 2, 'dir': 'send',
       'player': 'Bob', 'location': 'Fargoth Quest'})

# Item from our world for us: a single notification, dir = self.
check('self', build(send(ME, ME, 10, 500, 4)),
      {'t': 'notify', 'item': 'Ebony Dagger', 'flags': 4, 'dir': 'self',
       'location': 'Fargoth Quest'})

# Server command (/send): received without a sender.
n = build(send(ME, 0, 10, -1, 0, kind='ItemCheat'))
check('cheat dir', n and n['dir'], 'recv')
check('cheat no player', n and 'player' in n, False)

# Unrelated to us: ignored.
check('unrelated', build(send(BOB, BOB, 20, 600)), None)
check('other kind', build({'cmd': 'PrintJSON', 'type': 'Chat', 'message': 'hi'}), None)
check('no slot', bridge.build_notify(send(ME, BOB, 10, 600), None, players, games, names), None)

# Unknown name: readable fallback.
n = build(send(ME, BOB, 999, 777))
check('unknown item', n['item'], 'item #999')
check('unknown location absent', 'location' in n, False)

# Strictly increasing ids, even within the same millisecond.
a, b = bridge.next_notify_id(), bridge.next_notify_id()
check('ids increase', b > a, True)

# Games to download: empty cache -> all; identical checksum -> none.
check('missing all', bridge.missing_games({'Hollow Knight', None}, {}), ['Hollow Knight'])
bridge.names['Hollow Knight'] = {'checksum': 'abc', 'items': {}, 'locations': {}}
check('cached ok', bridge.missing_games({'Hollow Knight'}, {'Hollow Knight': 'abc'}), [])
check('checksum changed', bridge.missing_games({'Hollow Knight'}, {'Hollow Knight': 'zzz'}), ['Hollow Knight'])

if fails:
    print(f'{fails} failure(s)')
    sys.exit(1)
print('all bridge notify tests passed')
