-- Archipelago mod configuration for OpenMW.
--
-- This is the only place to edit to change server / slot.
-- The Python bridge can also be configured with the environment
-- variables AP_HOST, AP_PORT, AP_SLOT, AP_PASSWORD, AP_DATA_DIR,
-- but the mod always launches the bridge with the values below.
return {
  -- Archipelago server
  host = 'archipelago.gg',
  port = 64423,
  slot = 'TestMW',
  password = '',

  -- Bridge Python
  -- ~ is replaced by the home directory.
  data_dir = '~/.local/share/openmw/ap',
  python = 'python3',
  bridge_path = '~/.local/share/openmw/ap/bridge.py',
  auto_start_bridge = true,

  -- Gameplay
  deathlink = true,
  poll_interval = 1.0, -- seconds
}
