import copy
import unittest
from test_workflow import complete
from test_research import source
from researchlib.journals import schedule_check, recheck_journals
from researchlib.output import validate, markdown


def scheduled():
    s = complete(); s['profile']['timezone'] = 'Asia/Seoul'
    s['candidates'][0]['submission_plan'] = {'status': 'estimated', 'experiments_complete': '2026-12-01', 'timezone': 'Asia/Seoul', 'writing_days': 7, 'assumptions': 'TEST includes internal review and formatting', 'source': source()}
    s['journals'] = [{'id': 'TEST-V1', 'candidate_id': 'TEST-C1', 'name': 'TEST Conference', 'category': 'conference', 'edition': '2027', 'track': 'Main', 'round': 'R1',
        'schedule': {'status': 'verified', 'value': 'TEST R1 schedule', 'mode': 'fixed', 'source': {**source(), 'url': 'https://example.invalid/TEST-CFP', 'official': True, 'checked_at': '2026-11-12', 'venue_name': 'TEST Conference', 'edition': '2027', 'track': 'Main', 'round': 'R1'},
                     'deadlines': [{'id': 'abstract', 'kind': 'abstract', 'at': '2026-12-05T23:59:59-12:00', 'timezone': 'Etc/GMT+12'},
                                   {'id': 'paper', 'kind': 'submission', 'at': '2026-12-10T23:59:59-12:00', 'timezone': 'Etc/GMT+12', 'requires': ['abstract']}]}}]
    return s


class SubmissionScheduleTests(unittest.TestCase):
    def test_readiness_includes_writing_and_timezone(self):
        s = scheduled(); venue = s['journals'][0]
        r = schedule_check(s, venue, '2026-11-18T12:00:00+09:00')
        self.assertTrue(r['ready_at'].startswith('2026-12-08T23:59:59'))
        self.assertEqual(r['deadlines'][1]['readiness'], 'pending_prerequisite')
        s['candidates'][0]['submission_plan']['writing_days'] = 15
        self.assertEqual(schedule_check(s, venue, '2026-11-18')['deadlines'][1]['readiness'], 'insufficient_preparation_time')
        self.assertEqual(validate(s, final=True), [])
        self.assertIn('insufficient_preparation_time', markdown(s))
        # The same deadline is Dec 11 in Seoul and Dec 10 in AoE.
        self.assertEqual(schedule_check(s, venue, '2026-12-11')['deadlines'][1]['timing'], 'deadline_day_needs_recheck')
        self.assertEqual(schedule_check(s, venue, '2026-12-11T20:59:59+09:00')['deadlines'][1]['timing'], 'expired')
        self.assertEqual(schedule_check(s, venue, '2026-12-11T20:59:58+09:00')['deadlines'][1]['timing'], 'upcoming')

    def test_expired_required_steps_and_completed_evidence(self):
        s = scheduled(); v = s['journals'][0]
        plan = s['candidates'][0]['submission_plan']
        self.assertEqual(schedule_check(s, v, '2026-12-08')['deadlines'][1]['readiness'], 'blocked_prerequisite')
        plan['completed_steps'] = [{'venue_id': v['id'], 'deadline_id': 'abstract', 'completed_at': '2026-12-05T12:00:00+00:00', 'evidence': source()}]
        r = schedule_check(s, v, '2026-12-08')
        self.assertEqual(r['deadlines'][1]['readiness'], 'ready_in_time')
        plan['completed_steps'][0]['completed_at'] = '2026-12-07T12:00:00+00:00'
        self.assertEqual(schedule_check(s, v, '2026-12-08')['deadlines'][1]['readiness'], 'blocked_prerequisite')
        plan['completed_steps'][0]['evidence'] = None
        self.assertTrue(validate(s))

    def test_round_mismatch_legacy_rolling_unknown(self):
        s = scheduled(); v = s['journals'][0]
        v['round'] = 'R2'
        self.assertEqual(schedule_check(s, v, '2026-11-18')['status'], 'unverified')
        v['round'] = 'R1'; del v['schedule']['mode']
        self.assertEqual(schedule_check(s, v, '2026-11-18')['status'], 'needs_structure')
        self.assertEqual(validate(s), [])
        v['category'] = 'journal'; v['issn'] = 'TEST-ISSN'
        v['schedule']['source'].update(journal_name=v['name'], issn=v['issn'])
        v['schedule'].update(mode='rolling', deadlines=[])
        self.assertEqual(schedule_check(s, v, '2026-11-18')['status'], 'rolling')
        del s['candidates'][0]['submission_plan']
        self.assertEqual(schedule_check(s, v, '2026-11-18')['status'], 'readiness_unknown')
        self.assertEqual(recheck_journals(s, '2026-11-18T01:00:00Z')[0]['submission']['reference_timezone'], 'Asia/Seoul')

    def test_invalid_dates_offsets_dependencies_and_plan(self):
        for key, value in [('at', '2026-02-30T12:00:00+00:00'), ('at', '2026-12-05T12:00:00'), ('timezone', 'BAD'), ('at', '2026-12-05T23:59:59+09:00'), ('requires', ['paper'])]:
            s = scheduled(); s['journals'][0]['schedule']['deadlines'][0][key] = value
            self.assertTrue(validate(s), (key, value))
        for value in (-1, True, 1.5):
            s = scheduled(); s['candidates'][0]['submission_plan']['writing_days'] = value
            self.assertTrue(validate(s))
        s = scheduled(); before = copy.deepcopy(s)
        recheck_journals(s, '2026-11-18')
        self.assertEqual(s, before)
