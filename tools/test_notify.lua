-- Test des notifications d'items Archipelago (mod/scripts/ap/notify.lua).
--
-- Depuis la racine du depot :
--   luajit tools/test_notify.lua
package.path = 'mod/?.lua;' .. package.path

local notify = require('scripts.ap.notify')

local failures = 0
local function check(name, actual, expected)
  if actual ~= expected then
    failures = failures + 1
    print(('FAIL %s: got %s, expected %s'):format(name, tostring(actual), tostring(expected)))
  else
    print(('ok   %s'):format(name))
  end
end

-- Flags : 1 progression, 2 utile, 4 piege (le piege prime).
check('no flag', notify.flagTag(0), '')
check('progression', notify.flagTag(1), ' [Progression]')
check('useful', notify.flagTag(2), ' [Utile]')
check('trap', notify.flagTag(4), ' [Piège]')
check('trap wins', notify.flagTag(5), ' [Piège]')
check('nil flags', notify.flagTag(nil), '')

-- Formats.
check('recv', notify.format({ dir = 'recv', item = 'Ebony Dagger', player = 'Bob', flags = 1 }),
  'Archipelago : Bob vous envoie Ebony Dagger [Progression]')
check('recv without sender', notify.format({ dir = 'recv', item = 'Gold' }),
  'Archipelago : vous recevez Gold')
check('send', notify.format({ dir = 'send', item = 'Cloak', player = 'Bob' }),
  'Archipelago : vous envoyez Cloak à Bob')
check('send quest check', notify.format({ dir = 'send', item = 'Cloak', player = 'Bob', location = 'Fargoth' }),
  'Archipelago : Cloak (Fargoth) obtenu [check complété] -> Bob')
check('send quest check with flag', notify.format({ dir = 'send', item = 'Cloak', player = 'Bob', location = 'Fargoth', flags = 2 }),
  'Archipelago : Cloak [Utile] (Fargoth) obtenu [check complété] -> Bob')
check('self', notify.format({ dir = 'self', item = 'Dagger', location = 'Fargoth' }),
  'Archipelago : Dagger (Fargoth) obtenu [check complété]')
check('self quest check with flag', notify.format({ dir = 'self', item = 'Dagger', location = 'Fargoth', flags = 1 }),
  'Archipelago : Dagger [Progression] (Fargoth) obtenu [check complété]')
check('self without location', notify.format({ dir = 'self', item = 'Gold' }),
  'Archipelago : vous avez trouvé Gold')
check('empty location falls back', notify.format({ dir = 'self', item = 'Gold', location = '' }),
  'Archipelago : vous avez trouvé Gold')
check('percent in names is kept', notify.format({ dir = 'send', item = '100% Cloak', player = 'B%d' }),
  'Archipelago : vous envoyez 100% Cloak à B%d')
check('unknown dir', notify.format({ dir = 'x', item = 'a' }), nil)
check('not a table', notify.format(nil), nil)

-- Filtre : id nouveau et recent.
check('new id', notify.accept({ id = 5, ts = 1000 }, 4, 1010), true)
check('same id', notify.accept({ id = 5, ts = 1000 }, 5, 1010), false)
check('older id', notify.accept({ id = 3, ts = 1000 }, 5, 1010), false)
check('stale', notify.accept({ id = 6, ts = 1000 }, 5, 1000 + notify.MAX_AGE + 1), false)
check('age limit ok', notify.accept({ id = 6, ts = 1000 }, 5, 1000 + notify.MAX_AGE), true)
check('no ts accepted', notify.accept({ id = 6 }, 5, 99999), true)
check('no id', notify.accept({ ts = 1000 }, 5, 1010), false)
check('first ever', notify.accept({ id = 1 }, nil, nil), true)

if failures > 0 then
  print(('%d failure(s)'):format(failures))
  os.exit(1)
end
print('all notify tests passed')
