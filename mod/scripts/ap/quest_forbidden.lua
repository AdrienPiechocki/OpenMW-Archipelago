-- Quests that must never progress while one of their `goals` is selected.
--
-- "A Cure for Vampirism" (MS_VampireCure) removes the player's vampirism for good, which would make
-- the final quest of the chosen vampire clan impossible (soft-lock of the goal). While a vampire clan
-- goal is selected, the quest is held at stage 0 (journal reset, like the locked Daedric quests).
-- The apworld removes the matching check (see FORBIDDEN_QUESTS in options.py): keep both in sync
-- (tools/test_vampire_options.py checks it).
--
-- Pure module (no OpenMW dependency) so it can be tested with plain Lua.
local M = {}

M.QUESTS = {
  {
    quest = 'ms_vampirecure',
    name  = 'A Cure for Vampirism',
    goals = { 'vampire_aundae', 'vampire_berne', 'vampire_quarra', 'vampire_baluath', 'vampire_orlukh' },
  },
}

-- True if the entry applies: at least one of its goals is selected. `goalActive(key)` -> boolean.
function M.applies(entry, goalActive)
  for _, g in ipairs(entry.goals) do
    if goalActive(g) then return true end
  end
  return false
end

return M
