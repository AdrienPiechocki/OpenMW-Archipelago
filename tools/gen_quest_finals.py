#!/usr/bin/env python3
"""Generates data/quest_finals.yaml: completion stages per quest.

Each entry contains:
  stage  : "main" stage (the highest ending stage, or the override);
           kept for compatibility.
  stages : ALL stages that successfully finish the quest. The quest is
           completed as soon as one of these stages is reached.
  fail   : failure stages (cancel the completion).

Completion stages are deduced from the ESM: a journal entry stage that
neither a dialogue (Journal filter) nor a script (GetJournalIndex) uses as a
condition has no follow-up: it is a possible ending (candidate). The
quest_finish stages are added if they exist (tes3conv does not always export
them), then known failure stages are removed. As a fallback, we take the
highest Journal stage (< 150: vanilla convention; a quest whose real ending
is above that must be listed in STAGES_OVERRIDES, as Foul Murder is).
Overrides fix known branches. Automatically added stages are listed in
quest_review.txt.

Usage:
  tes3conv Morrowind.esm morrowind.json
  python tools/gen_quest_finals.py /tmp/morrowind.json --out data/quest_finals.yaml
  # --recompute: also recomputes quests already present (stage/stages)
"""
import argparse
import collections
import json
import pathlib
import re

import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from quest_groups import classify, load_overrides  # noqa: E402

# Explicit "main" stage when the raw maximum does not match the quest's
# actual "successful" ending.
STAGE_OVERRIDES = {
    'fg_nchurdamz': 100,
    'il_maidentoken': 110,
    'mv_strayedpilgrim': 100,
    'tt_diseasecarrier': 100,
    'tt_ministryheathen': 100,
    'tt_sanctusshrine': 100,
    'c3_destroydagoth': 50,
    'a1_4_muzgobinformant': 30,
    'mv_recoverwidowmaker': 80,
    'mv_abusedhealer': 85,
    'il_rescuepilgrim': 100,
    'b3_zainabbride': 55,
    'eb_invisible': 120,
    'mv_cultistvictim': 100,
    'mv_3_charming': 90,
    # Tamriel Rebuilt: Foul Murder only succeeds at stage 200. The automatic
    # "< 150" cap would stop at 110 (a dialogue branch, not an ending).
    'tr_necmq_3': 200,
    # Troubles on the Road: alternate ending, report to Yan-Ahhe (stage 200).
    'tr_m4_bal0_troubles_a': 200,
}

# COMPLETE list of completion stages, when the automatic deduction
# (quest_finish minus failures) is wrong. Takes priority over everything else.
# Nels Llendo: 90 (refusal/attack), 100 (gold), 120 and 130 (kiss) all finish
# the quest; 140 is only a follow-up at Pelagiad, often never reached.
STAGES_OVERRIDES = {
    'mv_3_charming': [90, 100, 120, 130],
    "mv_wanderingpilgrim": [100, 110],
    # Courtesy: the quest already ends at stage 100 (110 is a later follow-up).
    "il_courtesy": [100, 110],
    "mv_richpilgrim": [100, 120, 130],
    # Tamriel Rebuilt (Foul Murder). These journals are dialogue branches:
    # only one of their stages is reached per playthrough, so every branch is
    # a valid completion. They are above the default "< 150" cap, which is
    # why they need explicit overrides.
    'tr_necmq_2': [60, 65],                       # summon or refuse
    'tr_necmq_2path': [35, 75],                   # Simine or Alvu ritual
    'tr_necmq_3': [200],                          # keep the truth (success)
    'tr_necmq_3death': [115, 120, 125, 130, 135],
    'tr_necmq_3moment': [140, 145, 150, 155],
    'tr_necmq_3tribunal': [160, 165, 170, 175, 180, 185],
    # Ringlets: give it to Simine or to Alvu.
    'tr_necmq_destroyer': [110, 115],
    'tr_necmq_madman': [55, 70],
    'tr_necmq_outcast': [35, 40],
    'tr_necmq_schemer': [60, 75],
    # Troubles on the Road: alternate ending (report to Yan-Ahhe, stage 200).
    'tr_m4_bal0_troubles_a': [200],
    # Great House strongholds: UESP flags the intermediate construction
    # milestones (100/200) as "Finishes quest", but the quest truly ends
    # only at the final stage (300).
    'hh_stronghold': [300],
    'hr_stronghold': [300],
    'ht_stronghold': [300],
}

# BEGIN UESP OVERRIDES (tools/scrape_uesp_finals.py)
# Completion stages = every UESP "Finishes quest" stage of the journal.
# Not overridden by hand. Delete a line here and move it up to keep a manual value.
STAGES_OVERRIDES.update({
    'a1_10_mehramilo': [50],
    'a1_11_zainsubaniinformant': [50],
    'a1_1_findspymaster': [14, 18, 20, 22],
    'a1_2_antabolisinformant': [20, 25],
    'a1_4_muzgobinformant': [25, 30, 55],
    'a1_6_addhiranirrinformant': [45, 60],
    'a1_7huleeyainformant': [50],
    'a1_dreams': [1, 5, 10, 15],
    'a1_sleeperdreamer02': [50],
    'a1_sleepersawake': [1, 50],
    'a1_v_vivecinformants': [50, 55],
    'a2_1_kurapli_zallay': [50],
    'a2_1_meetsulmatuul': [60],
    'a2_2_6thhouse': [50],
    'a2_3_corpruscure': [50],
    'a2_4_milo_hola_go': [1],
    'a2_4_milocaiusgone': [5],
    'a2_4_milogone': [50],
    'a2_4_milogone_books': [1],
    'a2_4_miloprisonsafe': [100],
    'a2_6_ane_teria': [100],
    'a2_6_conoon': [100],
    'a2_6_erur-dan': [100],
    'a2_6_hort-ledd': [100],
    'a2_6_idrenie': [100],
    'a2_6_incarnate': [70, 72, 74, 76, 78, 80],
    'a2_6_peakstar': [100],
    'b1_unifyurshilaku': [50],
    'b1_urshilakukill': [1],
    'b2_ahemmusasafe': [50],
    'b3_zainabbride': [50, 55],
    'b3_zainabkill': [1],
    'b4_erabenimsunkill': [1],
    'b4_heartfire': [1, 5],
    'b4_killwarlovers': [55],
    'b4_robe': [1, 5],
    'b4_waraxe': [1, 5],
    'b4_warloverkill': [1],
    'b5_redoranhort': [50, 60, 70],
    'b6_hlaaluhort': [50],
    'b7_telvannihort': [50, 60, 70],
    'b8_failed_nerevarine': [1],
    'b8_meetvivec': [50, 55],
    'c3_destroydagoth': [50],
    'cx_backpath': [50, 55, 60, 65],
    'da_azura': [30, 40],
    'da_boethiah': [70],
    'da_malacath': [70],
    'da_mehrunes': [40],
    'da_mephala': [57, 60],
    'da_molagbal': [30],
    'da_sheogorath': [70],
    'eb_actor': [35, 80, 90],
    'eb_bone': [30, 60, 70, 110],
    'eb_clients': [50],
    'eb_deadmen': [60],
    'eb_deed': [40, 50],
    'eb_express': [50],
    'eb_false': [55, 60],
    'eb_invisible': [120, 130],
    'eb_pest': [40],
    'eb_shipment': [30, 40, 50],
    'eb_tradespy': [50],
    'eb_unrequited': [30, 100, 110],
    'fg_alofsfarm': [100],
    'fg_beneranbounty': [100],
    'fg_bigbosses': [100, 110],
    'fg_corprusstalker': [100],
    'fg_debtorc': [100],
    'fg_debtstoine': [100],
    'fg_deseledebt': [100],
    'fg_dissaplamine': [100],
    'fg_duniraisupply': [100, 110],
    'fg_egg_poachers': [100],
    'fg_elithpalsupply': [100],
    'fg_engaerbounty': [100],
    'fg_findpudai': [100],
    'fg_hungerloose': [100],
    'fg_khajiitbounty': [100],
    'fg_killbosses': [100],
    'fg_killcronies': [100],
    'fg_killhardheart': [100],
    'fg_nchurdamz': [100],
    'fg_orcbounty': [100],
    'fg_rathunt': [105, 110],
    'fg_silencemagistrate': [100],
    'fg_silencetaxgirl': [100],
    'fg_sottilde': [100],
    'fg_suranbandits': [100],
    'fg_telasero': [100, 110],
    'fg_telvanni_agents': [100],
    'fg_tenimbounty': [100],
    'fg_tonguetoad': [100],
    'fg_vas': [100, 105],
    'fg_verethigang': [100],
    'hh_ashlanderebony': [100, 200],
    'hh_bankcourier': [100],
    'hh_bankfraud': [100, 110],
    'hh_berosupport': [100, 200],
    'hh_buriedtreasure': [100, 110],
    'hh_capturespy': [100, 110, 120],
    'hh_crassius': [100],
    'hh_destroyindarysmanor': [100],
    'hh_destroyteluvirith': [100],
    'hh_disguisedarmor': [100, 150, 200],
    'hh_ebonydelivery': [100, 110],
    'hh_eggmine': [100, 210],
    'hh_escortmerchant': [100],
    'hh_guardmerchant': [100],
    'hh_indesp1': [100, 200],
    'hh_indesp2': [100],
    'hh_indesp3': [100],
    'hh_indesp4': [100, 110],
    'hh_literacycampaign': [100],
    'hh_nordsmugglers': [100],
    'hh_odirniran': [100],
    'hh_rentcollector': [100, 110],
    'hh_replacedocs': [100],
    'hh_retaliation': [100, 110, 120, 150, 200],
    'hh_sunkentreasure': [100],
    'hh_theexterminator': [100],
    'hh_twinlamps1': [100],
    'hh_twinlamps3': [100],
    'hh_wincamonna': [100, 110],
    'hh_winsaryoni': [100],
    'hr_archmaster': [100],
    'hr_arobarkidnap': [100],
    'hr_ashimanumine': [100],
    'hr_attackrethan': [100],
    'hr_attackuvirith': [100],
    'hr_billcollect': [100],
    'hr_calderacorrupt': [100],
    'hr_calderadisrupt': [100],
    'hr_clearsarethi': [100, 110],
    'hr_courier': [100],
    'hr_cowarddisgrace': [100],
    'hr_cultelimination': [100],
    'hr_dagothtanis': [100],
    'hr_finddalobar': [100],
    'hr_findgiladren': [100],
    'hr_findtharen': [100, 110],
    'hr_foundershelm': [100, 200],
    'hr_guardguarherds': [100, 110],
    'hr_guardsarethi': [100],
    'hr_hlaanoslanders': [100],
    'hr_honorchallenge': [100, 200],
    'hr_kagouti': [100],
    'hr_koalcave': [100],
    'hr_lostbanner': [100],
    'hr_madmilk': [100, 110],
    'hr_morvaynmanor': [100],
    'hr_mudcrabnest': [100],
    'hr_oldbluefin': [100],
    'hr_oldflame': [100, 101, 110],
    'hr_ransommandas': [100],
    'hr_redastomb': [100, 110],
    'hr_rescuesarethi': [100],
    'hr_shishireport': [100, 110],
    'hr_shurinbaal': [100],
    'hr_sixthhousebase': [100],
    'hr_taxcollector': [100],
    'ht_archmagister': [100],
    'ht_attackindarys': [100],
    'ht_attackrethan': [100],
    'ht_aurielbow': [100],
    'ht_baladasally': [100],
    'ht_blackjinx': [100],
    'ht_chroniclesnchuleft': [100],
    'ht_cureblight': [100],
    'ht_daedraskin': [100],
    'ht_dahrkmezalf': [100],
    'ht_drakepride': [100],
    'ht_dwemerlaw': [100],
    'ht_eddieamulet': [100],
    'ht_eddiering': [100],
    'ht_fireandfaith': [100],
    'ht_fleshamulet': [100],
    'ht_fyrmessage': [100],
    'ht_minecure': [100],
    'ht_monopoly': [100],
    'ht_muck': [100],
    'ht_nchuleftkey': [100],
    'ht_odirniran': [100],
    'ht_recruiteddie': [100],
    'ht_shishi': [100],
    'ht_silverdawn': [100],
    'ht_slaverebellion': [100, 110],
    'ht_sloadsoap': [100],
    'ht_spybaladas': [100],
    'ht_theranaclothes': [100],
    'ht_wizardspells': [100],
    'ic10_buckmoth_alms': [5, 50, 60],
    'ic10_buckmoth_not': [1],
    'ic11_shirt': [50],
    'ic11_shirt_not': [1],
    'ic12_dinner': [5, 50],
    'ic12_dinner_not': [5],
    'ic13_rich': [45, 50],
    'ic13_rich_not': [1],
    'ic14_ponius': [50],
    'ic15_missing_limeware': [50],
    'ic15_missing_not': [1],
    'ic16_haunting': [50],
    'ic16_haunting_not': [1],
    'ic17_witch': [50],
    'ic17_witch_not': [1],
    'ic18_silver_not': [1],
    'ic18_silver_staff': [50, 55],
    'ic19_restless_not': [1],
    'ic19_restless_spirit': [50],
    'ic1_marshmerrow': [5, 50],
    'ic1_marshmerrow_not': [1],
    'ic25_jonhawker': [50],
    'ic26_amanin': [50, 60],
    'ic27_oracle': [50, 55],
    'ic28_urjorad': [50, 55],
    'ic29_crusher': [50],
    'ic2_muck': [5, 50],
    'ic2_muck_not': [1],
    'ic30_imperial_veteran': [10],
    'ic3_willow': [5, 50],
    'ic3_willow_not': [1],
    'ic4_scrib': [5, 50],
    'ic4_scrib_a': [1],
    'ic4_scrib_not': [1],
    'ic5_corkbulb': [5, 50],
    'ic5_corkbulb_not': [1],
    'ic6_rat': [5, 50],
    'ic6_rat_not': [1],
    'ic7_netch': [5, 50],
    'ic7_netch_not': [1],
    'ic9_argonian_alms': [30, 50, 60],
    'ic9_argonian_not': [1],
    'il_blueprints': [100],
    'il_damsel': [100],
    'il_falseordinator': [100],
    'il_giantnetch': [100],
    'il_gnisisblight': [100],
    'il_grandmaster': [100],
    'il_knightshield': [100],
    'il_maidentoken': [100, 110],
    'il_necromancer': [100],
    'il_protectentius': [100, 110],
    'il_rescuehermit': [100],
    'il_rescueknight': [100, 200],
    'il_rescuepilgrim': [100],
    'il_rescueragash': [100],
    'il_scrapmetal': [100],
    'il_smuggler': [100],
    'il_talostreason': [100],
    'il_traitorwarrior': [100],
    'il_widowland': [100, 120],
    'mg_apprentice': [100, 200],
    'mg_bcshrooms': [100],
    'mg_bethamez': [100],
    'mg_bowl': [100],
    'mg_dwarves': [100],
    'mg_escortscholar1': [100],
    'mg_escortscholar2': [100],
    'mg_excavation': [100, 110],
    'mg_flowers': [100],
    'mg_guildmaster': [100],
    'mg_joinus': [100],
    'mg_killnecro1': [100],
    'mg_killnecro2': [100],
    'mg_killtelvanni': [100],
    'mg_mzuleft': [100],
    'mg_nchuleftbook': [100],
    'mg_paydues': [100],
    'mg_potion': [100],
    'mg_returnbook': [100],
    'mg_sabotage': [100],
    'mg_science': [100],
    'mg_sharn_necro': [10],
    'mg_soulgem2': [100],
    'mg_spycatch': [100, 110],
    'mg_staffmagnus': [100],
    'mg_stealbook': [100],
    'mg_stolenreport': [100],
    'mg_stopcompetition': [100, 110],
    'mg_vampirecure': [100],
    'mg_vampvol2': [100],
    'mg_warlocksring': [100],
    'mg_wisewoman': [100],
    'ms_apologies': [100],
    'ms_arenimtomb': [100, 110],
    'ms_fargothring': [100],
    'ms_gold_kanet_flower': [100],
    'ms_hannat': [70, 110],
    'ms_hatandskirt': [50, 55, 60, 65],
    'ms_hentuspants': [100],
    'ms_jobashaabolitionist': [100],
    'ms_lookout': [100],
    'ms_nuccius': [100],
    'ms_piernette': [100],
    'ms_trerayna_bounty': [50],
    'ms_umbra': [50, 60],
    'ms_vampirecure': [50],
    'ms_whiteguar': [80],
    'mt_db_aldsotha': [100],
    'mt_db_assernerairan': [100],
    'mt_db_carecalmo': [100],
    'mt_db_contact': [100],
    'mt_db_darys': [100, 110],
    'mt_grandmaster': [100, 110],
    'mt_writbaladas': [100, 110],
    'mt_writbelvayn': [100, 110],
    'mt_writbemis': [100, 110],
    'mt_writbero': [100, 110],
    'mt_writbrilnosu': [100, 110],
    'mt_writgalasa': [100, 110],
    'mt_writguril': [100, 110],
    'mt_writmavon': [100, 110],
    'mt_writnavil': [100, 110],
    'mt_writoran': [100, 110],
    'mt_writsadus': [100, 110],
    'mt_writsaren': [100, 110],
    'mt_writtherana': [100, 110],
    'mt_writvarro': [100, 110],
    'mt_writvendu': [100, 110],
    'mt_writyasalmibaal': [100, 110],
    'mv_abusedhealer': [35, 85],
    'mv_angrytrader': [25, 100, 105, 110],
    'mv_banditvictim': [40, 100, 105, 110, 120],
    'mv_bastard': [110],
    'mv_bountyhunter': [120, 130, 140],
    'mv_bugrol': [25, 100],
    'mv_cultistvictim': [100],
    'mv_deadtaxman': [100],
    'mv_fakeslave': [50, 100, 110],
    'mv_innocentashlanders': [40, 110, 115],
    'mv_lostring': [40],
    'mv_missingcompanion': [60, 70],
    'mv_monsterdisease': [60, 70],
    'mv_outcastashlanders': [110],
    'mv_paralyzedbarbarian': [50, 100],
    'mv_poorpilgrim': [23, 100, 120],
    'mv_recoverwidowmaker': [40, 70, 80],
    'mv_richtrader': [100, 105],
    'mv_runawayslave': [36, 100, 105, 120, 130, 140],
    'mv_skoomacorpse': [20, 30],
    'mv_slavemule': [108, 109, 110, 113, 115],
    'mv_strayedpilgrim': [21, 26, 29, 100],
    'mv_thieftrader': [100, 105],
    'mv_traderabandoned': [30, 100, 110],
    'mv_traderlate': [100],
    'mv_tradermissed': [100, 110, 130],
    'mv_victimromance': [110, 115],
    'pc_m0_fw_letkha': [100, 110, 120, 130],
    'romance_ahnassi': [95],
    'tg_aldruhndefenses': [100],
    'tg_badgandosa': [100],
    'tg_balmoradefenses': [100, 110],
    'tg_bitterbribe': [100, 110, 120],
    'tg_brotherbragor': [100],
    'tg_brotherthief': [100, 110],
    'tg_cookbookalchemy': [100, 110],
    'tg_dartsjudgement': [100, 105],
    'tg_diamonds': [100],
    'tg_ebonystaff': [100, 105, 110],
    'tg_enemyparley': [100, 110],
    'tg_grandmasterretort': [100],
    'tg_hostage': [100, 110],
    'tg_killhardheart': [100],
    'tg_killienith': [100],
    'tg_lootaldruhnmg': [100],
    'tg_manorkey': [100],
    'tg_masterhelm': [100],
    'tg_overduepayments': [100],
    'tg_redorancookbook': [100],
    'tg_sadrithmoradefenses': [100, 110],
    'tg_ss_churchpolice': [100],
    'tg_ss_enamor': [100],
    'tg_ss_generosity1': [100],
    'tg_ss_generosity2': [100],
    'tg_ss_greedyslaver': [100],
    'tg_ss_plutocrats': [100],
    'tg_ss_yngling': [100, 110],
    'tg_vintagebrandy': [100],
    'tg_withershins': [100],
    'town_ald_bevene': [3, 5, 10],
    'town_ald_bivale': [3, 5, 10],
    'town_ald_daynes': [3, 5, 10],
    'town_ald_llethri': [3, 5, 10],
    'town_ald_tiras': [3, 5, 10],
    'town_balmora': [30, 35],
    'town_sadrith': [50, 55, 60, 65, 70, 75, 80, 85, 90, 100, 105, 110],
    'town_tel_vos': [35],
    'town_vivec': [50, 55],
    'tr_m0_gilsdrelas': [100],
    'tr_m0_hh_atranoran': [100, 110, 120],
    'tr_m0_hh_tholerandas': [100],
    'tr_m0_ht_cephalopodshells': [100],
    'tr_m0_ic_dustbeetleshell': [50],
    'tr_m0_ic_dustbeetleshell_not': [1],
    'tr_m0_il_honthjolf': [100],
    'tr_m0_mg_ajira': [100],
    'tr_m0_mg_tenyeminwe': [100],
    'tr_m0_siegeatfiremoth': [100, 110, 120],
    'tr_m0_tg_secretmasterpick': [100],
    'tr_m0_tonguetoad': [100],
    'tr_m0_tt_anoforondas': [100],
    'tr_m0_yakinbael': [100],
    'tr_m1_as_dwemer': [50, 60, 65],
    'tr_m1_as_guard': [15, 60, 70, 80],
    'tr_m1_bah_guarmeat': [100, 110],
    'tr_m1_bah_widow': [2, 50, 60],
    'tr_m1_bomuskfly_ito': [100],
    'tr_m1_da_clavicus': [25, 100, 110],
    'tr_m1_da_sanguine': [25, 55, 100, 150, 200],
    'tr_m1_eec_lora': [30],
    'tr_m1_eec_lora2': [30, 35, 40],
    'tr_m1_eec_lora3': [100, 120, 170, 180],
    'tr_m1_eec_zaren': [60, 65, 67, 68, 70],
    'tr_m1_fg_burglary': [100, 101, 105],
    'tr_m1_fg_burglaryextra': [10, 20],
    'tr_m1_fg_codaliastalker': [100, 105, 110],
    'tr_m1_fg_codaliastalkeralt': [105],
    'tr_m1_fg_egg': [100, 110, 120],
    'tr_m1_fg_findorc': [100, 105, 110],
    'tr_m1_fg_mandaran': [100],
    'tr_m1_fg_manrizache': [90, 100],
    'tr_m1_fg_past': [100],
    'tr_m1_fg_past2': [10, 20],
    'tr_m1_fg_protection': [90, 100],
    'tr_m1_fw_abittertaste': [20],
    'tr_m1_fw_atighterfit': [30],
    'tr_m1_fw_clannfear': [100],
    'tr_m1_fw_collegeenrollalchemy': [100],
    'tr_m1_fw_collegeenrollarchaeology': [100],
    'tr_m1_fw_collegeenrollgeography': [100],
    'tr_m1_fw_collegeenrollhistory': [100],
    'tr_m1_fw_collegeenrollmagecraft': [100],
    'tr_m1_fw_collegeenrollphilosophy': [100],
    'tr_m1_fw_collegeenrollrhetoric': [100],
    'tr_m1_fw_collegegreatriver': [95, 100, 105, 110, 120],
    'tr_m1_fw_collegerealthing': [100, 110, 120, 130],
    'tr_m1_fw_doublemean': [50],
    'tr_m1_fw_gummidge': [100, 150],
    'tr_m1_fw_ic1_guar': [100, 200, 201],
    'tr_m1_fw_ic2_taxes': [100, 200, 201, 202],
    'tr_m1_fw_ic3_ring': [100],
    'tr_m1_fw_ic5_sword': [100, 200],
    'tr_m1_fw_ic6_lore': [100],
    'tr_m1_fw_ic6_lore2': [5],
    'tr_m1_fw_ic6_lore3': [5],
    'tr_m1_fw_ic7_blood': [100],
    'tr_m1_fw_iftheglovefits': [100, 101],
    'tr_m1_fw_mg01': [100],
    'tr_m1_fw_mg02': [100],
    'tr_m1_fw_mg03': [100],
    'tr_m1_fw_mg04': [100],
    'tr_m1_fw_mg05': [100],
    'tr_m1_fw_mg06': [100],
    'tr_m1_fw_mg07': [100],
    'tr_m1_fw_mg07a': [100, 200, 300, 350],
    'tr_m1_fw_mg08': [100, 150],
    'tr_m1_fw_mg09': [100],
    'tr_m1_fw_minerproblems': [110],
    'tr_m1_fw_outoforder': [25, 45, 95, 100, 105, 110, 115],
    'tr_m1_fw_sugarandspice': [100, 200],
    'tr_m1_fw_tg1_brandy': [100],
    'tr_m1_fw_tg2_candle': [80, 90, 100, 110, 115],
    'tr_m1_fw_tg3_dagger': [100],
    'tr_m1_fw_tg4_letter': [100],
    'tr_m1_fw_tg5_helm': [100],
    'tr_m1_fw_tg6_stone': [200, 205, 210],
    'tr_m1_fw_va_bloodsample': [100, 110, 120],
    'tr_m1_go_1': [100, 101, 102, 300, 310],
    'tr_m1_go_2_ito': [100, 101],
    'tr_m1_go_4': [100, 101, 102, 110],
    'tr_m1_go_5': [100, 101, 102, 103, 104, 200],
    'tr_m1_go_6': [100, 110, 120, 200],
    'tr_m1_gs_mq_1': [10, 20, 30, 40, 50],
    'tr_m1_gs_mq_2': [75, 85, 95, 100],
    'tr_m1_gs_mq_3': [20, 25, 30],
    'tr_m1_gs_mq_4': [50, 60],
    'tr_m1_gs_mq_5': [80, 85, 90, 95, 100, 105, 120, 130],
    'tr_m1_ht_dr1': [20],
    'tr_m1_ht_dr2': [41, 46, 50, 55],
    'tr_m1_ht_el1': [100, 110],
    'tr_m1_ht_el2': [100],
    'tr_m1_ht_fa1': [100],
    'tr_m1_ht_fa2': [100, 101, 200],
    'tr_m1_ht_mi1': [60],
    'tr_m1_ht_mi2': [50],
    'tr_m1_ht_nu1': [100, 110],
    'tr_m1_ht_oathrung': [50, 51],
    'tr_m1_ht_ra1': [100],
    'tr_m1_ht_ra2': [100],
    'tr_m1_ht_rathra_q1': [100, 200],
    'tr_m1_ht_rathra_q2': [100],
    'tr_m1_ht_rathra_q3': [100],
    'tr_m1_ht_rathra_q4': [100],
    'tr_m1_ht_rathra_q5': [100],
    'tr_m1_ht_rathra_q6': [100],
    'tr_m1_ht_unseatingdral': [100],
    'tr_m1_ht_va1': [101],
    'tr_m1_ht_va2': [100],
    'tr_m1_il_fauna2': [100, 110],
    'tr_m1_il_finepoor': [100, 110],
    'tr_m1_il_knightduel': [70, 100, 110, 120],
    'tr_m1_il_nivalis': [15],
    'tr_m1_il_onimushili': [100],
    'tr_m1_il_pahunsabi': [100, 105, 110, 120],
    'tr_m1_il_skoomaship': [100, 110, 120],
    'tr_m1_il_sweetdeal': [100, 110, 120],
    'tr_m1_il_templar': [100],
    'tr_m1_mt_hlaaluamulet': [100, 110],
    'tr_m1_niv_crack': [100, 200],
    'tr_m1_niv_justasip': [35],
    'tr_m1_pt_adh': [900, 901, 902, 1000],
    'tr_m1_pt_dreughgreaves': [40],
    'tr_m1_pt_mai_1': [100, 110],
    'tr_m1_pt_mai_2': [100],
    'tr_m1_pt_mai_3': [100, 200, 201, 202, 450, 500],
    'tr_m1_pt_mai_4': [109, 119, 129, 400, 401, 402, 403, 404, 500],
    'tr_m1_pt_muse': [60],
    'tr_m1_pt_noisesoff': [40],
    'tr_m1_pt_ogrim': [100, 101, 105, 110, 200, 210],
    'tr_m1_pt_packrats': [100, 110, 120, 200, 201, 310],
    'tr_m1_pt_slavetrade': [40, 50],
    'tr_m1_pt_translation': [100],
    'tr_m1_rr_drunkard': [70, 100],
    'tr_m1_rr_mq_1': [10, 20, 34, 35, 40],
    'tr_m1_rr_mq_10': [1000],
    'tr_m1_rr_mq_2': [70],
    'tr_m1_rr_mq_3': [50],
    'tr_m1_rr_mq_4': [50],
    'tr_m1_rr_mq_5': [60],
    'tr_m1_rr_mq_6': [50],
    'tr_m1_rr_mq_7': [70],
    'tr_m1_rr_mq_8': [90],
    'tr_m1_rr_mq_9': [30],
    'tr_m1_rr_romance': [40],
    'tr_m1_rr_slander': [90, 100, 110, 120],
    'tr_m1_sp_qforaadri': [100, 110],
    'tr_m1_sp_sickstrider': [100, 105, 110],
    'tr_m1_to_acoldharbourkeelhaul': [85, 100, 110, 120],
    'tr_m1_to_killorbekilled': [70, 80, 90, 100],
    'tr_m1_to_ninarissecret': [100, 110],
    'tr_m1_to_runningintotrouble': [100, 200, 300],
    'tr_m1_tt_1a': [10],
    'tr_m1_tt_1b': [10],
    'tr_m1_tt_1c': [10],
    'tr_m1_tt_3': [50],
    'tr_m1_tt_4': [50],
    'tr_m1_tt_4point5': [100],
    'tr_m1_tt_5': [30],
    'tr_m1_tt_6': [30, 40],
    'tr_m1_tt_7': [100],
    'tr_m1_wil_coward': [4, 13, 25, 30, 85, 90, 100],
    'tr_m1_wil_drink': [40],
    'tr_m1_wil_drink_b': [10, 20, 30],
    'tr_m1_wil_escorttoto': [30, 31, 32],
    'tr_m1_wil_mudlapmosslog': [60, 90, 100, 110, 120, 130, 140, 150],
    'tr_m1_wil_smuggleseeker': [10, 30, 31, 32, 33],
    'tr_m1_wil_woebringer': [100, 110],
    'tr_m2_a8_5_freeatlast': [20, 25, 35, 45, 55, 65, 75, 90, 95, 105, 110, 111, 115, 123, 124, 125, 126],
    'tr_m2_a8_5_freeatlast2': [130, 131],
    'tr_m2_ab_choosefamily': [5, 40, 50],
    'tr_m2_ab_htreports': [30],
    'tr_m2_ak_cantkill': [100, 105, 110, 120, 125, 145, 150],
    'tr_m2_ak_daedra': [50],
    'tr_m2_ak_daedrab': [20],
    'tr_m2_ak_flaw': [60, 100, 110, 120],
    'tr_m2_ak_gem': [100, 101],
    'tr_m2_ak_nameless': [120, 140, 150],
    'tr_m2_ao_flingalore': [90, 100],
    'tr_m2_ao_shackledlove': [40, 60],
    'tr_m2_ba_smiler': [70, 80, 90],
    'tr_m2_fg_amiro1': [100, 170],
    'tr_m2_fg_amiro2': [100, 110],
    'tr_m2_fg_amiro3': [100, 120, 140, 160, 221, 250],
    'tr_m2_fg_hartise_eggmine': [100],
    'tr_m2_fg_hartise_joran': [100],
    'tr_m2_fg_hartise_rethyn': [100, 110],
    'tr_m2_fg_hartise_selyn': [100],
    'tr_m2_fg_hartise_selyn2': [10, 20, 30, 50],
    'tr_m2_fg_hartise_selyn3': [10],
    'tr_m2_fg_hartise_selyn4': [10],
    'tr_m2_fg_hartise_tainted': [100],
    'tr_m2_fg_hartise_twilight': [100],
    'tr_m2_fg_irano1': [100, 110, 120],
    'tr_m2_fg_irano2': [100],
    'tr_m2_fg_irano3': [100],
    'tr_m2_fg_irano4': [90, 93, 95, 100],
    'tr_m2_fg_leonos1': [60],
    'tr_m2_fg_leonos2': [40],
    'tr_m2_fw_skoomafree': [50],
    'tr_m2_hb_fraud': [80],
    'tr_m2_he_m_seekingfriend': [100, 150, 300, 400],
    'tr_m2_he_tg1': [100, 110],
    'tr_m2_he_tg2': [100, 110],
    'tr_m2_he_tg3': [100],
    'tr_m2_he_tg4': [100],
    'tr_m2_ht_vaerin_q1': [100],
    'tr_m2_ht_vaerin_q2': [100],
    'tr_m2_ht_vaerin_q3': [100],
    'tr_m2_ht_vaerin_q4': [100],
    'tr_m2_ht_vaerin_q5': [100],
    'tr_m2_ht_vaerin_q6': [100, 125, 150, 200],
    'tr_m2_ias_belongmuseum': [100, 110, 200],
    'tr_m2_ic_convert': [40, 50, 60],
    'tr_m2_ic_haunting': [80, 100, 110],
    'tr_m2_ic_pilgrim': [40, 50],
    'tr_m2_ic_widower': [40],
    'tr_m2_il_racerswarm': [30],
    'tr_m2_il_raidersotori': [30],
    'tr_m2_il_wantedwizard': [60, 70],
    'tr_m2_ito_literary_critic': [40, 50, 100, 200],
    'tr_m2_mg_areanne1': [100],
    'tr_m2_mg_areanne2': [90, 100, 110, 120],
    'tr_m2_mg_francine1': [100],
    'tr_m2_mg_francine2': [100],
    'tr_m2_mg_francine3': [50, 60, 90, 100],
    'tr_m2_mg_polodie1': [140],
    'tr_m2_mg_polodie2': [100, 120, 140, 160],
    'tr_m2_mg_ranosa1': [100],
    'tr_m2_mg_ranosa2': [100, 101, 102, 120, 121, 122],
    'tr_m2_nm_brokenfamily': [100, 105, 110, 120, 130, 140, 150, 160, 161, 162, 170, 180, 190],
    'tr_m2_nm_drunk': [60],
    'tr_m2_nm_house': [15, 20, 25],
    'tr_m2_nm_scout': [30, 40],
    'tr_m2_nm_vorith': [20],
    'tr_m2_nm_wake': [23, 51, 61, 62, 71, 82, 84, 86, 89, 100, 101],
    'tr_m2_nm_walker': [30, 60],
    'tr_m2_telon_folkmedicine': [100, 110],
    'tr_m2_telon_lovewar': [150, 200, 210],
    'tr_m2_tgi_complicatcomp': [65, 70, 75],
    'tr_m2_tm_brothers': [40, 50, 60, 70, 100, 200],
    'tr_m2_tm_sadsong_a': [150, 350, 400],
    'tr_m2_tm_sadsong_b': [100, 175],
    'tr_m2_tm_vendetta': [100, 150, 175, 180, 190, 250, 300],
    'tr_m2_tmo_gonetoground': [25, 50, 55, 56, 57, 58, 60],
    'tr_m2_tmo_qualitytime': [15, 35, 40],
    'tr_m2_tmo_trialsofage': [25],
    'tr_m2_tt_1a': [10],
    'tr_m2_tt_1b': [10],
    'tr_m2_tt_1c': [10],
    'tr_m2_vp_jealousshopkeeper': [47, 50],
    'tr_m2_wil_avengeknights': [90, 100, 110, 130, 140],
    'tr_m2_wil_faith': [10, 20, 50, 51],
    'tr_m2_wil_farm': [50, 60, 65, 125, 126],
    'tr_m2_wil_hlersis': [100],
    'tr_m2_wil_legacy': [11, 20, 30, 40, 50],
    'tr_m2_wil_pestilent': [40, 50, 51, 52],
    'tr_m2_wil_pestilent_b': [60],
    'tr_m2_wil_ruinofstrife': [50, 55, 60, 65, 80, 85],
    'tr_m2_wil_therift': [5, 40, 65, 130],
    'tr_m2_wil_tongue': [60, 75],
    'tr_m2_wil_whichwitch': [10, 50, 60, 70, 80, 90],
    'tr_m3_aim_dreugh1': [100],
    'tr_m3_aim_dreugh2': [200],
    'tr_m3_aim_horrav': [100, 101, 102, 103],
    'tr_m3_aim_intermediation': [100, 101, 102],
    'tr_m3_aim_rats': [100],
    'tr_m3_amm_scapegoat': [100],
    'tr_m3_at_armiger': [100, 150, 200],
    'tr_m3_at_brother': [50, 70, 80, 81, 82, 101, 102, 105, 210, 250, 251, 252, 253],
    'tr_m3_at_catcatchers': [110, 120, 130, 200],
    'tr_m3_at_deed': [100, 110, 120, 130, 150, 200, 300, 400],
    'tr_m3_at_deed_d': [200],
    'tr_m3_at_hisdeath': [41, 45, 60, 61, 100],
    'tr_m3_at_literacy': [100, 200],
    'tr_m3_at_matter_record': [100, 110, 200],
    'tr_m3_at_mg01': [100],
    'tr_m3_at_mg02': [100, 110],
    'tr_m3_at_mg03': [100, 110, 120],
    'tr_m3_at_mg04': [100],
    'tr_m3_at_mg05': [100],
    'tr_m3_at_mg06': [100, 110],
    'tr_m3_at_mg07': [100, 110],
    'tr_m3_at_mgbonus': [100],
    'tr_m3_at_nuccius_lanette': [20],
    'tr_m3_at_ratfriend': [110],
    'tr_m3_at_silentnight': [110, 120, 130, 200],
    'tr_m3_at_top secret recipes': [100, 110, 200, 210],
    'tr_m3_at_waters': [90],
    'tr_m3_b_aesithal tyavylch': [100],
    'tr_m3_b_llanehra androthi': [100],
    'tr_m3_bala_wlcr': [100, 210, 220, 230, 240],
    'tr_m3_bo_burglar1': [100],
    'tr_m3_bo_burglar2': [25, 26, 27, 96, 98, 99, 100, 101, 110, 111, 112, 113, 122, 130, 131],
    'tr_m3_bo_dragonhunter': [90, 100, 110, 150],
    'tr_m3_bo_kiseen': [50, 60, 70],
    'tr_m3_dar_debtssettled': [100, 110, 120, 200, 205],
    'tr_m3_dar_farragian': [50, 55, 70, 100],
    'tr_m3_dar_reprus': [100],
    'tr_m3_dar_simplecartography': [40, 41, 50],
    'tr_m3_dar_sulphur': [100],
    'tr_m3_do_cultists': [100, 101, 102],
    'tr_m3_do_delivery': [50, 51, 53, 100, 200],
    'tr_m3_do_velk': [110],
    'tr_m3_dr_bandits': [40],
    'tr_m3_dr_daughter': [1, 15, 80, 95, 100],
    'tr_m3_eec_cano1': [200],
    'tr_m3_eec_cano2': [200],
    'tr_m3_eec_cano3': [200, 210],
    'tr_m3_eec_cano4': [200],
    'tr_m3_eec_cano5': [200],
    'tr_m3_eec_cano5z': [200],
    'tr_m3_eec_cano6': [200, 205, 210],
    'tr_m3_eec_counterfeit': [30, 40, 45],
    'tr_m3_eec_curse': [30, 40, 50, 51, 52, 55],
    'tr_m3_eec_ebony': [70, 71, 72, 82],
    'tr_m3_eec_excise': [75, 77, 80, 90, 95, 96, 100],
    'tr_m3_eec_spoon': [45, 60, 65],
    'tr_m3_er_prayer': [16, 57, 70, 75],
    'tr_m3_fg_at_1': [100],
    'tr_m3_fg_at_2': [100],
    'tr_m3_fg_at_3': [100],
    'tr_m3_fg_at_4': [100],
    'tr_m3_fg_at_5': [100],
    'tr_m3_fg_at_6': [100],
    'tr_m3_fg_oe2': [100],
    'tr_m3_fg_oe4': [100],
    'tr_m3_fg_oe5': [100],
    'tr_m3_fg_oe8': [100],
    'tr_m3_fg_oe_cursing': [100, 101],
    'tr_m3_fg_oe_cursing2': [100, 101, 102],
    'tr_m3_fg_oe_fate': [100],
    'tr_m3_fg_oe_ghosts': [100],
    'tr_m3_fg_oe_legacy': [100],
    'tr_m3_go_fish': [1, 2, 3, 15, 25, 40, 45, 50, 52, 55],
    'tr_m3_go_guard1': [65, 70, 80],
    'tr_m3_go_guard2': [40, 60, 61, 62, 63, 80, 90, 100],
    'tr_m3_go_poisonsong': [100, 110, 200],
    'tr_m3_go_wind': [100],
    'tr_m3_hi_beroth1': [100, 150],
    'tr_m3_hi_gorne1': [100],
    'tr_m3_hi_gorne2': [100],
    'tr_m3_hi_gorne3': [100, 110],
    'tr_m3_hi_gorne4': [100, 110],
    'tr_m3_hi_gorne5': [100, 110],
    'tr_m3_hi_gorne6': [100],
    'tr_m3_hi_gorne7': [100],
    'tr_m3_hi_gorne8': [100, 110, 120],
    'tr_m3_hi_ilvi1': [100, 110],
    'tr_m3_hi_mq1_1': [100],
    'tr_m3_hi_mq1_2': [100],
    'tr_m3_hi_mq1_3': [100],
    'tr_m3_hi_nanaav1': [100],
    'tr_m3_hi_nanaav2': [100],
    'tr_m3_hi_nanaav3': [100],
    'tr_m3_hi_nanaav4': [100],
    'tr_m3_hi_nanaav5': [100],
    'tr_m3_hi_nanaav6': [100, 110],
    'tr_m3_hi_nanaav7': [100, 110],
    'tr_m3_hi_roadyr1': [100],
    'tr_m3_hi_roadyr2': [100],
    'tr_m3_hi_roadyr3': [100],
    'tr_m3_hi_roadyr4': [100],
    'tr_m3_hi_roadyr5': [200, 300, 500],
    'tr_m3_hi_roadyr6': [100, 200],
    'tr_m3_hi_roadyr7': [100],
    'tr_m3_hi_roadyr8': [100],
    'tr_m3_hi_sandil1': [100, 200],
    'tr_m3_ic_oe_fundingdwemer': [100],
    'tr_m3_ic_oe_fundingguar': [100],
    'tr_m3_ic_oe_fundingrobes': [100],
    'tr_m3_ic_oe_mystspread': [100],
    'tr_m3_ic_oe_theftbrass': [100],
    'tr_m3_il_firemothrebuilt': [150, 160, 170],
    'tr_m3_il_judge': [100],
    'tr_m3_il_jury': [100],
    'tr_m3_il_justice': [100, 150, 200],
    'tr_m3_il_maur4': [100, 101],
    'tr_m3_il_purloined': [100],
    'tr_m3_il_sabotage': [100],
    'tr_m3_il_siegeatfiremoth': [100],
    'tr_m3_il_sirsa': [100, 200],
    'tr_m3_il_testimony': [100],
    'tr_m3_il_work': [100, 150],
    'tr_m3_kha_anguishcrux': [100],
    'tr_m3_kha_flowersdark': [100, 101, 102],
    'tr_m3_kha_forsaken_betrayer': [100, 101, 102],
    'tr_m3_kha_undyingrivalry': [100],
    'tr_m3_kz_ias': [100, 110],
    'tr_m3_mar_amulet': [100, 101],
    'tr_m3_mar_forcesofnature': [100, 101],
    'tr_m3_mar_mahmist': [100],
    'tr_m3_me_lost': [100, 110, 120, 130, 140],
    'tr_m3_mg_oe_q1': [100],
    'tr_m3_mg_oe_q2': [100],
    'tr_m3_mg_oe_q3': [100],
    'tr_m3_mg_oe_q4': [100],
    'tr_m3_mg_oe_q5': [100],
    'tr_m3_mg_oe_q6': [120, 150, 160],
    'tr_m3_mg_oe_q7': [100],
    'tr_m3_mg_oe_q8': [140, 150, 160],
    'tr_m3_mg_oe_q9': [100],
    'tr_m3_mt_arin': [100, 110],
    'tr_m3_mt_delynasilvas': [100, 110],
    'tr_m3_mt_dileru': [100, 110],
    'tr_m3_mt_ervysa': [100, 110],
    'tr_m3_mt_felrar': [100, 110],
    'tr_m3_mt_forvayn': [100, 110],
    'tr_m3_mt_indriri': [100, 110],
    'tr_m3_mt_sp_dils': [100, 110, 111, 112, 200],
    'tr_m3_mt_ughash': [100, 110],
    'tr_m3_mt_ulyn': [100, 110],
    'tr_m3_mt_varru': [100, 110],
    'tr_m3_nnv_cheat': [30, 100, 110],
    'tr_m3_nnv_slaverising': [100, 110, 120],
    'tr_m3_oe_abductedambassador': [100, 110, 120, 130],
    'tr_m3_oe_ambassadortrouble': [150, 160],
    'tr_m3_oe_archer': [20],
    'tr_m3_oe_breadcrumbtrail': [50, 60],
    'tr_m3_oe_courtwizard': [100, 110, 120, 130, 210, 220, 300, 310],
    'tr_m3_oe_criminallawyer': [100, 110, 120],
    'tr_m3_oe_deadlytreasure': [50],
    'tr_m3_oe_dukeaffair': [100, 200, 210, 300],
    'tr_m3_oe_freedom': [90, 100, 110, 115, 120],
    'tr_m3_oe_ghoulbusiness': [100, 101, 102, 103, 104, 105],
    'tr_m3_oe_hlarsisvalju-deekus': [100, 200, 300],
    'tr_m3_oe_ic_q6': [100],
    'tr_m3_oe_ic_q7': [100, 200],
    'tr_m3_oe_ic_q8': [100],
    'tr_m3_oe_ic_q9': [100],
    'tr_m3_oe_inspiration': [100, 150, 160, 200],
    'tr_m3_oe_kassad': [100],
    'tr_m3_oe_ohwhatcustoms': [100, 200, 250, 300],
    'tr_m3_oe_resigned': [50],
    'tr_m3_oe_smallcomplaint': [10, 15, 30],
    'tr_m3_oe_stendarrtowerhaunting': [110, 120, 125],
    'tr_m3_oe_stickysituation': [100],
    'tr_m3_oe_tamrielrebuilt': [30],
    'tr_m3_oe_wherehorsegone': [7, 10, 13, 14, 100, 200],
    'tr_m3_ord_doc1': [100, 101, 102],
    'tr_m3_ord_doc2': [100, 101, 102],
    'tr_m3_ord_doc3': [100, 101],
    'tr_m3_ord_doc4': [100, 101, 102, 103],
    'tr_m3_ord_doc5': [101],
    'tr_m3_ord_war1': [100],
    'tr_m3_ord_war2': [100],
    'tr_m3_ord_war3': [100],
    'tr_m3_ord_war4': [100],
    'tr_m3_ord_watch1': [100],
    'tr_m3_ord_watch2': [100],
    'tr_m3_ord_watch3': [100, 110],
    'tr_m3_ord_watch4': [100],
    'tr_m3_oth_alvana': [100, 110],
    'tr_m3_oth_arelothring': [100, 110, 120, 150],
    'tr_m3_oth_tt_1': [100],
    'tr_m3_oth_tt_2': [100, 110, 200],
    'tr_m3_oth_tt_3': [100],
    'tr_m3_oth_tt_4': [100, 200, 210],
    'tr_m3_oth_tt_5': [100],
    'tr_m3_oth_tt_6': [100, 150, 200],
    'tr_m3_rd_castingriches': [50, 60, 70, 71, 80],
    'tr_m3_rd_drinkstealrant': [100, 110, 150, 160, 165],
    'tr_m3_rd_extpunish': [45, 100, 110, 120, 130, 140, 200, 210, 220, 230],
    'tr_m3_rd_hiseyes': [100, 120, 200],
    'tr_m3_rils_grotto': [100, 101],
    'tr_m3_sa_inquiry': [60, 85, 90],
    'tr_m3_sa_thevoice': [100, 110, 120, 125, 130, 140, 150],
    'tr_m3_se_invest': [70],
    'tr_m3_ss_corroded': [100, 110, 120],
    'tr_m3_st_elimiran': [100, 200, 300],
    'tr_m3_stranded': [70],
    'tr_m3_sup_serialacc': [100],
    'tr_m3_sup_vampprank': [100, 101, 102, 103],
    'tr_m3_ta_strike': [50],
    'tr_m3_tg_at_q1': [100, 110],
    'tr_m3_tg_at_q2': [100],
    'tr_m3_tg_at_q3': [100, 110],
    'tr_m3_tg_at_q4': [100],
    'tr_m3_tg_at_q5': [100],
    'tr_m3_tg_at_q6': [150, 200],
    'tr_m3_tg_fentus2': [100],
    'tr_m3_tg_fentus3': [100, 120, 200],
    'tr_m3_tg_fentus3b': [100],
    'tr_m3_tg_fentus3d': [100, 110],
    'tr_m3_tg_fentus4': [100, 200],
    'tr_m3_tg_fentus5': [100],
    'tr_m3_tg_moranie1': [120, 250, 300],
    'tr_m3_tg_moranie2': [100, 105, 110, 200],
    'tr_m3_tg_moranie3': [115, 120, 250],
    'tr_m3_tou_tricksterknight': [100, 110],
    'tr_m3_tt_bloodstone': [100],
    'tr_m3_tt_dar_1': [100, 110],
    'tr_m3_tt_dar_2': [100],
    'tr_m3_tt_dar_3': [100],
    'tr_m3_tt_dar_4': [100],
    'tr_m3_tt_dar_5': [100, 101, 102],
    'tr_m3_tt_disembodied': [100],
    'tr_m3_tt_facestealer': [60, 100],
    'tr_m3_tt_ghosttrick': [100, 200],
    'tr_m3_tt_illene2': [100],
    'tr_m3_tt_illene3': [130, 140, 150],
    'tr_m3_tt_lloris1': [200, 225, 250, 300],
    'tr_m3_tt_lloris1c': [200],
    'tr_m3_tt_lloris2': [100, 175, 200],
    'tr_m3_tt_lloris3': [100],
    'tr_m3_tt_lloris4': [100, 150, 200],
    'tr_m3_tt_lloris5': [200, 250, 300],
    'tr_m3_tt_lloris6': [100],
    'tr_m3_tt_rip': [210, 220, 300],
    'tr_m3_tt_ritevoice': [100],
    'tr_m3_tt_ruinouskeep': [70],
    'tr_m3_tt_seeyou': [90, 100],
    'tr_m3_tt_seeyou_kha': [40, 60],
    'tr_m3_tt_speaker': [11, 30, 32, 100, 150, 200],
    'tr_m3_tt_stseryn_2': [100],
    'tr_m3_tt_stseryn_3': [100],
    'tr_m3_va_merihayan': [5, 20, 21, 25],
    'tr_m3_va_raenor': [100],
    'tr_m3_va_scrolldomination': [100, 150, 200],
    'tr_m3_var_doingwhatyoulove': [100, 110, 130, 140],
    'tr_m3_var_justiceforall': [100, 110, 200],
    'tr_m3_vf_shrine': [100, 101],
    'tr_m3_vh_bardstale': [100, 101],
    'tr_m3_vh_boots': [20],
    'tr_m3_vh_boots_a': [120],
    'tr_m3_vh_honns': [100, 110, 200],
    'tr_m3_vh_temple': [100, 101, 110],
    'tr_m3_vr_boundhelp': [100, 105, 110, 130],
    'tr_m3_wil_accountspayable': [100, 110, 120, 130],
    'tr_m3_wil_awillaway': [110],
    'tr_m3_wil_breakingthebinding': [100],
    'tr_m3_wil_brothchain': [100, 125, 150, 200],
    'tr_m3_wil_cleansweep': [100, 102, 103, 104],
    'tr_m3_wil_deadinthewater': [100, 200],
    'tr_m3_wil_esuranamit': [30],
    'tr_m3_wil_foeburner': [50, 100],
    'tr_m3_wil_haliwaran': [100, 200, 300],
    'tr_m3_wil_harrumat': [100, 101, 102],
    'tr_m3_wil_hvaldur': [100],
    'tr_m3_wil_kriepstheweak': [3, 4],
    'tr_m3_wil_seer': [100],
    'tr_m3_wil_zanammu': [40],
    'tr_m4_and_aab': [25, 30, 35, 40, 45],
    'tr_m4_and_alchemists_1': [65, 80, 100, 120],
    'tr_m4_and_alchemists_2': [100, 200],
    'tr_m4_and_alchemists_3': [15, 145],
    'tr_m4_and_alchemists_4': [50, 100],
    'tr_m4_and_alchemists_5': [100],
    'tr_m4_and_armistice': [90, 100, 200, 300],
    'tr_m4_and_bounty_boneeater': [25, 40, 50],
    'tr_m4_and_bounty_holst': [25, 40, 50],
    'tr_m4_and_bounty_rogueargonians': [25, 40, 50],
    'tr_m4_and_bounty_runat': [25, 40, 50],
    'tr_m4_and_bounty_vyper': [25, 40, 50],
    'tr_m4_and_credibility': [35, 40, 45, 50, 60, 70],
    'tr_m4_and_drowned': [100, 101, 102, 103, 110],
    'tr_m4_and_incthreat': [100, 110, 120, 130, 140],
    'tr_m4_and_materialmatters': [100],
    'tr_m4_and_missingmerchant': [100, 101, 102, 103, 104],
    'tr_m4_and_packrat': [100],
    'tr_m4_and_routinedelivery': [75, 76, 77, 78, 80, 85, 90, 95, 100],
    'tr_m4_and_shekindlyspoke': [100, 150, 200, 210],
    'tr_m4_and_soul': [5, 90, 95, 100, 110],
    'tr_m4_and_tmm': [10, 17, 18, 25, 40, 45],
    'tr_m4_and_tmm_ash': [6, 7, 8, 20],
    'tr_m4_arv_buriedsilver': [100],
    'tr_m4_arv_dravil': [100, 200],
    'tr_m4_arv_metamorphosis': [70, 90, 100],
    'tr_m4_arv_slavemistake': [1, 100, 150, 200, 250, 300],
    'tr_m4_arv_stolencargo': [5, 100, 110, 120, 130, 140, 200, 220],
    'tr_m4_arv_vampirefather': [100],
    'tr_m4_arv_vendelvisit': [120, 130, 160],
    'tr_m4_arv_vendelvisitd': [50, 60, 70],
    'tr_m4_bal0_troubles': [100, 200],
    'tr_m4_bal1_hunter': [100],
    'tr_m4_bal2_lair': [100],
    'tr_m4_bal3_arvsshadan': [100],
    'tr_m4_bal4_sathram': [100],
    'tr_m4_bal5_amuletspacts': [100],
    'tr_m4_bal_hannat': [100, 110],
    'tr_m4_bal_killorlukh': [100],
    'tr_m4_bd_armyyouhave': [100, 110, 120],
    'tr_m4_bd_lost_in_transit': [90, 91],
    'tr_m4_bd_lost_in_transit_a': [40],
    'tr_m4_bd_lost_in_transit_d': [10],
    'tr_m4_bd_redorandebt': [37, 40, 56, 60, 61, 63, 65, 70, 80],
    'tr_m4_bd_wesencolm': [20],
    'tr_m4_fa_fortancylishistory': [50],
    'tr_m4_fg_alits': [100, 105, 110],
    'tr_m4_fg_cliffracer': [200],
    'tr_m4_fg_darvas': [100, 105, 250, 275, 300, 400],
    'tr_m4_fg_hjaskar': [25, 26, 33, 35, 45, 46, 50, 55],
    'tr_m4_fg_map': [200],
    'tr_m4_fg_molsa': [100, 110],
    'tr_m4_fg_ushukur1': [100],
    'tr_m4_fg_ushukur2': [200, 250],
    'tr_m4_fg_ushukur3': [100, 125, 150, 200],
    'tr_m4_fg_ushukur4': [300],
    'tr_m4_fg_ushukur5': [550],
    'tr_m4_fg_ushukur5e': [100],
    'tr_m4_hh_and_caravanransom': [100],
    'tr_m4_hh_and_crates': [100],
    'tr_m4_hh_and_docksquests': [100, 110, 111],
    'tr_m4_hh_and_employment': [100, 110],
    'tr_m4_hh_and_employment2': [100, 120],
    'tr_m4_hh_and_greef': [100, 110],
    'tr_m4_hh_and_greef2': [100],
    'tr_m4_hh_and_hearing': [100, 105, 110],
    'tr_m4_hh_and_omaynisinn': [80, 85, 100, 101, 110],
    'tr_m4_hh_and_reconciliation': [100],
    'tr_m4_hh_and_reverserescue': [100, 110, 120, 130, 135],
    'tr_m4_hh_and_ship': [100, 110, 170, 200],
    'tr_m4_hh_and_ship2': [11],
    'tr_m4_hh_salvaniwine': [100],
    'tr_m4_hh_ulvo1': [100, 120],
    'tr_m4_hh_ulvo2': [100],
    'tr_m4_hh_ulvo3': [100],
    'tr_m4_hh_ulvo4': [100, 105, 110, 120],
    'tr_m4_il_agent': [100, 101, 110],
    'tr_m4_il_dreugh': [100],
    'tr_m4_il_freedom': [100, 110],
    'tr_m4_il_giveledger': [10],
    'tr_m4_il_grudge': [100, 105, 110, 120, 130],
    'tr_m4_il_grudgeb': [5],
    'tr_m4_il_kathletter': [100, 120],
    'tr_m4_il_savrethkey': [10, 15, 20],
    'tr_m4_il_smuggler': [100],
    'tr_m4_indal_mudcrabslayer': [40, 50, 60, 70, 80, 90],
    'tr_m4_ir_willtogoon': [100],
    'tr_m4_ish_nerevarine': [100, 150, 155, 200],
    'tr_m4_mg_ando_1': [100],
    'tr_m4_mg_ando_2': [100, 110, 150, 160],
    'tr_m4_mg_ando_3': [100],
    'tr_m4_mg_ando_4': [100, 110],
    'tr_m4_mg_ando_5': [100],
    'tr_m4_mg_ando_5a': [100],
    'tr_m4_mg_ando_6': [100],
    'tr_m4_mg_ando_7': [100, 200],
    'tr_m4_mg_ando_8': [100],
    'tr_m4_mg_ando_8a': [95, 100, 105],
    'tr_m4_mn_assassin': [30, 40, 50],
    'tr_m4_mn_shorted': [100, 110],
    'tr_m4_mp_slavewhisperer': [20, 120, 121, 122, 130, 140, 150],
    'tr_m4_mt_almse': [100, 110],
    'tr_m4_mt_dransa': [100, 110],
    'tr_m4_mt_ilmeni': [100, 110],
    'tr_m4_mt_jebyn': [100, 110],
    'tr_m4_mt_llirala': [100, 110],
    'tr_m4_mt_nadrasarvel': [100, 110],
    'tr_m4_mt_omayn': [100, 110],
    'tr_m4_mt_serali': [100, 110],
    'tr_m4_mt_sp_gulmon': [100, 110, 111, 112, 113],
    'tr_m4_mt_sp_gulmon_writ': [100, 110],
    'tr_m4_mt_tolmse': [100, 110],
    'tr_m4_ob_ancestral_guidance': [100, 200],
    'tr_m4_ob_poisoning_the_well': [15, 45, 100, 110, 150, 200],
    'tr_m4_om_remnantsresdayn': [10, 100, 110, 200, 210, 220, 230, 240, 300, 310, 320, 330, 340, 350],
    'tr_m4_om_statue': [10, 110, 130, 200],
    'tr_m4_ord_rite': [100],
    'tr_m4_t_euphoria': [100, 115, 130, 145, 150],
    'tr_m4_t_ilvaalmuunbound': [20, 30, 50],
    'tr_m4_t_lighthouse': [1, 2, 100],
    'tr_m4_t_motherinlaw': [20, 40, 100],
    'tr_m4_t_nuccius': [45, 50, 55, 60, 66, 91, 99, 100, 110, 120, 140, 145, 150, 160, 1000, 1001, 1002],
    'tr_m4_t_nuccius_wager': [32, 35, 40],
    'tr_m4_tg_marug1': [100, 150, 200],
    'tr_m4_tg_rilmas1': [100],
    'tr_m4_tg_rilmas2': [150, 200, 250, 300],
    'tr_m4_tg_shei1': [2, 100, 110, 150, 175, 200],
    'tr_m4_tg_shei3': [100, 150, 200],
    'tr_m4_tg_shei4': [150],
    'tr_m4_tg_shei5': [300, 325, 350],
    'tr_m4_tg_shei5f': [20, 50],
    'tr_m4_tg_shei6': [200, 225, 250, 275, 300],
    'tr_m4_tg_tattara1': [100, 200, 300],
    'tr_m4_tg_threeeyes1': [100, 125, 150, 175, 200, 250, 300, 400],
    'tr_m4_tg_threeeyes2': [200, 250],
    'tr_m4_tg_threeeyes2c': [200],
    'tr_m4_tg_threeeyes2e': [10, 20],
    'tr_m4_tj_daedricdinner': [50, 100],
    'tr_m4_tj_heartthief': [90, 100],
    'tr_m4_tj_mt_1': [110, 200],
    'tr_m4_tt_andothrencharity': [100],
    'tr_m4_tt_armunadventure': [100],
    'tr_m4_tt_armunadventure_e': [90, 100],
    'tr_m4_tt_booksbarbarians': [100, 110, 120, 200],
    'tr_m4_tt_forgiveness': [100, 101, 102, 103],
    'tr_m4_tt_kitchensupplies': [100, 101],
    'tr_m4_tt_lastwillandtestament': [60, 200],
    'tr_m4_tt_shrinealmafury': [10],
    'tr_m4_tt_shrinebodrum': [10],
    'tr_m4_tt_shrineolmsrest': [10],
    'tr_m4_tt_staralor_q1': [100],
    'tr_m4_tt_staralor_q2': [100],
    'tr_m4_tt_staralor_q3': [100, 110],
    'tr_m4_tt_stf_aum_pilgrimage': [30],
    'tr_m4_tt_stf_destroy_ancient': [30, 100],
    'tr_m4_tt_stf_mf_pilgrimage': [30],
    'tr_m4_tt_troublesomeorc': [100, 110, 120, 130, 140, 210],
    'tr_m4_tt_wellnesscheck': [100, 101],
    'tr_m4_uman_b1': [40],
    'tr_m4_uman_b2': [40, 45, 200],
    'tr_m4_uman_b3': [40],
    'tr_m4_va_barendrethprotection': [100],
    'tr_m4_va_destroybaluath': [200],
    'tr_m4_va_ibinai': [100, 110, 120, 130, 200, 210],
    'tr_m4_va_invasion': [180, 200],
    'tr_m4_va_ironandblood': [90, 100, 200, 210, 215, 220],
    'tr_m4_va_moreblood': [100],
    'tr_m4_va_namira': [100, 225],
    'tr_m4_va_ovamphunt': [200],
    'tr_m4_va_proper': [200],
    'tr_m4_va_propylon': [200],
    'tr_m4_va_roadside': [50],
    'tr_m4_va_termination': [5, 100, 200, 250],
    'tr_m4_va_vrashmind': [105, 130, 135],
    'tr_m4_va_warmblooded': [100],
    'tr_m4_vf_mancrystal': [100, 200],
    'tr_m4_wickedwater': [85, 90, 100, 110, 120, 130, 140],
    'tr_m4_wil_ahnaissa': [100, 101, 102, 103],
    'tr_m4_wil_argonianbandits': [20, 30, 40, 50, 75, 100],
    'tr_m4_wil_armunroadblock': [50, 75, 80, 150, 200],
    'tr_m4_wil_banditduo': [100, 200],
    'tr_m4_wil_belbetu1': [40, 70],
    'tr_m4_wil_belbetu2': [100],
    'tr_m4_wil_belbetu3': [120],
    'tr_m4_wil_buyingrope': [30, 40, 50],
    'tr_m4_wil_catcatchers': [100, 105, 110],
    'tr_m4_wil_catcatchersb': [100, 105],
    'tr_m4_wil_curedredasedevani': [100, 150, 200],
    'tr_m4_wil_emmurbalpitu': [100, 105, 110, 120],
    'tr_m4_wil_ganahiru': [15, 100, 110, 120],
    'tr_m4_wil_hautharmokill': [200],
    'tr_m4_wil_householdslave': [25, 100, 110, 200],
    'tr_m4_wil_immetarca': [40],
    'tr_m4_wil_joscus': [100, 200],
    'tr_m4_wil_koboldfisher': [105, 110, 115, 120, 130, 200],
    'tr_m4_wil_mannuscamps': [5, 30, 100, 200, 250],
    'tr_m4_wil_mydearfriendarvena': [60],
    'tr_m4_wil_nakedwitch': [15, 80, 90, 95, 100, 102, 103, 104, 106, 108, 109, 110],
    'tr_m4_wil_nirnboundsaint': [13, 150, 200, 210],
    'tr_m4_wil_nirnboundsaintb': [120],
    'tr_m4_wil_nirnboundsaintc': [100],
    'tr_m4_wil_oranescaped': [105, 110, 120],
    'tr_m4_wil_oranescaped2': [40],
    'tr_m4_wil_oranmissingbrother': [5, 30, 40],
    'tr_m4_wil_skeletonwizard': [5, 50, 100],
    'tr_m4_wil_strayguars': [100],
    'tr_m4_wil_taxmanindalruhn': [40, 45, 50],
    'tr_m4_wil_tribunalts': [15, 18, 27, 29, 98, 100, 101, 110, 121, 123, 125, 130, 131],
    'tr_m4_wil_troupe_trouble': [40, 60, 130],
    'tr_m4_wil_urnuridunguar': [100, 200, 300],
    'tr_m6_wil_eggminedelivery': [100, 110, 200],
    'tr_m7_ai_infestation': [100, 110, 120],
    'tr_m7_ai_jns_1': [100],
    'tr_m7_ai_jns_2': [100],
    'tr_m7_ai_jns_3': [100, 200],
    'tr_m7_ai_jns_4': [100],
    'tr_m7_ai_jns_5': [100],
    'tr_m7_ai_jns_6': [100],
    'tr_m7_ai_jns_7': [100],
    'tr_m7_ai_nuccius_guar': [40, 45, 50, 51, 52, 99],
    'tr_m7_ai_ornadabtd': [100, 125, 150],
    'tr_m7_ai_sweetwaterdreugh': [100, 110],
    'tr_m7_ai_tt_q1': [100, 110],
    'tr_m7_ai_tt_q2': [100, 110, 120],
    'tr_m7_ai_tt_q3': [100],
    'tr_m7_ai_tt_q4': [100, 110, 120],
    'tr_m7_ai_tt_q5': [100, 110, 120, 130, 140],
    'tr_m7_ai_tt_q6': [100, 110, 200, 210, 220],
    'tr_m7_am_alwayssomething': [100, 110, 120],
    'tr_m7_am_freeinggulveeus': [100, 110, 120, 130],
    'tr_m7_da_meridia': [100],
    'tr_m7_da_namira': [25, 100, 105, 110],
    'tr_m7_db_special1': [100],
    'tr_m7_eec_narsis1': [100],
    'tr_m7_eec_narsis2': [100, 110, 120],
    'tr_m7_eec_narsis3': [100],
    'tr_m7_eec_narsis4': [100, 110],
    'tr_m7_eec_narsis5': [100],
    'tr_m7_eec_narsis6': [100],
    'tr_m7_eec_narsis7': [100],
    'tr_m7_eec_narsis8': [80],
    'tr_m7_fg_hl_q1': [100],
    'tr_m7_fg_hl_q2': [100],
    'tr_m7_fg_hl_q3': [100],
    'tr_m7_fg_hl_q4': [100, 200],
    'tr_m7_fg_hl_q5': [100],
    'tr_m7_fg_hl_q6': [100, 200],
    'tr_m7_fg_krag_rescue': [100, 150, 200],
    'tr_m7_fg_narsismaster_casimor': [100],
    'tr_m7_fg_narsismaster_consulate': [100],
    'tr_m7_fg_narsismaster_hlaalu': [100],
    'tr_m7_fg_narsismaster_rescue': [100, 150],
    'tr_m7_hh_alvynu_1': [100],
    'tr_m7_hh_alvynu_2': [100],
    'tr_m7_hh_alvynu_3': [100],
    'tr_m7_hh_alvynu_4': [100, 101],
    'tr_m7_hh_alvynu_5': [100],
    'tr_m7_hh_alvynu_6': [100],
    'tr_m7_hh_alvynu_7': [100, 101],
    'tr_m7_hh_dren': [100],
    'tr_m7_hh_firstfamily_1': [100],
    'tr_m7_hh_firstfamily_2': [62, 100, 110],
    'tr_m7_hh_gm_1': [200],
    'tr_m7_hh_gm_2z': [100, 200],
    'tr_m7_hh_gm_3za': [100],
    'tr_m7_hh_gm_3zb': [100],
    'tr_m7_hh_gm_4': [100],
    'tr_m7_hh_gm_4a': [30],
    'tr_m7_hh_gm_4b': [60, 250],
    'tr_m7_hh_gm_4c': [60, 70],
    'tr_m7_hh_gm_5': [100],
    'tr_m7_hh_gm_6': [250, 255],
    'tr_m7_hh_gm_7': [40, 50],
    'tr_m7_hh_gm_8': [100],
    'tr_m7_hh_raran1': [100, 200],
    'tr_m7_hh_raran2': [40, 60, 80, 100],
    'tr_m7_hh_sathis1': [100, 200, 250],
    'tr_m7_hh_sathis2': [100],
    'tr_m7_hh_sathis3': [100, 125, 150, 200, 250],
    'tr_m7_hh_sathis4': [200, 250],
    'tr_m7_hh_sathis5': [100],
    'tr_m7_hh_sathis6': [100, 125, 150, 200],
    'tr_m7_hh_seventhfamily_1': [100, 200],
    'tr_m7_hh_seventhfamily_2': [100, 110],
    'tr_m7_hh_sixthfamily_1': [100, 110],
    'tr_m7_hh_sixthfamily_2': [100, 110, 120],
    'tr_m7_hh_vedas1': [100, 125],
    'tr_m7_hh_vedas2': [100],
    'tr_m7_hl_affairsheart': [310, 320, 330, 500],
    'tr_m7_hl_helpingothers': [10, 40, 100, 110, 120, 130, 200],
    'tr_m7_hl_partnersinwine': [100],
    'tr_m7_hl_pauperandprince': [100, 110],
    'tr_m7_hl_pearlsforconrel': [100],
    'tr_m7_hl_provingfaith': [30, 100, 120, 130],
    'tr_m7_ho_cluelesseggminer': [120],
    'tr_m7_ho_divingforarns': [100, 101],
    'tr_m7_ho_guide': [100, 101, 102, 103, 110, 111],
    'tr_m7_ho_highanddry': [100, 110, 150, 200, 210],
    'tr_m7_ho_houseforsale_a': [100, 200],
    'tr_m7_ho_lost': [100],
    'tr_m7_ho_missingfriend': [100],
    'tr_m7_ho_passagemenevia': [100, 101, 102, 150, 200, 210],
    'tr_m7_ho_strabobook': [100, 150, 200, 300],
    'tr_m7_ho_tt_01': [100],
    'tr_m7_ho_tt_02': [100, 110],
    'tr_m7_ho_tt_03': [100, 110, 120],
    'tr_m7_ho_tt_04': [100, 111, 121, 131, 200],
    'tr_m7_ho_tt_05': [100, 110, 111, 120, 121, 130, 131, 132],
    'tr_m7_ho_tt_06': [100],
    'tr_m7_ho_tt_07': [100, 210, 220, 230, 240, 241],
    'tr_m7_ho_tt_shrineho': [10],
    'tr_m7_hr_aldiuval_q1': [100],
    'tr_m7_hr_aldiuval_q2': [100],
    'tr_m7_hr_aldiuval_q3': [100],
    'tr_m7_hr_aldiuval_q4': [100, 110],
    'tr_m7_hr_aldiuval_q5': [100, 125],
    'tr_m7_hr_am_01': [100],
    'tr_m7_hr_am_02': [100],
    'tr_m7_hr_am_03': [100],
    'tr_m7_hr_am_04': [100],
    'tr_m7_hr_am_05': [100],
    'tr_m7_hr_wm_ep': [100],
    'tr_m7_ic_maria1': [100],
    'tr_m7_ic_maria2': [100],
    'tr_m7_ic_maria3': [100],
    'tr_m7_ic_maria4': [100],
    'tr_m7_ic_maria5': [100],
    'tr_m7_ic_maria5_a': [100],
    'tr_m7_ic_maria6': [100, 200],
    'tr_m7_ic_maria7': [100, 200],
    'tr_m7_ic_maria8': [100, 200, 300],
    'tr_m7_ida_net': [100, 101, 111, 120, 121, 122],
    'tr_m7_il_hl_q1': [100],
    'tr_m7_il_hl_q2': [100, 120, 125],
    'tr_m7_il_hl_q3': [100, 110],
    'tr_m7_il_hl_q4': [100, 120],
    'tr_m7_insearchofsnacks': [100, 200],
    'tr_m7_jns_theboss_breathingin': [100],
    'tr_m7_jns_theboss_breathingout': [100],
    'tr_m7_jns_theboss_consolidation': [100],
    'tr_m7_jns_theboss_endoftheline': [100],
    'tr_m7_jns_theboss_snakeeyes': [100],
    'tr_m7_maarbani_suppliessd': [100, 200, 210],
    'tr_m7_mt_hagar': [100, 110],
    'tr_m7_mt_hlevis': [100, 110],
    'tr_m7_mt_ibarmas': [100, 110],
    'tr_m7_mt_llevas': [100, 110],
    'tr_m7_mt_milena': [100, 110],
    'tr_m7_mt_nelyos': [100, 110],
    'tr_m7_mt_peleri': [100, 110],
    'tr_m7_mt_selvura': [100, 110],
    'tr_m7_mt_special1': [200],
    'tr_m7_mt_special2': [100],
    'tr_m7_mt_special3': [150],
    'tr_m7_mt_special3a': [50],
    'tr_m7_mt_special4': [100],
    'tr_m7_mt_turesa': [100, 110],
    'tr_m7_mt_ulvys': [100, 110],
    'tr_m7_ns_air': [15, 100, 200, 300],
    'tr_m7_ns_arena_01': [100, 105, 120],
    'tr_m7_ns_arena_02': [100, 105, 120],
    'tr_m7_ns_arena_03': [100],
    'tr_m7_ns_arena_04': [100, 120],
    'tr_m7_ns_arena_05': [100, 105, 120],
    'tr_m7_ns_arena_06': [100],
    'tr_m7_ns_arena_07': [100, 105, 120],
    'tr_m7_ns_arena_08': [100, 105, 120],
    'tr_m7_ns_arena_09': [99, 100, 120],
    'tr_m7_ns_arena_10': [100, 105, 120],
    'tr_m7_ns_arena_11': [100, 105, 110, 115, 120, 125, 130],
    'tr_m7_ns_arena_12': [100],
    'tr_m7_ns_arena_13': [100],
    'tr_m7_ns_bearingbadnews': [110, 120, 130, 140, 200],
    'tr_m7_ns_beneathstvelothsgaze': [100, 110, 120, 130],
    'tr_m7_ns_bilchabul': [200, 300, 450, 600],
    'tr_m7_ns_caravan': [100, 200, 300],
    'tr_m7_ns_casino_accountant': [11, 100, 200],
    'tr_m7_ns_distaste': [100, 150, 175, 200],
    'tr_m7_ns_fg_1': [100, 110],
    'tr_m7_ns_fg_2': [100],
    'tr_m7_ns_fg_3': [100],
    'tr_m7_ns_fg_4': [100],
    'tr_m7_ns_fg_5': [100, 110],
    'tr_m7_ns_fg_6': [100, 110],
    'tr_m7_ns_fg_7': [100],
    'tr_m7_ns_fg_8': [100, 110],
    'tr_m7_ns_hh_angryletter': [100],
    'tr_m7_ns_hh_angrylettera': [100, 110],
    'tr_m7_ns_hh_rentfarming': [100],
    'tr_m7_ns_hh_rentfarminga': [100],
    'tr_m7_ns_hh_rentfarmingb': [100, 110],
    'tr_m7_ns_hh_rentfarmingc': [100],
    'tr_m7_ns_ic1': [100],
    'tr_m7_ns_ic2': [100],
    'tr_m7_ns_ic3': [100],
    'tr_m7_ns_ic4': [100, 110, 120, 130],
    'tr_m7_ns_ic5': [100, 110, 120, 130],
    'tr_m7_ns_ic6': [100],
    'tr_m7_ns_ic7': [110],
    'tr_m7_ns_ic8': [100, 110],
    'tr_m7_ns_il_1': [100],
    'tr_m7_ns_il_2': [100],
    'tr_m7_ns_il_3': [100, 200],
    'tr_m7_ns_il_4': [100],
    'tr_m7_ns_il_5': [100, 110],
    'tr_m7_ns_il_6': [100],
    'tr_m7_ns_il_7': [100],
    'tr_m7_ns_il_8': [100],
    'tr_m7_ns_il_9': [100, 200, 250],
    'tr_m7_ns_irwaen': [100, 110],
    'tr_m7_ns_jns_1': [100],
    'tr_m7_ns_jns_2': [100, 101],
    'tr_m7_ns_jns_3': [100, 101],
    'tr_m7_ns_jns_4': [100, 200],
    'tr_m7_ns_jns_5': [100],
    'tr_m7_ns_jns_6': [100],
    'tr_m7_ns_jns_7': [100, 110],
    'tr_m7_ns_joincamonnatong': [100, 110, 120, 200],
    'tr_m7_ns_matterofpedigree': [105, 110, 120],
    'tr_m7_ns_mg_alch': [100],
    'tr_m7_ns_mg_alt': [100],
    'tr_m7_ns_mg_arch01': [100, 110],
    'tr_m7_ns_mg_arch02': [100],
    'tr_m7_ns_mg_arch03': [100, 105, 110],
    'tr_m7_ns_mg_conj': [100],
    'tr_m7_ns_mg_des': [100],
    'tr_m7_ns_mg_desa': [100],
    'tr_m7_ns_mg_ench': [100],
    'tr_m7_ns_mg_ill': [100],
    'tr_m7_ns_mg_mys': [100],
    'tr_m7_ns_mg_rest': [100],
    'tr_m7_ns_moonshiner': [100, 110, 120],
    'tr_m7_ns_movinghouse': [100, 101, 102, 110],
    'tr_m7_ns_nicering': [100, 101, 110],
    'tr_m7_ns_payingdues': [60, 70, 90, 100, 110, 120, 130],
    'tr_m7_ns_piousandpersecuted': [50, 110, 150],
    'tr_m7_ns_rescuepotlady': [100, 101, 102],
    'tr_m7_ns_robbingancestors': [100, 150, 200, 300, 350],
    'tr_m7_ns_robeheavyswinging': [100, 110, 120],
    'tr_m7_ns_shocktherapy': [100, 110],
    'tr_m7_ns_sinkorswim': [100, 110, 120],
    'tr_m7_ns_talebreathbrine': [100, 110, 111, 114, 120, 130, 135, 137, 140],
    'tr_m7_ns_tg_1': [100],
    'tr_m7_ns_tg_2': [100],
    'tr_m7_ns_tg_3': [100],
    'tr_m7_ns_tg_4': [100],
    'tr_m7_ns_tg_5': [100],
    'tr_m7_ns_tg_6': [100],
    'tr_m7_ns_tg_7': [100],
    'tr_m7_ns_tg_8': [100, 105],
    'tr_m7_ns_tg_9': [100, 105, 150],
    'tr_m7_ns_tothelastdrop': [100, 110, 120, 130],
    'tr_m7_ns_traipsing': [100, 200, 300, 310],
    'tr_m7_ns_tt_chavana1': [100, 110, 120],
    'tr_m7_ns_tt_chavana2': [70, 101],
    'tr_m7_ns_tt_chavana3': [100],
    'tr_m7_ns_tt_chavana3a': [100, 110, 120],
    'tr_m7_ns_tt_chavana4': [100, 110],
    'tr_m7_ns_tt_orvayn1': [100],
    'tr_m7_ns_tt_orvayn2': [100],
    'tr_m7_ns_tt_orvayn3': [100, 110],
    'tr_m7_ns_tt_orvayn4': [100],
    'tr_m7_ns_tt_orvayn5': [100, 110],
    'tr_m7_oth_banditsinkuriki': [100],
    'tr_m7_oth_brotherslove': [100, 110, 120],
    'tr_m7_oth_bugtracker': [95, 100, 110, 120, 150],
    'tr_m7_oth_changinghouses': [26, 30],
    'tr_m7_oth_edalvelletter': [100, 110, 150, 160, 170],
    'tr_m7_oth_familybusiness': [100, 105, 110, 120],
    'tr_m7_oth_hh_1': [100],
    'tr_m7_oth_hh_2': [100, 110, 120],
    'tr_m7_oth_hh_3': [100, 110, 120, 130],
    'tr_m7_oth_hh_4': [100, 110, 120],
    'tr_m7_oth_hh_5': [100, 110, 120],
    'tr_m7_oth_hh_6': [100, 110, 120],
    'tr_m7_oth_hh_7': [100, 120, 140, 150],
    'tr_m7_oth_mg_1': [100, 110],
    'tr_m7_oth_mg_2': [100],
    'tr_m7_oth_mg_3': [100, 101, 102],
    'tr_m7_sdr_defilingwithholiness': [100, 110, 120, 130, 140, 150],
    'tr_m7_sdr_thestinkcurse': [50, 60, 80, 90, 100],
    'tr_m7_sepgap_shinathi': [110, 120, 130, 140, 150, 155, 160],
    'tr_m7_shin_bornnecro': [120],
    'tr_m7_shin_renderingassistance': [100, 110, 120],
    'tr_m7_shisha_familyaffair': [100, 110, 120, 125, 150, 175, 200],
    'tr_m7_shisha_hh_1': [100],
    'tr_m7_shisha_hh_2': [100, 150, 200],
    'tr_m7_shisha_hh_3': [100],
    'tr_m7_shisha_hh_4': [100],
    'tr_m7_shisha_il_1': [100, 110, 120],
    'tr_m7_shisha_il_2': [100, 110],
    'tr_m7_shisha_il_3': [100, 110, 120, 121],
    'tr_m7_shisha_il_4': [120],
    'tr_m7_shisha_liftspirits': [100, 110, 120],
    'tr_m7_shisha_painting': [100, 125, 150],
    'tr_m7_shisha_sense': [50, 60, 70, 80, 100],
    'tr_m7_slavetrouble': [80, 85, 90, 100, 110, 120, 140, 150],
    'tr_m7_stdelyn_tt_01': [100],
    'tr_m7_stdelyn_tt_02': [100],
    'tr_m7_stdelyn_tt_03': [100],
    'tr_m7_thedeadpilgrim': [100, 110, 120, 130, 140],
    'tr_m7_tt_pedestalmuatra': [10],
    'tr_m7_tt_shrineconviction': [10],
    'tr_m7_va_anivamp': [100, 101, 102, 103],
    'tr_m7_va_daedricorigin': [10, 50, 60, 80, 100],
    'tr_m7_wil_dralnasvirian': [100, 110, 200, 210],
    'tr_m7_wil_fatherslove': [100],
    'tr_m7_wil_longwaydown': [100, 110, 130, 140],
    'tr_m7_wil_lurkerinthemangrove': [50, 100],
    'tr_m7_wil_nymph': [50, 200, 210],
    'tr_m7_wil_oneclan': [100, 110, 200],
    'tr_m7_wil_onrocks': [50, 100, 110, 120],
    'tr_m7_wil_secretmaster': [100],
    'tr_m7_wil_thrashthresher': [100, 110],
    'tr_m7_wil_trevasatribulations': [100],
    'tr_m7_yand_airdominance': [100, 110, 120],
    'tr_necmq_1': [55],
    'tr_tt_q1': [100],
    'tt_alddaedroth': [100],
    'tt_aldsotha': [100],
    'tt_assarnibibi': [100, 110],
    'tt_balur': [100],
    'tt_compassion': [100, 200],
    'tt_curingtouch': [100],
    'tt_dagonfel': [100],
    'tt_diseasecarrier': [100],
    'tt_falseincarnate': [100],
    'tt_felmscleaver': [100, 110],
    'tt_fieldskummu': [100],
    'tt_galomdeus': [100],
    'tt_ghostgate': [100],
    'tt_hairshirt': [100, 110],
    'tt_hassour': [100],
    'tt_llothiscrosier': [100, 110],
    'tt_maargan': [100],
    'tt_maskvivec': [100],
    'tt_mawia': [100],
    'tt_ministryheathen': [100],
    'tt_mountkand': [100, 110],
    'tt_palacevivec': [100],
    'tt_pilgrimspath': [100],
    'tt_puzzlecanal': [100],
    'tt_rilmsshoes': [100, 110],
    'tt_ruddyman': [100],
    'tt_sanctusshrine': [100],
    'tt_sevengraces': [100],
    'tt_staralor': [100],
    'tt_stopmoon': [100],
    'tt_supplymonk': [100],
    'va_shashev': [100],
    'va_vampamulet': [40, 50],
    'va_vampblood': [50],
    'va_vampblood2': [100],
    'va_vampchild': [120, 130],
    'va_vampcountess': [60, 70],
    'va_vampcult': [120],
    'va_vampcurse': [100],
    'va_vampdust': [100],
    'va_vamphunter': [80, 90, 100, 110],
    'va_vampmarara': [100],
    'va_vamprich': [80],
})
# END UESP OVERRIDES

# Stages to add to the automatic deduction (endings not flagged quest_finish).
STAGES_EXTRA = {
    # 'quest_id': [stage, ...],
    'mv_monsterdisease': [60],
}

# Stages to remove from the automatic deduction (intermediate, dialogues,
# refusals/abandonments...). Verified against the journal text (quest_review.txt).
_HORT = [5, 10, 20]
STAGES_EXCLUDE = {
    'a1_1_findspymaster': [20],
    'a1_sleepersawake': [1, 7],
    'a1_v_vivecinformants': [55],
    'a2_6_incarnate': [52, 54, 60, 62, 64, 70, 72, 74, 76, 78, 80],
    'b5_arobarhort': _HORT, 'b5_llethrihort': _HORT,
    'b5_morvaynhort': _HORT, 'b5_ramoranhort': _HORT,
    'b6_berohort': [5], 'b6_curiohort': [5], 'b6_omanihort': [5, 20],
    'b6_uleshort': [5, 20], 'b6_ynglinghort': [5, 20],
    'b7_baladashort': [5, 30], 'b7_drathahort': [5, 10, 30],
    'b7_gothrenhort': [5], 'b7_nelothhort': [5, 30], 'b7_theranahort': [5, 30],
    'c0_act_c': [1, 2, 3, 4, 5, 6, 7, 10, 15],
    'cx_backpath': [5, 10, 55, 60],
    'da_azura': [40], 'da_mehrunes': [10], 'da_molagbal': [10],
    'da_sheogorath': [20, 40, 50, 55],
    'hh_wincamonna': [5], 'hr_calderacorrupt': [30],
    'ht_archmagister': [10], 'ht_stronghold': [105],
    'ic12_dinner_not': [0], 'ic26_amanin': [5, 10], 'ic29_crusher': [10, 15],
    'ic8_heidmir': [10], 'ic8_ingokning': [10],
    'il_blueprints': [10], 'ms_fargothring': [10],
    'ms_jobashaabolitionist': [10], 'ms_piernette': [10],
    'ms_umbra': [10, 20, 30, 40], 'mt_grandmaster': [10, 20],
    'mv_abusedhealer': [60], 'mv_tradermissed': [110],
    'town_aldruhn': [50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 76, 77, 78, 79],
    'town_tel_vos_ashur': [1],
    'va_vampamulet': [10, 25], 'va_vampcountess': [30], 'va_vampmarara': [20, 40],
}

# Stages that cancel completion (failure branch).
FAIL_STAGES = {
    'fg_nchurdamz': [110],
    'il_maidentoken': [120],
    'il_rescuepilgrim': [200],
    'mv_recoverwidowmaker': [90],
    'mv_strayedpilgrim': [110, 115],
    'tt_diseasecarrier': [110],
    'tt_ministryheathen': [200],
    'tt_sanctusshrine': [110],
    'mv_abusedhealer': [80],
    'b3_zainabbride': [60],
    'eb_invisible': [140],
    'mv_cultistvictim': [110],
    'mv_fakeslave': [90],       # Tul dies on the way
    'mv_poorpilgrim': [110],    # time ran out
    'mv_richtrader': [110],     # the merchant dies
    'mv_thieftrader': [30, 35], # refused to help Lucan
    'mv_victimromance': [50],   # refused to look for Nelos
    # Fargoth's Hiding Place: stage 30 is the refusal ("No? Well, I'll find
    # someone else to do it, then."). lookoutScript treats it as terminal, so
    # it must not validate the quest; the only success is stage 100.
    'ms_lookout': [30],
    # Foul Murder: Simine (190) or Alvu (195) dies; 199 is the resulting
    # softlock marker. None of them may validate the main quest.
    'tr_necmq_3': [190, 195, 199],
    # Aimrah Dreugh questline. Dreugh1 stage 110 reports the body to a guard
    # (the priest is jailed) and Dreugh2 stage 120 is "Ivon Seloth is dead":
    # both are failure branches, not successful endings. Dreugh2 is only
    # triggered by Dreugh1 at stage 100 (not 110), so the success path must
    # not treat 110 as a completion.
    'tr_m3_aim_dreugh1': [110],
    'tr_m3_aim_dreugh2': [120],
    # --- Missed failure branches found by scanning quest prerequisites -----
    # A successor requires an exact earlier stage (Journal "X" == n): the
    # higher "Finishes quest" stages below are terminal failures (death,
    # expulsion, refusal, explicit failure) and must not validate the quest.
    # Alternate endings (ringlets, arena, ...) are deliberately not listed.
    'fg_dissaplamine': [110],
    'fg_suranbandits': [110],
    'hh_indesp2': [110, 200],
    'tg_brotherbragor': [110],
    'tg_ss_generosity1': [110],
    'tg_ss_greedyslaver': [110, 120],
    'tr_m1_fg_mandaran': [110],
    'tr_m1_fg_past': [110, 200],
    'tr_m1_fw_mg07': [300],
    'tr_m1_ht_mi1': [70],
    'tr_m1_ht_rathra_q1': [150],
    'tr_m1_tt_4': [51, 150],
    'tr_m1_tt_6': [150],
    'tr_m2_fg_hartise_eggmine': [110, 120, 200],
    'tr_m2_fg_hartise_joran': [110],
    'tr_m2_fg_hartise_rethyn': [120],
    'tr_m2_fg_hartise_selyn': [110, 120],
    'tr_m2_fg_hartise_tainted': [110, 120, 130, 200],
    'tr_m2_fg_irano2': [120, 123, 125],
    'tr_m2_he_tg1': [500, 510],
    'tr_m2_he_tg2': [200, 510],
    'tr_m2_he_tg3': [200, 510],
    'tr_m2_ht_vaerin_q1': [150],
    'tr_m2_ht_vaerin_q2': [125, 150],
    'tr_m2_ht_vaerin_q5': [150],
    'tr_m2_ic_widower': [50, 60],
    'tr_m3_at_mg05': [110],
    'tr_m3_eec_cano2': [300],
    'tr_m3_fg_oe_ghosts': [101, 102],
    'tr_m3_hi_mq1_2': [110],
    'tr_m3_hi_nanaav1': [110],
    'tr_m3_hi_nanaav2': [110],
    'tr_m3_il_judge': [101],
    'tr_m3_il_jury': [101],
    'tr_m3_il_testimony': [150],
    'tr_m3_mg_oe_q4': [110],
    'tr_m3_mg_oe_q5': [120],
    'tr_m3_mg_oe_q7': [120],
    'tr_m3_ord_doc2': [103],
    'tr_m3_ord_war3': [200, 300],
    'tr_m3_tt_dar_3': [110],
    'tr_m4_arv_vampirefather': [110, 120],
    'tr_m4_bal_hannat': [200],
    'tr_m4_hh_and_caravanransom': [150],
    'tr_m4_il_agent': [200, 201],
    'tr_m4_il_freedom': [105],
    'tr_m4_tg_shei4': [200],
    'tr_m4_tt_staralor_q2': [110, 200],
    'tr_m4_tt_stf_aum_pilgrimage': [100],
    'tr_m4_tt_stf_mf_pilgrimage': [100],
    'tr_m4_tt_wellnesscheck': [110],
    'tr_m4_wil_belbetu1': [110],
    'tr_m4_wil_belbetu2': [120],
    'tr_m7_eec_narsis3': [110, 120],
    'tr_m7_fg_narsismaster_consulate': [200],
    'tr_m7_fg_narsismaster_rescue': [200],
    'tr_m7_hh_alvynu_1': [200, 300],
    'tr_m7_hh_alvynu_2': [200],
    'tr_m7_hh_alvynu_4': [102],
    'tr_m7_hh_alvynu_5': [101],
    'tr_m7_hh_alvynu_6': [101],
    'tr_m7_hh_gm_1': [250],
    'tr_m7_hh_gm_5': [250],
    'tr_m7_ho_tt_02': [200, 201],
    'tr_m7_ho_tt_04': [210, 211, 220, 221, 300, 301],
    'tr_m7_ho_tt_06': [101, 102],
    'tr_m7_ic_maria2': [200, 210],
    'tr_m7_mt_special3': [250],
    'tr_m7_ns_fg_2': [110],
    'tr_m7_ns_fg_3': [110],
    'tr_m7_ns_ic1': [110],
    'tr_m7_ns_ic2': [110],
    'tr_m7_ns_ic3': [110],
    'tr_m7_ns_ic6': [110],
    'tr_m7_ns_il_1': [110, 200],
    'tr_m7_ns_il_2': [220, 300],
    'tr_m7_ns_il_4': [200],
    'tr_m7_ns_il_8': [200],
    'tr_m7_ns_jns_5': [110],
    'tr_m7_ns_jns_6': [110, 120],
    'tr_m7_ns_tg_1': [110, 150],
    'tr_m7_ns_tg_6': [110, 150],
    'tr_m7_ns_tg_8': [150],
    'tr_m7_ns_tt_chavana1': [130],
    'tr_m7_stdelyn_tt_02': [110],
    'tr_m7_wil_trevasatribulations': [110],
    'va_vampcult': [130],
    'va_vamprich': [90],
}

# Journals that only contain failure entries (no successful ending). They must
# never become an Archipelago check: the mod would watch a journal that can
# only report a failure. The generator writes stage 0 / stages [] /
# fail_only: true, and does NOT report them as unknown. The failure stages are
# kept for documentation (they can never complete the quest anyway).
FAIL_ONLY = {
    # Imperial Cult: The Star Wound. Alternate failure journal set by
    # TR_m1_IC6_Wisemomanscript when the wise woman dies; the successful
    # journal is tr_m1_fw_ic6_lore.
    'tr_m1_fw_ic6_lorefail': [300],
    # Finding Jelyn the Sailor. Alternate failure journal: caught in the cargo
    # hold (200) or expelled by Captain Obedur (250).
    'tr_m3_aim_dreugh1b': [200, 250],
}

PAT_QUOTED = re.compile(r'(?<!Get)Journal\s*,?\s*"([^"]+)"\s*,?\s*(\d+)', re.I)
PAT_BARE = re.compile(r'(?<!Get)Journal\s*,?\s*([A-Za-z_][A-Za-z0-9_\-]*)\s*,?\s*(\d+)', re.I)
PAT_COND = re.compile(
    r'GetJournalIndex\s*,?\s*"?([A-Za-z_][A-Za-z0-9_\-]*)"?\s*(==|=|>=|>|<=|<|!=)\s*(\d+)', re.I)

# comparison (tes3conv filter) -> operator
CMP = {'equal': '==', 'notequal': '!=', 'greater': '>', 'greaterequal': '>=',
       'less': '<', 'lessequal': '<='}


class Data:
    def __init__(self):
        self.stages = collections.defaultdict(set)   # stages set by Journal (scripts)
        self.entries = collections.defaultdict(set)  # stages having a journal entry
        self.conds = collections.defaultdict(list)   # (op, value) read as conditions
        self.finishes = collections.defaultdict(set)  # quest_finish, if exported
        self.texts = {}                              # (quest, stage) -> text
        self.schema = {}                             # record type -> keys (tes3conv version)


def collect_stages(esm_jsons, scripts_path=None):
    D = Data()

    def add_text(text):
        if not text:
            return
        for pat in (PAT_QUOTED, PAT_BARE):
            for m in pat.finditer(text):
                D.stages[m.group(1).strip().lower()].add(int(m.group(2)))
        for m in PAT_COND.finditer(text):
            D.conds[m.group(1).strip().lower()].append((m.group(2), int(m.group(3))))

    for esm_json in esm_jsons:
        with open(esm_json, encoding='utf-8') as f:
            data = json.load(f)
        cur_id, cur_journal = None, False
        for rec in data:
            t = rec.get('type')
            if t and t not in D.schema:
                D.schema[t] = sorted(rec.keys())
            if t == 'Dialogue':
                cur_id = (rec.get('id') or '').lower()
                _dt = rec.get('dialogue_type')
                if not _dt:
                    _dt = (rec.get('data') or {}).get('dialogue_type')
                cur_journal = str(_dt or '').lower() == 'journal'
            elif t == 'DialogueInfo':
                # tes3conv versions disagree on field names: the result
                # script (which fires `Journal ...`) may live in
                # script_text / result_text / result, the journal index in
                # disposition / journal_index / quest_index. Scan them all
                # (the NPC line itself never contains a valid Journal call).
                for _k in ('script_text', 'result_text', 'result', 'text'):
                    add_text(rec.get(_k))
                for flt in rec.get('filters') or []:
                    ft = str(flt.get('filter_type') or flt.get('type') or '').lower()
                    if ft != 'journal':
                        continue
                    op = CMP.get(str(flt.get('comparison', '')).lower())
                    val = flt.get('value') or {}
                    val = val.get('data') if isinstance(val, dict) else val
                    qid = str(flt.get('id') or '').strip().lower()
                    if op and isinstance(val, int) and qid:
                        D.conds[qid].append((op, val))
                d = rec.get('data') or {}
                st = None
                for _k in ('disposition', 'journal_index', 'quest_index'):
                    _v = d.get(_k, rec.get(_k))
                    if isinstance(_v, int):
                        st = _v
                        break
                _dt = rec.get('dialogue_type') or d.get('dialogue_type')
                is_j = cur_journal or str(_dt or '').lower() == 'journal'
                if is_j and cur_id and isinstance(st, int):
                    D.entries[cur_id].add(st)
                    D.texts.setdefault((cur_id, st), (rec.get('text') or '').strip())
                    if rec.get('quest_finish') or d.get('quest_finish'):
                        D.finishes[cur_id].add(st)
            elif t == 'Script':
                add_text(rec.get('script_text') or rec.get('text'))

    if scripts_path:
        with open(scripts_path, encoding='utf-8', errors='replace') as f:
            for line in f:
                add_text(line)

    return D


def terminal_stages(D, qid):
    """Journal entry stages (< 150) that no condition consumes."""
    used = set()
    for op, v in D.conds.get(qid, []):
        for s in D.entries.get(qid, ()):
            if op in ('==', '>=', '>') and s == v:
                used.add(s)
            elif op == '!=' and s == v:
                used.add(s)
            elif op == '<' and s < v:
                used.add(s)
            elif op == '<=' and s <= v:
                used.add(s)
    return sorted(s for s in D.entries.get(qid, ()) if 0 < s < 150 and s not in used)


def completion_stages(qid, raw, fin, fail, known_stage=None, entries=()):
    """Returns (main stage, sorted list of all ending stages).

    An empty ending list means NO completion stage could be deduced: the
    quest must be fixed by hand (STAGE_OVERRIDES / STAGES_OVERRIDES) or
    removed from quest_completions.yaml. We never silently write stage 0:
    a journal at index 0 is "quest not started" for the mod, so such a
    check can never fire in-game (dead location)."""
    if qid in STAGES_OVERRIDES:
        found = sorted(set(STAGES_OVERRIDES[qid]))
    else:
        exclude = set(STAGES_EXCLUDE.get(qid, [])) | set(fail)
        # Explicit/known stages are trusted even above the "< 150" vanilla cap
        # (strongholds end at 200/300, TR quests at 500...). Filtering them out
        # here would trigger the fallback below and add a bogus low stage.
        explicit = set(STAGES_EXTRA.get(qid, []))
        if STAGE_OVERRIDES.get(qid) is not None:
            explicit.add(STAGE_OVERRIDES[qid])
        if known_stage:
            explicit.add(known_stage)
        found = sorted(s for s in (set(fin) | explicit)
                        if s not in exclude and (s in explicit or 0 < s < 150))
        # Journal index 0 holds the quest TITLE ("Imperial Cult: Buckmoth
        # Alms"): it is written as soon as the quest starts and never marks
        # progress. It must never be a completion stage.
        if not found:
            # Fallback: highest stage with actual evidence in the ESM.
            # Never 0 (see docstring).
            cands = [s for s in raw if 0 < s < 150 and s not in exclude] \
                or [s for s in entries if 0 < s < 150 and s not in exclude]
            if cands:
                found = [max(cands)]
    main = STAGE_OVERRIDES.get(qid)
    if main is None:
        main = known_stage if known_stage else (found[-1] if found else 0)
    if found and main not in found:
        found = sorted(found + [main])
    return main, found


def snippet(D, qid, st):
    t = D.texts.get((qid, st), '').replace('\n', ' ')
    return (t[:80] + '...') if len(t) > 80 else t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('esm_json', nargs='+')
    ap.add_argument('--scripts', default=None,
                    help='script text dump (optional, improves coverage)')
    ap.add_argument('--qc', default='data/quest_completions.yaml')
    ap.add_argument('--out', default='data/quest_finals.yaml')
    ap.add_argument('--recompute', action='store_true',
                    help='also recomputes stage/stages of quests already present')
    ap.add_argument('--no-auto', action='store_true',
                    help="does not add automatically deduced stages without follow-up")
    ap.add_argument('--fail-on-unknown', action='store_true',
                    help='exit code 1 if quests remain without any completion stage')
    ap.add_argument('--debug', default='',
                    help='comma-separated quest ids: print every ESM evidence found '
                         'for them (entries, finishes, script stages, conditions) '
                         'plus the record schema, then exit')
    args = ap.parse_args()

    D = collect_stages(args.esm_json, args.scripts)
    if args.debug:
        print('record schemas (tes3conv version):')
        for t, keys in sorted(D.schema.items()):
            if t in ('Dialogue', 'DialogueInfo', 'Script'):
                print(f'  {t}: {keys}')
        for qid in [q.strip().lower() for q in args.debug.split(',') if q.strip()]:
            print(f'== {qid}')
            print('  journal entries:', sorted(D.entries.get(qid, ())))
            print('  quest_finish:', sorted(D.finishes.get(qid, ())))
            print('  stages set by scripts:', sorted(D.stages.get(qid, ())))
            print('  conditions (Journal filters):', D.conds.get(qid, ()))
            for (q, s), txt in sorted(D.texts.items()):
                if q == qid:
                    print(f'    entry {s}: {txt[:90]}')
        return
    if not D.finishes:
        print('info: no quest_finish in the JSON, endings deduced from conditions '
              '(Journal / GetJournalIndex filters)')

    existing = {}
    if pathlib.Path(args.out).exists():
        with open(args.out, encoding='utf-8') as f:
            for row in yaml.safe_load(f) or []:
                existing[str(row['quest']).lower()] = row

    with open(args.qc, encoding='utf-8') as f:
        completions = yaml.safe_load(f) or []

    ids = collections.defaultdict(list)
    for q in completions:
        qid = str(q['trigger']['quest']).strip().lower()
        ids[qid].append(q['id'])

    overrides = load_overrides(pathlib.Path(args.qc).parent / 'quest_groups_override.yaml')
    rows, review, unknown = [], [], []
    for qid in sorted(ids):
        if qid in FAIL_ONLY:
            # Failure-only journal: no check may be created (see FAIL_ONLY).
            row = dict(existing.get(qid) or {})
            row['quest'] = qid
            row['stage'] = 0
            row['stages'] = []
            row['fail'] = sorted(set(FAIL_STAGES.get(qid, [])) | set(FAIL_ONLY[qid]))
            row['ids'] = ids[qid]
            row['group'] = classify(qid, overrides)
            row['fail_only'] = True
            row.pop('unknown', None)
            rows.append(row)
            continue

        raw = sorted(s for s in D.stages.get(qid, set()) if s < 150)
        fin = set(s for s in D.finishes.get(qid, set()) if s < 150)
        if not args.no_auto:
            fin |= set(terminal_stages(D, qid))
        fin = sorted(fin)
        entries = sorted(s for s in D.entries.get(qid, ()) if 0 < s < 150)

        if qid in existing:
            row = dict(existing[qid])
            row.pop('fail_only', None)  # only FAIL_ONLY journals are failure-only
            fail = sorted(set(row.get('fail') or []) | set(FAIL_STAGES.get(qid, [])))
            known = None if args.recompute else row.get('stage')
            if known is not None and known <= 0:
                known = None  # legacy stage 0 is not knowledge, re-deduce
            main, found = completion_stages(qid, raw, fin, fail, known, entries)
            old = row.get('stages')
            if args.recompute or not old:
                row['stage'] = main
                row['stages'] = found
            else:
                row['stages'] = sorted(set(old) | set(found))
            # purge: excluded / failure stages already written by a previous
            # run, plus stage 0 (dead location, never fires)
            drop = set(STAGES_EXCLUDE.get(qid, [])) | set(fail) | {0}
            row['stages'] = sorted((set(row['stages']) - drop) | ({main} if main > 0 else set()))
            if qid in STAGES_OVERRIDES:
                row['stages'] = sorted(STAGES_OVERRIDES[qid])
            if main <= 0:
                row['unknown'] = True
                row['stage'] = 0
                row['stages'] = []
                unknown.append(qid)
            else:
                row.pop('unknown', None)
            row['fail'] = fail
            row['ids'] = ids[qid]
            row['group'] = classify(qid, overrides)
            added = [s for s in row['stages'] if s != row['stage']]
            if added and old != row['stages']:
                review.append(f'{qid}: stage={row["stage"]} stages={row["stages"]} (existing)')
                for s in added:
                    review.append(f'    + {s}: {snippet(D, qid, s)}')
            rows.append(row)
            continue

        fail = FAIL_STAGES.get(qid, [])
        main, found = completion_stages(qid, raw, fin, fail, None, entries)
        row = {
            'quest': qid,
            'stage': main,
            'stages': found,
            'fail': fail,
            'ids': ids[qid],
            'group': classify(qid, overrides),
        }
        if main <= 0:
            row['unknown'] = True
            row['stage'] = 0
            row['stages'] = []
            unknown.append(qid)
        rows.append(row)
        if main <= 0:
            review.append(f'{qid}: !! NO ENDING FOUND (unknown) raw={raw} entries={entries}  <-- fix by hand or remove')
        else:
            flag = '' if len(found) <= 1 else '  <-- several possible endings, check'
            review.append(f'{qid}: stage={main} stages={found} raw={raw}{flag}')
            for s in found:
                if s != main:
                    review.append(f'    + {s}: {snippet(D, qid, s)}')

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        yaml.safe_dump(rows, f, sort_keys=False, allow_unicode=True)
    multi = sum(1 for r in rows if len(r['stages']) > 1)
    print(f'quest finals: {len(rows)} entries -> {out} ({multi} with several endings)')
    if unknown:
        banner = [f'!! {len(unknown)} QUESTS WITHOUT ANY COMPLETION STAGE (unknown: true):']
        banner += [f'    {q}' for q in unknown]
        banner.append('Fix them by hand (STAGE_OVERRIDES / STAGES_OVERRIDES) or remove '
                      'them from quest_completions.yaml.')
        print('\n'.join(banner))
    rp = out.with_name('quest_review.txt')
    if review or unknown:
        head = []
        if unknown:
            head = [f'!! {len(unknown)} QUESTS WITHOUT ANY COMPLETION STAGE:']
            head += [f'    {q}' for q in unknown]
            head.append('')
        rp.write_text('\n'.join(head + review) + '\n', encoding='utf-8')
        print(f'to check in {rp}')
    elif rp.exists():
        rp.unlink()
    if args.fail_on_unknown and unknown:
        sys.exit(1)


if __name__ == '__main__':
    main()
