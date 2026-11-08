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
}

# BEGIN UESP OVERRIDES (tools/scrape_uesp_finals.py)
# Only journals that were not overridden by hand and have no failure-looking
# "Finishes quest" stage. Delete a line here and move it up to keep a manual value.
STAGES_OVERRIDES.update({
    'a1_1_findspymaster': [14, 18, 20, 22],
    'a1_2_antabolisinformant': [20, 25],
    'a1_4_muzgobinformant': [25, 30, 55],
    'a1_6_addhiranirrinformant': [45, 60],
    'a1_dreams': [1, 10, 15, 50],
    'a1_v_vivecinformants': [50, 55],
    'a2_4_milogone': [1, 5, 50, 100],
    'b5_redoranhort': [70],
    'b7_telvannihort': [70],
    'da_mephala': [57, 60],
    'eb_clients': [40, 50],
    'eb_express': [30, 50],
    'eb_shipment': [30, 40, 50],
    'eb_tradespy': [40, 50],
    'fg_vas': [100, 105],
    'hh_disguisedarmor': [100, 150, 200],
    'hh_ebonydelivery': [100, 110],
    'hh_eggmine': [100, 210],
    'hh_indesp1': [100, 200],
    'hh_indesp4': [100, 110],
    'hh_retaliation': [100, 110, 120, 150, 200],
    'hh_stronghold': [100, 200, 300],
    'hh_wincamonna': [100, 110],
    'hh_winsaryoni': [100],
    'hr_clearsarethi': [100, 110],
    'hr_findtharen': [100, 110],
    'hr_foundershelm': [100, 200],
    'hr_guardguarherds': [100, 110],
    'hr_honorchallenge': [100, 200],
    'hr_madmilk': [100, 110],
    'hr_stronghold': [100, 200, 300],
    'ht_dwemerlaw': [100],
    'ht_slaverebellion': [100, 110],
    'ht_stronghold': [100, 200, 300],
    'ic10_buckmoth_alms': [5, 50, 60],
    'ic11_shirt': [1, 50],
    'ic13_rich': [45, 50],
    'ic18_silver_staff': [1, 50, 55],
    'ic19_restless_spirit': [1, 5, 50],
    'ic26_amanin': [50, 60],
    'ic28_urjorad': [50, 55],
    'ic9_argonian_alms': [1, 30, 50, 60],
    'il_protectentius': [100, 110],
    'mg_apprentice': [100, 200],
    'mg_excavation': [100, 110],
    'mg_spycatch': [100, 110],
    'mg_stopcompetition': [100, 110],
    'ms_hannat': [70, 110],
    'mt_writbaladas': [100, 110],
    'mt_writbelvayn': [100, 110],
    'mt_writbemis': [100, 110],
    'mt_writbero': [100, 110],
    'mt_writbrilnosu': [100, 110],
    'mt_writgalasa': [100, 110],
    'mt_writguril': [100, 110],
    'mt_writmavon': [100, 110],
    'mt_writnavil': [100, 110],
    'mt_writsadus': [100, 110],
    'mt_writsaren': [100, 110],
    'mt_writtherana': [100, 110],
    'mt_writvarro': [100, 110],
    'mt_writvendu': [100, 110],
    'mt_writyasalmibaal': [100, 110],
    'mv_runawayslave': [36, 100, 105, 120, 130, 140],
    'mv_skoomacorpse': [20, 30],
    'mv_slavemule': [108, 109, 110, 113, 115],
    'mv_thieftrader': [30, 35, 100, 105],
    'mv_traderlate': [40, 100],
    'tg_dartsjudgement': [100, 105],
    'town_ald_bevene': [3, 5, 10],
    'town_ald_bivale': [3, 5, 10],
    'town_ald_daynes': [3, 5, 10],
    'town_ald_llethri': [3, 5, 10],
    'town_ald_tiras': [3, 5, 10],
    'town_balmora': [30, 35],
    'town_sadrith': [50, 55, 60, 65, 70, 75, 80, 85, 90, 100, 105, 110],
    'tr_m0_hh_atranoran': [100, 110, 120],
    'tr_m0_tt_anoforondas': [100],
    'tr_m1_as_dwemer': [50, 60, 65],
    'tr_m1_bah_guarmeat': [100, 110],
    'tr_m1_eec_lora2': [30, 35, 40],
    'tr_m1_eec_zaren': [60, 65, 67, 68, 70],
    'tr_m1_fg_burglary': [10, 20, 100, 101, 105],
    'tr_m1_fg_codaliastalker': [100, 105, 110],
    'tr_m1_fg_egg': [100, 110, 120],
    'tr_m1_fg_findorc': [100, 105, 110],
    'tr_m1_fg_manrizache': [90, 100],
    'tr_m1_fg_protection': [90],
    'tr_m1_fw_gummidge': [100, 150],
    'tr_m1_fw_ic1_guar': [100, 200, 201],
    'tr_m1_fw_ic2_taxes': [100, 200, 201, 202],
    'tr_m1_fw_ic5_sword': [100, 200],
    'tr_m1_fw_mg07': [100, 300],
    'tr_m1_fw_mg08': [100, 150],
    'tr_m1_fw_sugarandspice': [100, 200],
    'tr_m1_go_2_ito': [100, 101],
    'tr_m1_go_4': [100, 101, 102, 110],
    'tr_m1_gs_mq_3': [20, 25, 30],
    'tr_m1_ht_el1': [100, 110],
    'tr_m1_ht_fa2': [100, 101, 200],
    'tr_m1_ht_nu1': [100, 110],
    'tr_m1_ht_va1': [100, 101],
    'tr_m1_il_finepoor': [100, 110],
    'tr_m1_il_pahunsabi': [100, 105, 110, 120],
    'tr_m1_il_skoomaship': [100, 110, 120],
    'tr_m1_il_sweetdeal': [100, 110, 120],
    'tr_m1_niv_crack': [100, 200],
    'tr_m1_pt_translation': [100],
    'tr_m1_rr_drunkard': [70, 100],
    'tr_m1_rr_mq_10': [1000],
    'tr_m1_rr_slander': [90, 100, 110, 120],
    'tr_m1_sp_qforaadri': [100, 110],
    'tr_m1_to_acoldharbourkeelhaul': [85, 100, 110, 120],
    'tr_m1_to_killorbekilled': [70, 80, 90, 100],
    'tr_m1_wil_drink': [10, 20, 30, 40],
    'tr_m1_wil_woebringer': [100, 110],
    'tr_m2_ak_gem': [100, 101],
    'tr_m2_ak_nameless': [120, 140, 150],
    'tr_m2_ao_shackledlove': [40, 60],
    'tr_m2_fg_amiro1': [100, 170],
    'tr_m2_fg_amiro2': [100, 110],
    'tr_m2_fg_hartise_joran': [100, 110],
    'tr_m2_fg_irano1': [100, 110, 120],
    'tr_m2_fg_irano4': [90, 93, 95, 100],
    'tr_m2_he_tg1': [100, 110, 500, 510],
    'tr_m2_he_tg3': [100, 200, 510],
    'tr_m2_he_tg4': [100, 510],
    'tr_m2_ias_belongmuseum': [100, 110, 200],
    'tr_m2_il_wantedwizard': [60, 70],
    'tr_m2_mg_areanne2': [90, 100, 110, 120],
    'tr_m2_mg_francine3': [50, 60, 90, 100],
    'tr_m2_mg_polodie2': [100, 120, 140, 160],
    'tr_m2_mg_ranosa2': [100, 101, 102, 120, 121, 122],
    'tr_m2_nm_walker': [30, 60],
    'tr_m2_telon_folkmedicine': [100, 110],
    'tr_m2_tgi_complicatcomp': [65, 70, 75],
    'tr_m2_tmo_gonetoground': [25, 50, 55, 56, 57, 58, 60],
    'tr_m2_tmo_qualitytime': [15, 35, 40],
    'tr_m2_vp_jealousshopkeeper': [47, 50],
    'tr_m2_wil_pestilent': [40, 50, 51, 52],
    'tr_m2_wil_ruinofstrife': [50, 55, 60, 65, 80, 85],
    'tr_m3_aim_dreugh1': [100, 110],
    'tr_m3_at_mg02': [100, 110],
    'tr_m3_at_mg03': [100, 110, 120],
    'tr_m3_at_mg05': [100, 110],
    'tr_m3_at_mg06': [100, 110],
    'tr_m3_at_ratfriend': [100, 110],
    'tr_m3_do_cultists': [100, 101, 102],
    'tr_m3_eec_cano1': [200],
    'tr_m3_eec_cano4': [200],
    'tr_m3_eec_cano5z': [200],
    'tr_m3_eec_cano6': [205],
    'tr_m3_eec_counterfeit': [30, 40, 45],
    'tr_m3_eec_curse': [30, 40, 50, 51, 52, 55],
    'tr_m3_eec_ebony': [70, 71, 72, 82],
    'tr_m3_fg_oe_cursing': [100, 101],
    'tr_m3_go_guard1': [65, 70, 80],
    'tr_m3_hi_beroth1': [100, 150],
    'tr_m3_hi_gorne3': [100, 110],
    'tr_m3_hi_gorne4': [100, 110],
    'tr_m3_hi_gorne5': [100, 110],
    'tr_m3_hi_ilvi1': [100, 110],
    'tr_m3_hi_nanaav6': [100, 110],
    'tr_m3_hi_nanaav7': [100, 110],
    'tr_m3_hi_roadyr5': [200, 300, 500],
    'tr_m3_hi_roadyr6': [100, 200],
    'tr_m3_hi_sandil1': [100, 200],
    'tr_m3_il_justice': [100, 150, 200],
    'tr_m3_il_testimony': [100, 150],
    'tr_m3_il_work': [100, 150],
    'tr_m3_kha_flowersdark': [100, 101, 102],
    'tr_m3_mg_oe_q4': [100, 110],
    'tr_m3_mg_oe_q6': [120, 150, 160],
    'tr_m3_mg_oe_q8': [140, 150, 160],
    'tr_m3_mt_arin': [100, 110],
    'tr_m3_mt_delynasilvas': [100, 110],
    'tr_m3_mt_dileru': [100, 110],
    'tr_m3_mt_ervysa': [100, 110],
    'tr_m3_mt_felrar': [100, 110],
    'tr_m3_mt_forvayn': [100, 110],
    'tr_m3_mt_indriri': [100, 110],
    'tr_m3_mt_ughash': [100, 110],
    'tr_m3_mt_ulyn': [100, 110],
    'tr_m3_mt_varru': [100, 110],
    'tr_m3_nnv_cheat': [30, 100, 110],
    'tr_m3_oe_freedom': [90, 100, 110, 115, 120],
    'tr_m3_oe_hlarsisvalju-deekus': [100, 200, 300],
    'tr_m3_oe_ic_q7': [100, 200],
    'tr_m3_oe_smallcomplaint': [10, 15, 30],
    'tr_m3_oe_stendarrtowerhaunting': [110, 120, 125],
    'tr_m3_ord_doc4': [100, 101, 102, 103],
    'tr_m3_ord_war3': [100, 200, 300],
    'tr_m3_ord_watch3': [100, 110],
    'tr_m3_oth_alvana': [100, 110],
    'tr_m3_oth_tt_2': [100, 110, 200],
    'tr_m3_oth_tt_4': [100, 200, 210],
    'tr_m3_oth_tt_6': [100, 150, 200],
    'tr_m3_rd_hiseyes': [100, 120, 200],
    'tr_m3_ss_corroded': [100, 110, 120],
    'tr_m3_tg_at_q1': [100, 110],
    'tr_m3_tg_at_q3': [100, 110],
    'tr_m3_tg_at_q6': [150, 200],
    'tr_m3_tg_fentus3': [100, 120, 200],
    'tr_m3_tg_fentus4': [100, 200],
    'tr_m3_tg_moranie1': [120, 250, 300],
    'tr_m3_tg_moranie2': [105, 110, 200],
    'tr_m3_tg_moranie3': [115, 120, 250],
    'tr_m3_tou_tricksterknight': [100, 110],
    'tr_m3_tt_dar_1': [100, 110],
    'tr_m3_tt_dar_4': [100],
    'tr_m3_tt_facestealer': [60, 100],
    'tr_m3_tt_ghosttrick': [100, 200],
    'tr_m3_tt_illene3': [130, 140, 150],
    'tr_m3_tt_lloris1': [200, 225, 250, 300],
    'tr_m3_tt_lloris2': [175],
    'tr_m3_tt_lloris4': [100, 150, 200],
    'tr_m3_tt_lloris5': [200, 250, 300],
    'tr_m3_tt_rip': [210, 220, 300],
    'tr_m3_tt_ruinouskeep': [70],
    'tr_m3_tt_seeyou': [40, 60, 90, 100],
    'tr_m3_tt_speaker': [11, 30, 32, 100, 150, 200],
    'tr_m3_vf_shrine': [100, 101],
    'tr_m3_vh_bardstale': [100, 101],
    'tr_m3_vh_temple': [100, 101, 110],
    'tr_m3_wil_deadinthewater': [100, 200],
    'tr_m3_wil_foeburner': [50, 100],
    'tr_m3_wil_haliwaran': [100, 200, 300],
    'tr_m4_and_credibility': [35, 40, 45, 50, 60, 70],
    'tr_m4_and_missingmerchant': [100, 101, 102, 103, 104],
    'tr_m4_and_tmm_ash': [6, 7, 8, 20],
    'tr_m4_arv_dravil': [100, 200],
    'tr_m4_arv_metamorphosis': [70, 90, 100],
    'tr_m4_bd_lost_in_transit': [90, 91],
    'tr_m4_bd_redorandebt': [37, 40, 56, 60, 61, 63, 65, 70, 80],
    'tr_m4_fg_cliffracer': [200],
    'tr_m4_fg_darvas': [100, 105, 250, 275, 300, 400],
    'tr_m4_fg_hjaskar': [25, 26, 33, 35, 45, 46, 50, 55],
    'tr_m4_fg_map': [200],
    'tr_m4_fg_ushukur2': [200, 250],
    'tr_m4_fg_ushukur3': [125, 150, 200],
    'tr_m4_fg_ushukur4': [300],
    'tr_m4_fg_ushukur5': [550],
    'tr_m4_hh_and_docksquests': [100, 110, 111],
    'tr_m4_hh_and_employment': [100, 110, 120],
    'tr_m4_hh_and_greef': [100, 110],
    'tr_m4_hh_and_hearing': [100, 105, 110],
    'tr_m4_hh_and_omaynisinn': [85, 100, 101, 110],
    'tr_m4_hh_and_ship': [11, 100, 110, 170, 200],
    'tr_m4_hh_ulvo1': [100, 120],
    'tr_m4_hh_ulvo4': [100, 105, 110, 120],
    'tr_m4_il_agent': [100, 101, 110, 200, 201],
    'tr_m4_il_grudge': [5, 100, 105, 110, 120, 130],
    'tr_m4_il_kathletter': [100, 120],
    'tr_m4_mg_ando_2': [100, 110, 150, 160],
    'tr_m4_mg_ando_4': [100, 110],
    'tr_m4_mg_ando_8': [95, 100, 105],
    'tr_m4_mn_assassin': [30, 40, 50],
    'tr_m4_mn_shorted': [100, 110],
    'tr_m4_mt_almse': [100, 110],
    'tr_m4_mt_dransa': [100, 110],
    'tr_m4_mt_ilmeni': [100, 110],
    'tr_m4_mt_jebyn': [100, 110],
    'tr_m4_mt_llirala': [100, 110],
    'tr_m4_mt_nadrasarvel': [100, 110],
    'tr_m4_mt_omayn': [100, 110],
    'tr_m4_mt_serali': [100, 110],
    'tr_m4_mt_sp_gulmon': [100, 110, 111, 112, 113],
    'tr_m4_mt_tolmse': [100, 110],
    'tr_m4_ob_ancestral_guidance': [100, 200],
    'tr_m4_t_euphoria': [115, 130, 145, 150],
    'tr_m4_tg_marug1': [100, 150, 200],
    'tr_m4_tg_shei2': [150],
    'tr_m4_tg_shei5': [20, 50, 300, 325, 350],
    'tr_m4_tg_shei6': [200, 225, 250, 275, 300],
    'tr_m4_tg_tattara1': [200, 300],
    'tr_m4_tg_threeeyes1': [125, 150, 175, 200, 250, 300, 400],
    'tr_m4_tg_threeeyes2': [10, 20, 200, 250],
    'tr_m4_tj_mt_1': [110, 200],
    'tr_m4_tt_forgiveness': [100, 101, 102, 103],
    'tr_m4_tt_lastwillandtestament': [200],
    'tr_m4_tt_staralor_q2': [100, 110, 200],
    'tr_m4_tt_staralor_q3': [100, 110],
    'tr_m4_va_destroybaluath': [200],
    'tr_m4_va_invasion': [180, 200],
    'tr_m4_va_ironandblood': [90, 100, 200, 210, 215, 220],
    'tr_m4_va_namira': [100, 225],
    'tr_m4_va_ovamphunt': [200],
    'tr_m4_va_proper': [200],
    'tr_m4_va_propylon': [200],
    'tr_m4_va_termination': [5, 100, 200, 250],
    'tr_m4_wil_ahnaissa': [100, 101, 102, 103],
    'tr_m4_wil_argonianbandits': [20, 30, 40, 50, 75, 100],
    'tr_m4_wil_banditduo': [100, 200],
    'tr_m4_wil_belbetu1': [40, 70, 110],
    'tr_m4_wil_belbetu2': [100, 120],
    'tr_m4_wil_buyingrope': [30, 40, 50],
    'tr_m4_wil_hautharmokill': [200],
    'tr_m4_wil_joscus': [100, 200],
    'tr_m4_wil_oranescaped': [40, 105, 110, 120],
    'tr_m4_wil_oranmissingbrother': [5, 30, 40],
    'tr_m4_wil_strayguars': [10, 100],
    'tr_m4_wil_troupe_trouble': [40, 60, 130],
    'tr_m7_ai_jns_3': [100, 200],
    'tr_m7_ai_tt_q1': [100, 110],
    'tr_m7_ai_tt_q2': [100, 110, 120],
    'tr_m7_ai_tt_q4': [100, 110, 120],
    'tr_m7_ai_tt_q5': [100, 110, 120, 130, 140],
    'tr_m7_ai_tt_q6': [100, 110, 200, 210, 220],
    'tr_m7_eec_narsis2': [100, 110, 120],
    'tr_m7_eec_narsis4': [100, 110],
    'tr_m7_fg_hl_q4': [100, 200],
    'tr_m7_fg_hl_q6': [100, 200],
    'tr_m7_fg_narsismaster_consulate': [100, 200],
    'tr_m7_hh_alvynu_1': [100, 200, 300],
    'tr_m7_hh_alvynu_2': [100, 200],
    'tr_m7_hh_alvynu_4': [100, 101, 102],
    'tr_m7_hh_gm_1': [200, 250],
    'tr_m7_hh_gm_2z': [100, 200],
    'tr_m7_hh_gm_4b': [60, 250],
    'tr_m7_hh_gm_4c': [60, 70],
    'tr_m7_hh_gm_5': [100, 250],
    'tr_m7_hh_gm_7': [40, 50],
    'tr_m7_hh_raran1': [100, 200],
    'tr_m7_hh_raran2': [40, 60, 80, 100],
    'tr_m7_hh_sathis3': [100, 125, 150, 200, 250],
    'tr_m7_hh_sathis4': [200, 250],
    'tr_m7_hh_sathis6': [100, 125, 150, 200],
    'tr_m7_hh_seventhfamily_1': [100, 200],
    'tr_m7_hh_seventhfamily_2': [100, 110],
    'tr_m7_hh_sixthfamily_1': [100, 110],
    'tr_m7_hh_vedas1': [100, 125],
    'tr_m7_hl_affairsheart': [310, 320, 330, 500],
    'tr_m7_ho_houseforsale': [100, 200],
    'tr_m7_ho_tt_02': [100, 110, 200, 201],
    'tr_m7_ho_tt_03': [100, 110, 120],
    'tr_m7_ho_tt_04': [100, 111, 121, 131, 200, 210, 211, 220, 221, 300, 301],
    'tr_m7_hr_aldiuval_q5': [100, 125],
    'tr_m7_ic_maria2': [100, 200, 210],
    'tr_m7_ic_maria6': [100, 200],
    'tr_m7_ic_maria7': [100, 200],
    'tr_m7_ic_maria8': [100, 200, 300],
    'tr_m7_il_hl_q2': [100, 120, 125],
    'tr_m7_il_hl_q3': [100, 110],
    'tr_m7_il_hl_q4': [100, 120],
    'tr_m7_insearchofsnacks': [100, 200],
    'tr_m7_mt_hagar': [100, 110],
    'tr_m7_mt_hlevis': [100, 110],
    'tr_m7_mt_ibarmas': [100, 110],
    'tr_m7_mt_llevas': [100, 110],
    'tr_m7_mt_milena': [100, 110],
    'tr_m7_mt_nelyos': [100, 110],
    'tr_m7_mt_peleri': [100, 110],
    'tr_m7_mt_selvura': [100, 110],
    'tr_m7_mt_special1': [200],
    'tr_m7_mt_special3': [150, 250],
    'tr_m7_mt_special4': [100],
    'tr_m7_mt_turesa': [100, 110],
    'tr_m7_mt_ulvys': [100, 110],
    'tr_m7_ns_arena_01': [100, 105, 120],
    'tr_m7_ns_arena_02': [100, 105, 120],
    'tr_m7_ns_arena_04': [100, 120],
    'tr_m7_ns_arena_05': [100, 105, 120],
    'tr_m7_ns_arena_07': [100, 105, 120],
    'tr_m7_ns_arena_08': [100, 105, 120],
    'tr_m7_ns_arena_09': [99, 120],
    'tr_m7_ns_arena_10': [100, 105, 120],
    'tr_m7_ns_fg_1': [100, 110],
    'tr_m7_ns_fg_5': [100, 110],
    'tr_m7_ns_fg_6': [100, 110],
    'tr_m7_ns_fg_8': [100, 110],
    'tr_m7_ns_hh_angryletter': [100, 110],
    'tr_m7_ns_hh_rentfarming': [100, 110],
    'tr_m7_ns_ic1': [100, 110],
    'tr_m7_ns_ic2': [100, 110],
    'tr_m7_ns_ic3': [100, 110],
    'tr_m7_ns_ic4': [100, 110, 120, 130],
    'tr_m7_ns_ic5': [110, 120, 130],
    'tr_m7_ns_ic8': [100, 110],
    'tr_m7_ns_il_2': [100, 220, 300],
    'tr_m7_ns_il_3': [100, 200],
    'tr_m7_ns_il_4': [100, 200],
    'tr_m7_ns_il_5': [100, 110],
    'tr_m7_ns_il_8': [100, 200],
    'tr_m7_ns_irwaen': [100, 110],
    'tr_m7_ns_jns_2': [100, 101],
    'tr_m7_ns_jns_3': [100, 101],
    'tr_m7_ns_jns_4': [100, 200],
    'tr_m7_ns_jns_6': [100, 110, 120],
    'tr_m7_ns_mg_arch01': [100, 110],
    'tr_m7_ns_mg_arch03': [100, 105, 110],
    'tr_m7_ns_movinghouse': [100, 101, 102, 110],
    'tr_m7_ns_shocktherapy': [100, 110],
    'tr_m7_ns_tt_chavana3a': [100, 110, 120],
    'tr_m7_ns_tt_chavana4': [100, 110],
    'tr_m7_ns_tt_orvayn3': [100, 110],
    'tr_m7_ns_tt_orvayn5': [100, 110],
    'tr_m7_oth_brotherslove': [100, 110, 120],
    'tr_m7_oth_bugtracker': [95, 100, 110, 120, 150],
    'tr_m7_oth_changinghouses': [26, 30],
    'tr_m7_oth_hh_2': [100, 110, 120],
    'tr_m7_oth_hh_4': [100, 110, 120],
    'tr_m7_oth_hh_5': [100, 110, 120],
    'tr_m7_oth_hh_7': [100, 120, 140, 150],
    'tr_m7_oth_mg_1': [100, 110],
    'tr_m7_shin_renderingassistance': [100, 110, 120],
    'tr_m7_shisha_hh_2': [100, 150, 200],
    'tr_m7_shisha_il_1': [100, 110, 120],
    'tr_m7_shisha_il_2': [100, 110],
    'tr_m7_shisha_il_3': [100, 110, 120, 121],
    'tr_m7_wil_dralnasvirian': [100, 110, 200, 210],
    'tr_m7_wil_lurkerinthemangrove': [50, 100],
    'tr_m7_wil_nymph': [50, 200, 210],
    'tr_m7_wil_onrocks': [50, 100, 110, 120],
    'tt_maargan': [100],
    'va_vampchild': [120, 130],
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
    'mv_abusedhealer': [60], 'mv_tradermissed': [110], 'mv_victimromance': [110],
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
    # Foul Murder: Simine (190) or Alvu (195) dies; 199 is the resulting
    # softlock marker. None of them may validate the main quest.
    'tr_necmq_3': [190, 195, 199],
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
        found = set(fin) | set(STAGES_EXTRA.get(qid, []))
        if STAGE_OVERRIDES.get(qid) is not None:
            found.add(STAGE_OVERRIDES[qid])
        if known_stage:
            found.add(known_stage)
        found = sorted(s for s in found
                        if s not in exclude and 0 < s < 150)
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
