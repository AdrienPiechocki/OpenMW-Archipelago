-- "+10 levels" Archipelago item.
--
-- We do not modify the current level directly: we add vanilla level-up
-- progress. The player thus gets the real level-up windows (attribute
-- choice, health gain) by sleeping, instead of a plain level number
-- without benefits.
local M = {}

-- Must stay in sync with apworld/morrowind_openmw/items.py.
M.ITEM_ID = 7703000
M.LEVELS = 10
M.DEFAULT_LEVEL_UP_TOTAL = 10

function M.progressGain(levels, levelUpTotal)
  levels = tonumber(levels) or 0
  levelUpTotal = tonumber(levelUpTotal) or M.DEFAULT_LEVEL_UP_TOTAL
  if levels < 0 then levels = 0 end
  if levelUpTotal <= 0 then levelUpTotal = M.DEFAULT_LEVEL_UP_TOTAL end
  return levels * levelUpTotal
end

function M.newProgress(current, levels, levelUpTotal)
  current = tonumber(current) or 0
  if current < 0 then current = 0 end
  return current + M.progressGain(levels, levelUpTotal)
end

return M
