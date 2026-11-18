import copy
import tempfile
import unittest
from unittest.mock import patch
from test_research import paper
from researchlib.state import new_state
from researchlib.budget import reserve_search, record_search, search_coverage, review_search
from researchlib.search import run_search, Crossref

class SearchAccountingTests(unittest.TestCase):
    def test_external_cache_admission_and_session_reuse(self):
        with tempfile.TemporaryDirectory() as td, patch.object(Crossref, 'search', return_value=[paper('A', test_data=False)]) as mock:
            first = new_state('TEST'); run_search(first, td, 'TEST', 'recent', limit=1)
            s = new_state('TEST'); run_search(s, td, 'TEST', 'validation', limit=1)
            run_search(s, td, 'TEST', 'novelty', limit=1)
            c = search_coverage(s)
            self.assertEqual(mock.call_count, 1)
            self.assertEqual((s['usage']['requests'], s['usage']['results']), (0, 1))
            self.assertEqual(c['branches']['validation']['admitted'], 1)
            self.assertEqual(c['branches']['validation']['requests'], 0)
            self.assertEqual(c['branches']['novelty']['reused'], 1)
            self.assertEqual(c['branches']['novelty']['admitted'], 0)
            self.assertEqual(c['identified_occurrences'], 1)
            review = {'action': 'continue', 'reason': 'TEST unresolved comparator', 'unresolved_questions': ['TEST comparator?'], 'relevant_paper_ids': ['A']}
            review_search(s, s['search_log'][0]['id'], review)
            review['action'] = 'stop'; review['reason'] = 'TEST budget; uncertainty remains'
            review_search(s, s['search_log'][1]['id'], review)
            before = copy.deepcopy(s)
            c = search_coverage(s)
            self.assertEqual([q['new_relevant'] for q in c['queries']], [1, 0])
            self.assertEqual(s, before)
            s["papers"][0]["excluded"] = True
            self.assertEqual(search_coverage(s)["queries"][0]["new_relevant"], 0)

    def test_failure_limit_and_replay_counters(self):
        s = new_state('TEST'); s['config']['max_results'] = 2
        entry = reserve_search(s, 'TEST', 'recent', 'web', 10)
        payload = {'results': [{'url': 'https://example.invalid/' + str(i)} for i in range(5)]}
        record_search(s, entry['id'], payload); record_search(s, entry['id'], payload)
        c = search_coverage(s)['branches']['recent']
        self.assertEqual((c['requests'], c['admitted'], c['received'], c['discarded']), (1, 2, 5, 3))
        with tempfile.TemporaryDirectory() as td, patch.object(Crossref, 'search', side_effect=ValueError('TEST failure')):
            s = new_state('TEST'); s['config']['max_requests'] = 1
            run_search(s, td, 'TEST', 'recent'); run_search(s, td, 'OTHER', 'recent')
            c = search_coverage(s)['branches']['recent']
            self.assertEqual((c['requests'], c['admitted'], c['failures']), (1, 0, 2))
            self.assertEqual(s['search_log'][-1]['request_count'], 0)

    def test_review_validation_and_legacy_cache_unknown(self):
        s = new_state('TEST'); entry = reserve_search(s, 'TEST', 'novelty', 'web', 1)
        record_search(s, entry['id'], {'results': []})
        for review in ({}, {'action': 'stop', 'reason': 'TEST', 'unresolved_questions': [], 'relevant_paper_ids': ['missing']}):
            with self.assertRaises(ValueError): review_search(s, entry['id'], review)
        s['search_log'].append({'id': 'old-cache', 'cache_hit': True, 'status': 'ok', 'branch': 'recent', 'count': 2})
        c = search_coverage(s)
        self.assertEqual(c['legacy_cache_accounting_unknown'], ['old-cache'])
        self.assertEqual(c['queries'][0]['action'], 'review_needed')
