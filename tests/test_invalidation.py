import copy
import unittest
from test_workflow import complete
from researchlib.state import invalidate, update_profile, progress_stages
from researchlib.evaluation import rank
from researchlib.output import validate

class InvalidationTests(unittest.TestCase):
    def test_local_change_and_selected_final(self):
        s = complete()
        other = copy.deepcopy(s['candidates'][0]); other['id'] = 'TEST-C2'
        s['candidates'].append(other)
        invalidate(s, 'evaluation', 'TEST pilot', ['TEST-C2'])
        results = {r['id']: r['status'] for r in rank(s)}
        self.assertEqual(results, {'TEST-C1': 'passed', 'TEST-C2': 'conditional'})
        self.assertEqual(progress_stages(s)['evaluation'], 'stale')
        self.assertEqual(validate(s, final=True), [])
        s['report']['selected_candidate_ids'].append('TEST-C2')
        self.assertTrue(any('TEST-C2.stage' in e for e in validate(s, final=True)))
        other['stages'] = dict.fromkeys(other['stages'], 'complete')
        self.assertEqual(validate(s, final=True), [])

    def test_global_change_dominates_local_completion(self):
        s = complete()
        s['candidates'][0]['stages'] = dict(s['stages'])
        for field in ('data', 'data_restrictions'):
            update_profile(s, {field: 'TEST new data'})
            self.assertEqual(s['stages']['gaps'], 'stale')
            self.assertEqual(s['stages']['novelty'], 'stale')
            self.assertEqual(rank(s)[0]['status'], 'conditional')
        self.assertTrue(validate(s, final=True))

    def test_venue_only_and_legacy_global(self):
        s = complete()
        update_profile(s, {'preferred_venues': ['TEST venue']})
        self.assertEqual(s['stages']['analysis'], 'complete')
        self.assertEqual(s['stages']['novelty'], 'complete')
        self.assertEqual(s['stages']['evaluation'], 'stale')
        with self.assertRaises(ValueError):
            invalidate(s, 'evaluation', 'TEST', ['missing'])
        s['candidates'][0]['stages'] = []
        self.assertTrue(validate(s))
