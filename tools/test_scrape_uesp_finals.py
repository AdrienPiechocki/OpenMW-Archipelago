#!/usr/bin/env python3
"""Test for tools/scrape_uesp_finals.py (no network: synthetic stage tables).

From the repository root:
    python3 tools/test_scrape_uesp_finals.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import scrape_uesp_finals as uesp  # noqa: E402
import gen_quest_finals as gqf  # noqa: E402

fails = 0


def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f'FAIL {name}: got {got!r}, want {want!r}')
    else:
        print(f'ok   {name}')


def analyse(quests, now):
    cur = {'STAGES_OVERRIDES': {}, 'FAIL_STAGES': {}}
    return uesp.analyse(quests, cur, now, None)


# IC17_Witch: UESP finishes at 50 ("made sure she was dead" is a success); the
# refusal is the separate IC17_Witch_not journal, stage 1.
witch = {
    'ic17_witch': {
        1: (False, 'Kaye has asked me to hunt the witch.'),
        5: (False, "I told Kaye I wasn't going to hunt the witch."),
        50: (True, 'I found the witch and made sure she was dead.'),
    },
    'ic17_witch_not': {
        1: (True, "I told Kaye I wasn't going to hunt the witch."),
    },
}
diffs, _, matches, targets = analyse(witch, {'ic17_witch': [50], 'ic17_witch_not': [1]})
check('ic17_witch already matches', [d['quest'] for d in diffs], [])
check('both journals match', matches, 2)
check('matched journals stay in the complete block', targets,
      {'ic17_witch': [50], 'ic17_witch_not': [1]})

# A "_not" journal is a failure completion, never a FAIL_STAGE suggestion.
not_only = {'ic15_missing_not': {1: (True, 'I told Kaye I would not be able to retrieve the bowl.')}}
diffs, _, _, _ = analyse(not_only, {'ic15_missing_not': [1]})
check('_not journal is not a failure', [d['quest'] for d in diffs], [])

# A large gap between finishing stages must not hold the update back.
diffs = [{
    'quest': 'ic17_witch', 'now': [50], 'overridden': False, 'known_fail': [],
    'uesp': [1, 50], 'success': [1, 50], 'suspects': [], 'texts': {},
}]
check('large stage gap is applied', uesp.uesp_updates(diffs), {'ic17_witch': [1, 50]})

# A "_not" journal that differs from the current value is still updated.
diffs = [{
    'quest': 'ic12_dinner_not', 'now': [1], 'overridden': False, 'known_fail': [],
    'uesp': [5], 'success': [5], 'suspects': [], 'texts': {},
}]
check('_not journal stages are applied', uesp.uesp_updates(diffs), {'ic12_dinner_not': [5]})

# The complete block keeps journals that already match (so a re-apply cannot
# wipe them) and still skips hand-written STAGES_OVERRIDES.
full = {'a_quest': {1: (True, 'done')}, 'b_quest': {5: (True, 'done')}}
cur = {'STAGES_OVERRIDES': {'b_quest': [5]}, 'FAIL_STAGES': {}}
diffs, _, _, targets = uesp.analyse(full, cur, {'a_quest': [1], 'b_quest': [5]}, None)
check('complete block keeps matches and skips manual overrides',
      uesp.uesp_updates(diffs, targets), {'a_quest': [1]})

# Known failure stages are subtracted from UESP's "Finishes quest" list, even
# when FAIL_HINTS does not recognise the text. Dreugh1: stage 110 (the priest
# is jailed after reporting the body) is a failure, the success is stage 100.
dreugh = {'tr_m3_aim_dreugh1': {
    100: (True, 'Ivon Seloth was glad to hear that I believe he is innocent.'),
    110: (True, 'I told a guard about the body. The guard told me the priest is going to jail.'),
}}
cur = {'STAGES_OVERRIDES': {}, 'FAIL_STAGES': {'tr_m3_aim_dreugh1': [110]}}
diffs, _, _, targets = uesp.analyse(dreugh, cur, {'tr_m3_aim_dreugh1': [100, 110]}, None)
check('known failure stage is subtracted', targets, {'tr_m3_aim_dreugh1': [100]})
check('journal with a known failure stage differs', [d['quest'] for d in diffs],
      ['tr_m3_aim_dreugh1'])
# Once the current value is the success list, it matches and stays in the block.
diffs, _, matches, targets = uesp.analyse(dreugh, cur, {'tr_m3_aim_dreugh1': [100]}, None)
check('success-only value matches UESP minus failures', [d['quest'] for d in diffs], [])
check('success-only value stays in the block', targets, {'tr_m3_aim_dreugh1': [100]})

# Refusals that the old FAIL_HINTS missed.
check('refusal: decided not to',
      bool(uesp.FAIL_HINTS.search('I have decided not to help Lucan deliver his shipment.')), True)
check('refusal: no time to',
      bool(uesp.FAIL_HINTS.search('I have no time to help Lucan, guildmate or not.')), True)
check('refusal: decided not to attempt / no time for',
      bool(uesp.FAIL_HINTS.search("I've decided not to attempt to find Nelos. I have no time for this.")), True)
check('success text is not a refusal',
      bool(uesp.FAIL_HINTS.search('I delivered the shipment to Yak gro-Skandar.')), False)

# Fargoth's Hiding Place: stage 30 is the refusal and lookoutScript treats it as
# terminal. It must be a failure, never a completion.
check('ms_lookout refusal stage is a failure', gqf.FAIL_STAGES.get('ms_lookout'), [30])
check('ms_lookout only succeeds at stage 100', gqf.STAGES_OVERRIDES.get('ms_lookout'), [100])
main, stages = gqf.completion_stages('ms_lookout', [10, 20, 30, 40, 50, 100],
                                     [30, 40, 50, 100], [30], None, [10, 20, 30, 40, 50, 100])
check('ms_lookout completion excludes the refusal stage', stages, [100])
check('ms_lookout main stage is 100', main, 100)

if fails:
    print(f'{fails} failure(s)')
    sys.exit(1)
print('all UESP scraper tests passed')
