"""Synthetic regressions for RC-02 candidate-to-literature traceability."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_research import ROOT, paper
from test_workflow import complete
from researchlib.evaluation import rank
from researchlib.output import validate, markdown
from researchlib.state import save


class GapLinkTests(unittest.TestCase):
    def test_empty_analysis_cannot_pass_or_become_final_recommendation(self):
        s = complete()
        s['claims'] = []
        s['gaps'] = []
        s['candidates'][0].pop('gap_ids')
        self.assertEqual(validate(s), [])
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        self.assertTrue(any('gap_ids' in error for error in validate(s, final=True)))

    def test_connected_candidate_is_final_and_traceable_in_report(self):
        s = complete()
        self.assertEqual(validate(s, final=True), [])
        self.assertEqual(rank(s)[0]['status'], 'passed')
        self.assertIn('TEST-G1 → TEST-CL1 → TEST-P1', markdown(s))

    def test_missing_chain_has_reason_and_next_work_in_draft(self):
        s = complete()
        s['candidates'][0].pop('gap_ids')
        s['candidates'][0]['gap_review'] = {
            'reason': 'TEST evidence not yet linked',
            'next_actions': ['TEST read comparison study'],
        }
        self.assertEqual(validate(s), [])
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        self.assertTrue(validate(s, final=True))
        report = markdown(s)
        self.assertIn('TEST evidence not yet linked', report)
        self.assertIn('TEST read comparison study', report)

    def test_dangling_gap_and_claim_references_are_reported(self):
        for field, target in [('gap_ids', 'TEST-MISSING-GAP'), ('claim_ids', 'TEST-MISSING-CLAIM')]:
            with self.subTest(field=field):
                s = complete()
                row = s['candidates'][0] if field == 'gap_ids' else s['gaps'][0]
                row[field] = [target]
                self.assertTrue(validate(s))
                self.assertEqual(rank(s)[0]['status'], 'conditional')

    def test_bad_reference_types_are_validation_errors(self):
        for field in ('gap_ids', 'claim_ids'):
            for value in (None, 'TEST-G1', [None], [{}], ['TEST-G1', 'TEST-G1']):
                with self.subTest(field=field, value=value):
                    s = complete()
                    row = s['candidates'][0] if field == 'gap_ids' else s['gaps'][0]
                    row[field] = value
                    self.assertTrue(validate(s))
                    self.assertEqual(rank(s)[0]['status'], 'conditional')

    def test_inaccessible_excluded_and_unread_evidence_cannot_support_gap(self):
        for change in ('unavailable', 'excluded', 'unread', 'versionless'):
            with self.subTest(change=change):
                s = complete()
                if change == 'unavailable':
                    s['papers'][0]['access'] = 'unavailable'
                elif change == 'excluded':
                    s['papers'][0]['excluded'] = True
                elif change == 'unread':
                    s['claims'][0]['evidence'][0]['location'] = 'TEST unread appendix'
                else:
                    s['claims'][0]['evidence'][0].pop('version')
                self.assertEqual(rank(s)[0]['status'], 'conditional')
                self.assertTrue(validate(s, final=True))

    def test_one_valid_gap_does_not_hide_another_broken_gap(self):
        s = complete()
        s['gaps'].append({'id': 'TEST-G2', 'title': 'TEST second gap', 'claim_ids': []})
        s['candidates'][0]['gap_ids'].append('TEST-G2')
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        self.assertTrue(validate(s, final=True))

    def test_one_valid_claim_does_not_hide_an_unread_claim(self):
        s = complete()
        other = copy.deepcopy(s['claims'][0])
        other['id'] = 'TEST-CL2'
        other['evidence'][0]['location'] = 'TEST unread section'
        s['claims'].append(other)
        s['gaps'][0]['claim_ids'].append('TEST-CL2')
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        self.assertTrue(validate(s, final=True))

    def test_malformed_follow_up_record_is_a_validation_error(self):
        for review in (None, {}, {'reason': '', 'next_actions': ['TEST task']},
                       {'reason': 'TEST reason', 'next_actions': 'TEST task'},
                       {'reason': 'TEST reason', 'next_actions': [None]}):
            with self.subTest(review=review):
                s = complete()
                s['candidates'][0].pop('gap_ids')
                s['candidates'][0]['gap_review'] = review
                self.assertTrue(any('gap_review' in error for error in validate(s)))

    def test_no_candidates_can_be_reported_with_reason_and_next_actions(self):
        s = complete()
        s['candidates'] = []
        s['claims'] = []
        s['gaps'] = []
        s['report'].update(selected_candidate_ids=[], no_candidate_reason='TEST insufficient evidence')
        self.assertEqual(validate(s, final=True), [])

    def test_unselected_legacy_candidate_does_not_block_supported_selection(self):
        s = complete()
        legacy = copy.deepcopy(s['candidates'][0])
        legacy.update(id='TEST-LEGACY')
        legacy.pop('gap_ids')
        s['candidates'].append(legacy)
        self.assertEqual(validate(s, final=True), [])
        self.assertEqual(next(r for r in rank(s) if r['id'] == 'TEST-LEGACY')['status'], 'conditional')

    def test_gap_claim_can_reference_an_actual_abstract(self):
        s = complete()
        s['papers'].append(paper('TEST-ABSTRACT', access='abstract_only'))
        ref = s['claims'][0]['evidence'][0]
        ref.update(paper_id='TEST-ABSTRACT', scope='abstract', location='abstract')
        self.assertEqual(validate(s, final=True), [])
        self.assertEqual(rank(s)[0]['status'], 'passed')

    def test_cli_final_rejects_unlinked_draft_and_accepts_linked_plan(self):
        with tempfile.TemporaryDirectory(prefix='rc02-cli-') as td:
            path = Path(td) / 'state.json'
            s = complete()
            s['candidates'][0].pop('gap_ids')
            save(path, s)
            cli = [sys.executable, str(ROOT / 'scripts/research.py')]
            for args, expected in ((['validate', str(path)], 0),
                                   (['evaluate', str(path)], 0),
                                   (['export', str(path)], 0),
                                   (['validate', str(path), '--final'], 2),
                                   (['export', str(path), '--final'], 2)):
                result = subprocess.run(cli + args, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
            self.assertIn('conditional', (Path(td) / 'report.md').read_text())
            s['candidates'][0]['gap_ids'] = ['TEST-G1']
            save(path, s)
            before = path.read_bytes()
            result = subprocess.run(cli + ['export', str(path), '--final'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(path.read_bytes(), before)
            self.assertIn('TEST-G1 → TEST-CL1 → TEST-P1', (Path(td) / 'report.md').read_text())


if __name__ == '__main__':
    unittest.main()
