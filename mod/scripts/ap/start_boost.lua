-- Starting level (YAML option `starting_level`, 1 to 40).
--
-- Once the tutorial is over (character creation finished), the player gets:
--   * level N (the level stat is set directly: no level-up window),
--   * +N to each of the 8 attributes and 27 skills (capped at 100),
--   * the health vanilla level-ups would have given (0.1 x Endurance per level).
-- N = 1 changes nothing (vanilla). Applied only once per save.
local M = {}

M.MIN_LEVEL = 1
M.MAX_LEVEL = 40
M.CAP = 100                 -- attribute / skill ceiling
M.HEALTH_PER_LEVEL = 0.1    -- x Endurance, as the vanilla fLevelUpHealthEndMult GMST

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

-- Level from the server, or nil if invalid. Rounded and clamped to [1, 40].
function M.clampLevel(n)
  n = tonumber(n)
  if not n then return nil end
  n = math.floor(n + 0.5)
  if n < M.MIN_LEVEL then n = M.MIN_LEVEL end
  if n > M.MAX_LEVEL then n = M.MAX_LEVEL end
  return n
end

-- New value of an attribute / skill (never lowered, even if already above the cap).
function M.boosted(base, n)
  base = tonumber(base) or 0
  local v = base + (tonumber(n) or 0)
  if v > M.CAP then v = M.CAP end
  if v < base then v = base end
  return v
end

-- Health vanilla level-ups would have given between level 1 and level n.
function M.healthGain(n, endurance)
  n = tonumber(n) or 1
  if n <= 1 then return 0 end
  return (n - 1) * M.HEALTH_PER_LEVEL * (tonumber(endurance) or 0)
end

-- Applies the bonus to `actor` (the player, from its local script).
-- `types` is the openmw.types module. Returns true if something was applied.
function M.apply(types, actor, n)
  n = M.clampLevel(n)
  if not n or n <= 1 then return false end

  for _, id in ipairs(M.ATTRIBUTES) do
    pcall(function()
      local stat = types.Actor.stats.attributes[id](actor)
      stat.base = M.boosted(stat.base, n)
    end)
  end
  for _, id in ipairs(M.SKILLS) do
    pcall(function()
      local stat = types.NPC.stats.skills[id](actor)
      stat.base = M.boosted(stat.base, n)
    end)
  end
  pcall(function()
    local lvl = types.Actor.stats.level(actor)
    if (lvl.current or 1) < n then lvl.current = n end
  end)
  pcall(function()
    local endu = types.Actor.stats.attributes.endurance(actor).base
    local gain = M.healthGain(n, endu)
    if gain > 0 then
      local health = types.Actor.stats.dynamic.health(actor)
      health.base = (health.base or 0) + gain
      health.current = (health.current or 0) + gain
    end
  end)
  return true
end

return M
