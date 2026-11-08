-- Starting bonuses (YAML options `attribute_<id>` and `skill_<id>`).
--
-- Once the tutorial is over (character creation finished), the player gets
-- the bonus chosen for each attribute and each skill:
--   * stat.base = min(100, base + bonus), never lowered,
--   * a bonus of 0 (default) leaves the stat unchanged (vanilla).
-- The server sends only the non-zero bonuses:
--   attributeBonuses = { strength = 5, luck = 20 }
--   skillBonuses     = { longblade = 10 }
-- Applied only once per save.
local M = {}

M.CAP = 100                 -- attribute / skill ceiling
M.MAX_BONUS = 100

-- Character creation is finished once Sellus Gravius has given the package
-- to Caius Cosades (journal A1_1_FindSpymaster index 1): the race, class and
-- birthsign are final at that point, so the bonus cannot be overwritten.
M.TRIGGER_QUEST = 'a1_1_findspymaster'
M.TRIGGER_STAGE = 1

M.ATTRIBUTES = {
  'strength', 'intelligence', 'willpower', 'agility',
  'speed', 'endurance', 'personality', 'luck',
}

M.SKILLS = {
  'acrobatics', 'alchemy', 'alteration', 'armorer', 'athletics', 'axe',
  'block', 'bluntweapon', 'conjuration', 'destruction', 'enchant',
  'handtohand', 'heavyarmor', 'illusion', 'lightarmor', 'longblade',
  'marksman', 'mediumarmor', 'mercantile', 'mysticism', 'restoration',
  'security', 'shortblade', 'sneak', 'spear', 'speechcraft', 'unarmored',
}

local function setOf(list)
  local s = {}
  for _, id in ipairs(list) do s[id] = true end
  return s
end
local ATTRIBUTE_SET, SKILL_SET = setOf(M.ATTRIBUTES), setOf(M.SKILLS)

-- Cleans a { id = bonus } table from the server: unknown ids and bonuses <= 0
-- are dropped, the others are rounded and clamped to [1, MAX_BONUS].
-- Returns nil if `t` is not a table (old server: option absent).
local function cleanBonuses(t, valid)
  if type(t) ~= 'table' then return nil end
  local out = {}
  for id, n in pairs(t) do
    n = tonumber(n)
    if valid[id] and n then
      n = math.floor(n + 0.5)
      if n > M.MAX_BONUS then n = M.MAX_BONUS end
      if n > 0 then out[id] = n end
    end
  end
  return out
end

function M.cleanAttributes(t) return cleanBonuses(t, ATTRIBUTE_SET) end
function M.cleanSkills(t) return cleanBonuses(t, SKILL_SET) end

-- True if neither table contains a bonus.
function M.isEmpty(attributes, skills)
  return next(attributes or {}) == nil and next(skills or {}) == nil
end

-- Total of the bonuses (informational: log / message).
function M.total(attributes, skills)
  local n = 0
  for _, v in pairs(attributes or {}) do n = n + v end
  for _, v in pairs(skills or {}) do n = n + v end
  return n
end

-- New value of an attribute / skill (never lowered, even if already above the cap).
function M.boosted(base, bonus)
  base = tonumber(base) or 0
  local v = base + (tonumber(bonus) or 0)
  if v > M.CAP then v = M.CAP end
  if v < base then v = base end
  return v
end

-- Applies the bonuses to `actor` (the player, from its local script).
-- `types` is the openmw.types module. Returns true if something was applied.
function M.apply(types, actor, attributes, skills)
  if M.isEmpty(attributes, skills) then return false end

  for _, id in ipairs(M.ATTRIBUTES) do
    local bonus = (attributes or {})[id]
    if bonus then
      pcall(function()
        local stat = types.Actor.stats.attributes[id](actor)
        stat.base = M.boosted(stat.base, bonus)
      end)
    end
  end
  for _, id in ipairs(M.SKILLS) do
    local bonus = (skills or {})[id]
    if bonus then
      pcall(function()
        local stat = types.NPC.stats.skills[id](actor)
        stat.base = M.boosted(stat.base, bonus)
      end)
    end
  end
  return true
end

return M
