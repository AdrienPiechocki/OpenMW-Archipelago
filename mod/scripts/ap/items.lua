-- Mapping item Archipelago -> action en jeu.
--
-- Les items de transport / progression sans objet physique sont suivis par
-- global.lua (table owned) : ils debloquent les services de voyage.
local M = {}
local levelUp = require('scripts.ap.level_up')

-- Objets donnes directement dans l'inventaire.
-- cles = id AP, valeur = { recordId, quantite }
local GIVE = {
  [7701001] = { 'gold_001', 100 },
  [7701002] = { 'p_restore_health_s', 1 },
  [7701003] = { 'misc_soulgem_common', 1 },
  [7701004] = { 'chitin arrow', 30 },
}

-- Sorts ajoutes au joueur.
local SPELLS = {}

-- Objets de quete par objectif (data/quest_items.yaml -> quest_items.lua) :
-- donnes par Archipelago, et retires de l'inventaire s'ils viennent des
-- quetes tant que l'item AP correspondant n'a pas ete recu.
local QUEST_ITEMS = require('scripts.ap.quest_items')
for _, list in pairs(QUEST_ITEMS) do
  for _, it in ipairs(list) do
    if it.give then GIVE[it.id] = it.give end
    if it.spells then SPELLS[it.id] = it.spells end
  end
end

-- Table { apId = { recordIds } } des objets a supprimer pour les objectifs
-- donnes (liste de cles, ou une cle). Sans objectif connu (config pas encore
-- recue) : rien n'est supprime.
function M.suppressFor(goals)
  if type(goals) == 'string' then goals = { goals } end
  local out = {}
  for _, goal in ipairs(goals or {}) do
    for _, it in ipairs(QUEST_ITEMS[goal] or {}) do
      if it.suppress then out[it.id] = it.suppress end
    end
  end
  return out
end

-- Objet exige par le script vanilla CharGenDoorExitCaptain pour sortir du
-- Census Office. Tant que le joueur est dans le batiment, on le garde (et on
-- le recree s'il manque), meme si l'item AP n'a pas encore ete recu.
M.CENSUS_PACKAGE = 'bk_a1_1_caiuspackage'

-- Vrai si la liste d'objets a supprimer contient le package et que le joueur
-- est encore dans le Census Office. On se base sur le record plutot que sur
-- un id AP code en dur : les ids de data/quest_items.yaml peuvent changer.
function M.keepInCensus(records, inCensus)
  if not inCensus then return false end
  for _, recordId in ipairs(records or {}) do
    if recordId == M.CENSUS_PACKAGE then return true end
  end
  return false
end

local function giveObject(player, recordId, count)
  local world = require('openmw.world')
  local types = require('openmw.types')
  local obj = world.createObject(recordId, count or 1)
  if not obj then return false end
  obj:moveInto(types.Actor.inventory(player))
  return true
end

local function giveSpells(player, ids)
  local types = require('openmw.types')
  local spells = types.Actor.spells(player)
  for _, id in ipairs(ids) do
    pcall(function() spells:add(id) end)
  end
  return true
end

-- Applique un item. Retourne true si l'item a ete traite (meme si l'effet
-- exact n'est pas connu), false sinon.
function M.apply(player, itemId, idx)
  local types = require('openmw.types')

  local g = GIVE[itemId]
  if g then
    print('AP: apply ' .. tostring(itemId) .. ' -> give ' .. tostring(g[1]) .. ' x' .. tostring(g[2]))
    local ok = giveObject(player, g[1], g[2])
    print('AP: giveObject(' .. tostring(g[1]) .. ') = ' .. tostring(ok))
    return true
  end

  local sp = SPELLS[itemId]
  if sp then
    giveSpells(player, sp)
    return true
  end

  -- (Bonus de Force supprime)

  -- Piege : maladie / embuscade
  if itemId == 7701200 then
    pcall(function()
      local inv = types.Actor.inventory(player)
      local gold = inv:find('gold_001')
      if gold then
        local n = math.min(gold.count or 0, 100)
        if n > 0 then gold:remove(n) end
      end
    end)
    pcall(function()
      local health = types.Actor.stats.dynamic.health(player)
      local cur = health.current or 0
      health.current = math.max(1, cur - 20)
    end)
    pcall(function()
      local world = require('openmw.world')
      local pos = player.position
      local c = world.createObject('cliff racer', 1)
      if c and pos then
        c:teleport(player.cell, { x = pos.x + 200, y = pos.y + 200, z = pos.z })
      end
    end)
    return true
  end

  -- Piege : mise a prix (bounty)
  if itemId == 7701201 then
    pcall(function()
      local cur = types.Player.getCrimeLevel(player)
      types.Player.setCrimeLevel(player, (cur or 0) + 1000)
    end)
    return true
  end

  -- Piege : invocation d'un scamp
  if itemId == 7701202 then
    pcall(function()
      local world = require('openmw.world')
      local pos = player.position
      local c = world.createObject('scamp', 1)
      if c and pos then
        c:teleport(player.cell, { x = pos.x + 200, y = pos.y + 200, z = pos.z })
      end
    end)
    return true
  end

  -- Piege : vol d'or
  if itemId == 7701203 then
    pcall(function()
      local types = require('openmw.types')
      local inv = types.Actor.inventory(player)
      local gold = inv:find('gold_001')
      if gold then
        local n = math.min(gold.count or 0, 250)
        if n > 0 then gold:remove(n) end
      end
    end)
    return true
  end

  -- +10 niveaux : la progression est ajoutee par player.lua, car les setters
  -- de stats ne sont autorises que sur openmw.self (pas depuis le script
  -- global). On renvoie l'effet a relayer au joueur.
  if itemId == levelUp.ITEM_ID then
    return true, { type = 'level_up', levels = levelUp.LEVELS }
  end

  -- Niveaux de competence : +5 au skill correspondant
  if itemId >= 7701300 and itemId <= 7701326 then
    local SKILLS = {
      [7701300] = 'acrobatics', [7701301] = 'alchemy', [7701302] = 'alteration',
      [7701303] = 'armorer', [7701304] = 'athletics', [7701305] = 'axe',
      [7701306] = 'block', [7701307] = 'bluntweapon', [7701308] = 'conjuration',
      [7701309] = 'destruction', [7701310] = 'enchant', [7701311] = 'handtohand',
      [7701312] = 'heavyarmor', [7701313] = 'illusion', [7701314] = 'lightarmor',
      [7701315] = 'longblade', [7701316] = 'marksman', [7701317] = 'mediumarmor',
      [7701318] = 'mercantile', [7701319] = 'mysticism', [7701320] = 'restoration',
      [7701321] = 'security', [7701322] = 'shortblade', [7701323] = 'sneak',
      [7701324] = 'spear', [7701325] = 'speechcraft', [7701326] = 'unarmored',
    }
    local skill = SKILLS[itemId]
    if skill then
      pcall(function()
        local types = require('openmw.types')
        local stat = types.NPC.stats.skills[skill](player)
        if stat then
          stat.base = (stat.base or 0) + 5
        end
      end)
    end
    return true
  end

  -- Items de transport / progression sans objet : rien a donner, la
  -- possession est suivie par global.lua.
  if itemId >= 7701100 and itemId <= 7701114 then
    return true
  end

  return false
end

return M
