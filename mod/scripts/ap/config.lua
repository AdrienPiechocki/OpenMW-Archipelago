-- Configuration du mod Archipelago pour OpenMW.
--
-- C'est le seul endroit a modifier pour changer de serveur / de slot.
-- Le bridge Python peut aussi etre configure avec les variables
-- d'environnement AP_HOST, AP_PORT, AP_SLOT, AP_PASSWORD, AP_DATA_DIR,
-- mais le mod lance toujours le bridge avec les valeurs ci-dessous.
return {
  -- Serveur Archipelago
  host = 'archipelago.gg',
  port = 64423,
  slot = 'TestMW',
  password = '',

  -- Bridge Python
  -- ~ est remplace par le dossier personnel.
  data_dir = '~/.local/share/openmw/ap',
  python = 'python3',
  bridge_path = '~/Projets/OpenMW-Archipelago/bridge/bridge.py',
  auto_start_bridge = true,

  -- Gameplay
  deathlink = true,
  poll_interval = 1.0, -- secondes
}
