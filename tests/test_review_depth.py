import copy
import unittest
from test_workflow import complete
from researchlib.evaluation import rank, record_review
from researchlib.output import validate

class ReviewDepthTests(unittest.TestCase):
    def test_screening_hold_promotion_history(self):
        s = complete(); c = s['candidates'][0]
        review = {'stage': 'screening', 'reason': 'TEST first comparison', 'main_blocker': 'TEST data access?', 'next_actions': ['TEST verify access']}
        record_review(s, c['id'], review)
        self.assertIsNone(rank(s)[0]['score'])
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        self.assertTrue(validate(s, final=True))
        review = {**review, 'stage': 'hold', 'reason': 'TEST unavailable data'}
        record_review(s, c['id'], review)
        c['gates']['data']['status'] = 'fail'
        self.assertEqual(rank(s)[0]['status'], 'rejected')
        c['gates']['data']['status'] = 'pass'
        record_review(s, c['id'], {'stage': 'detailed', 'reason': 'TEST access confirmed; compare new evidence', 'next_actions': []})
        c['stages'] = dict.fromkeys(c['stages'], 'complete')
        self.assertEqual(rank(s)[0]['status'], 'passed')
        self.assertEqual(validate(s, final=True), [])
        self.assertEqual(len(c['review_history']), 3)

    def test_malformed_review_does_not_mutate(self):
        s = complete(); before = copy.deepcopy(s)
        for review in ({}, {'stage': 'hold', 'reason': 'TEST', 'next_actions': []}):
            with self.assertRaises(ValueError): record_review(s, 'TEST-C1', review)
            self.assertEqual(s, before)
        s['candidates'][0]['review'] = 'bad'
        self.assertTrue(validate(s))
