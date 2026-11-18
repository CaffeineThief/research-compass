import copy
import unittest
from test_workflow import complete
from researchlib.output import markdown, validate
from researchlib.planning import week_checklist

class ReportSelectionTests(unittest.TestCase):
    def test_six_explicit_candidates_preserve_order_and_state(self):
        s = complete(); base = s['candidates'][0]
        s['candidates'] = [{**copy.deepcopy(base), 'id': f'TEST-C{i}'} for i in range(1, 7)]
        s['report']['selected_candidate_ids'] = [c['id'] for c in reversed(s['candidates'])]
        before = copy.deepcopy(s)
        self.assertEqual(validate(s, final=True), [])
        report, checklist = markdown(s), week_checklist(s)
        for content in (report, checklist):
            positions = [content.index(f"## {cid}:") for cid in s['report']['selected_candidate_ids']]
            self.assertEqual(positions, sorted(positions))
        self.assertIn('[TEST-C6:', report)
        self.assertIn('](#candidate-6)', report)
        self.assertLess(report.index('## 후보 선택 요약'), report.index('## 문헌 및 전문'))
        self.assertEqual(s, before)

    def test_default_empty_and_invalid_selection(self):
        s = complete(); del s['report']['selected_candidate_ids']
        self.assertIn('## TEST-C1:', week_checklist(s))
        self.assertIn('## TEST-C1:', markdown(s))
        s['report']['selected_candidate_ids'] = []
        self.assertNotIn('## TEST-C1:', markdown(s))
        self.assertNotIn('## TEST-C1:', week_checklist(s))
        for ids in (['missing'], ['TEST-C1', 'TEST-C1']):
            s['report']['selected_candidate_ids'] = ids
            self.assertTrue(validate(s))
