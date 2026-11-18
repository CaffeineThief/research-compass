"""Query relevance must be grounded in that query's admitted records."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_research import ROOT, paper
from test_workflow import complete
from researchlib.budget import reserve_search, record_search, review_search, search_coverage
from researchlib.literature import merge_papers
from researchlib.search import Crossref, run_search
from researchlib.state import new_state, save


def review(ids):
    return {'action': 'stop', 'reason': 'TEST scoped review', 'unresolved_questions': [], 'relevant_paper_ids': ids}


class SearchLinkTests(unittest.TestCase):
    def test_zero_result_review_cannot_claim_old_paper(self):
        s = complete(); entry = reserve_search(s, 'TEST empty', 'recent', 'fixture', 1)
        record_search(s, entry['id'], {'results': []}); before = copy.deepcopy(s)
        with self.assertRaises(ValueError): review_search(s, entry['id'], review(['TEST-P1']))
        self.assertEqual(s, before)
        review_search(s, entry['id'], review([]))
        self.assertEqual(search_coverage(s)['queries'][-1]['new_relevant'], 0)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'state.json'; payload = Path(td)/'review.json'
            save(path, before); save(payload, review(['TEST-P1'])); old = path.read_bytes()
            proc = subprocess.run([sys.executable, str(ROOT/'scripts/research.py'), 'search-review', str(path), entry['id'], str(payload)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertNotIn('Traceback', proc.stderr)
            self.assertEqual(path.read_bytes(), old)

    def test_doi_alias_and_merged_representative_link(self):
        s = complete(); p = s['papers'][0]; p['doi'] = '10.test/main'
        incoming = paper('TEST-ALIAS'); incoming['doi'] = '10.test/main'
        s['papers'] = merge_papers(s['papers'], [incoming], True)
        entry = reserve_search(s, 'TEST DOI', 'recent', 'fixture', 2)
        record_search(s, entry['id'], {'results': [{'url': 'https://doi.org/10.TEST/MAIN'}, {'paper_id': 'TEST-ALIAS'}]})
        before_usage = copy.deepcopy(s['usage'])
        review_search(s, entry['id'], review(['TEST-ALIAS']))
        self.assertEqual(entry['review']['relevant_paper_ids'], ['TEST-P1'])
        result = search_coverage(s)['queries'][-1]
        self.assertEqual(result['new_relevant'], 1)
        self.assertEqual(result['result_paper_ids'], ['TEST-P1'])
        review_search(s, entry['id'], review(['TEST-P1']))
        record_search(s, entry['id'], {'results': [{'url': 'https://doi.org/10.TEST/MAIN'}, {'paper_id': 'TEST-ALIAS'}]})
        self.assertEqual(s['usage'], before_usage)

    def test_legacy_unlinked_reviews_stay_unknown_and_unchanged(self):
        s = complete(); s['search_log'][0]['review'] = review(['TEST-P1'])
        before = copy.deepcopy(s)
        item = search_coverage(s)['queries'][0]
        self.assertIsNone(item['new_relevant'])
        self.assertEqual(item['result_link_status'], 'unknown')
        self.assertEqual(s, before)
        s['search_log'][0].update(results=[], count=0)
        item = search_coverage(s)['queries'][0]
        self.assertIsNone(item['new_relevant'])
        self.assertEqual(item['result_link_status'], 'unlinked_review')

    def test_cache_reuse_is_linked_but_not_new(self):
        with tempfile.TemporaryDirectory() as td, patch.object(Crossref, 'search', return_value=[paper('TEST-A', test_data=False)]) as call:
            original = new_state('TEST'); run_search(original, td, 'TEST', 'recent', limit=1)
            s = new_state('TEST'); first = run_search(s, td, 'TEST', 'validation', limit=1)
            review_search(s, first['id'], review(['TEST-A']))
            second = run_search(s, td, 'TEST', 'novelty', limit=1)
            review_search(s, second['id'], review(['TEST-A']))
            before = copy.deepcopy(s)
            queries = search_coverage(s)['queries']
            self.assertEqual([q['new_relevant'] for q in queries], [1, 0])
            self.assertEqual([q['result_link_status'] for q in queries], ['linked', 'linked'])
            self.assertEqual((s['usage']['requests'], s['usage']['results'], call.call_count), (0, 1, 1))
            self.assertEqual(s, before)

    def test_unidentified_or_ambiguous_results_cannot_prove_link(self):
        s = complete(); s['papers'].append(paper('TEST-P2'))
        for p in s['papers']: p['url'] = 'https://example.invalid/shared'
        entry = reserve_search(s, 'TEST ambiguous', 'recent', 'fixture', 1)
        record_search(s, entry['id'], {'results': [{'url': 'https://example.invalid/shared'}]})
        with self.assertRaises(ValueError): review_search(s, entry['id'], review(['TEST-P1']))
        entry['review'] = review(['TEST-P1'])
        self.assertIsNone(search_coverage(s)['queries'][-1]['new_relevant'])
