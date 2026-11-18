"""Scope narrowing is a proposal that needs a recorded value review."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_research import ROOT
from test_workflow import complete
from researchlib.output import validate, markdown
from researchlib.evaluation import rank
from researchlib.state import save


def scope_review(s, verdict='retain'):
    return {'original_question': s['candidates'][0]['plan']['question'],
            'narrowed_question': 'TEST narrowed question with a meaningful boundary',
            'reason': 'TEST prior study already answers the broad average-effect comparison',
            'knowledge_gain': 'TEST determine whether the conclusion changes at a relevant boundary',
            'decision_impact': 'TEST would change which approach is appropriate under that constraint',
            'scope_loss': 'TEST one boundary only; conclusions do not extend to the full population',
            'alternative': 'TEST keep the original question and compare a different failure mechanism',
            'rationale': 'TEST meaningful uncertainty remains, beyond avoiding paper overlap',
            'verdict': verdict, 'next_actions': ['TEST check the boundary mechanism before applying the scope'],
            'evidence': [copy.deepcopy(s['claims'][0]['evidence'][0])]}


class ScopeReviewTests(unittest.TestCase):
    def test_legacy_sessions_still_validate_and_export(self):
        s = complete(); before = copy.deepcopy(s)
        self.assertEqual(validate(s, final=True), [])
        self.assertIn('## TEST-C1:', markdown(s))
        self.assertEqual(s, before)

    def test_unapproved_narrowing_cannot_be_final(self):
        for verdict in ('pending', 'revise', 'discard'):
            s = complete(); c = s['candidates'][0]; c['scope_review'] = scope_review(s, verdict)
            c['plan']['question'] = c['scope_review']['narrowed_question']
            self.assertEqual(validate(s), [])
            self.assertEqual(rank(s)[0]['status'], 'conditional')
            self.assertTrue(validate(s, final=True))

    def test_rejected_narrowing_does_not_reject_the_original_question(self):
        for verdict in ('revise', 'discard'):
            s = complete(); s['candidates'][0]['scope_review'] = scope_review(s, verdict)
            self.assertEqual(validate(s, final=True), [])
            self.assertEqual(rank(s)[0]['status'], 'passed')

    def test_retained_scope_needs_read_evidence_and_matches_the_question(self):
        s = complete(); c = s['candidates'][0]; c['scope_review'] = scope_review(s)
        c['plan']['question'] = c['scope_review']['narrowed_question']
        self.assertEqual(validate(s, final=True), [])
        self.assertEqual(rank(s)[0]['status'], 'passed')
        for change in ('unread_version', 'no_evidence', 'different_question'):
            draft = copy.deepcopy(s); candidate = draft['candidates'][0]
            if change == 'unread_version': candidate['scope_review']['evidence'][0]['version'] = 'UNREAD'
            elif change == 'no_evidence': candidate['scope_review']['evidence'] = []
            else: candidate['plan']['question'] = 'TEST different scope'
            self.assertEqual(rank(draft)[0]['status'], 'conditional')
            self.assertTrue(validate(draft, final=True))

    def test_invalid_review_shapes_and_missing_value_are_errors(self):
        for bad in (None, [], {}, {'verdict': 'retain'}):
            s = complete(); s['candidates'][0]['scope_review'] = bad
            self.assertTrue(validate(s))
        for field in ('knowledge_gain', 'decision_impact', 'scope_loss', 'alternative', 'rationale'):
            s = complete(); s['candidates'][0]['scope_review'] = scope_review(s)
            s['candidates'][0]['scope_review'][field] = ''
            self.assertTrue(validate(s), field)

    def test_report_shows_value_loss_and_alternative_without_mutation(self):
        s = complete(); s['candidates'][0]['scope_review'] = scope_review(s)
        before = copy.deepcopy(s); report = markdown(s)
        for key in ('original_question', 'narrowed_question', 'knowledge_gain', 'decision_impact', 'scope_loss', 'alternative'):
            self.assertIn(s['candidates'][0]['scope_review'][key], report)
        self.assertEqual(s, before)
        c = s['candidates'][0]
        c['scope_review']['verdict'] = 'pending'
        c['plan']['question'] = c['scope_review']['narrowed_question']
        summary = markdown(s).split('## 진행 상태')[0]
        self.assertIn(c['scope_review']['next_actions'][0], summary)

    def test_cli_records_history_local_invalidation_and_preserves_question(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'state.json'; payload = Path(td)/'scope.json'
            s = complete(); other = copy.deepcopy(s['candidates'][0]); other['id'] = 'TEST-C2'; s['candidates'].append(other)
            save(path, s); review = scope_review(s, 'pending'); save(payload, review)
            command = [sys.executable, str(ROOT/'scripts/research.py'), 'review-scope', str(path), 'TEST-C1', str(payload)]
            for _ in range(2):
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            updated = json.loads(path.read_text()); candidate = updated['candidates'][0]
            self.assertEqual(candidate['plan']['question'], review['original_question'])
            self.assertEqual(len(candidate['scope_review_history']), 1)
            self.assertEqual(candidate['stages']['novelty'], 'stale')
            self.assertEqual(rank(updated)[0]['id'], 'TEST-C2')
            save(payload, {'verdict': 'retain'}); before = path.read_bytes()
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(path.read_bytes(), before)

    def test_cli_final_refusal_preserves_existing_report(self):
        s = complete(); c = s['candidates'][0]; c['scope_review'] = scope_review(s, 'pending')
        c['plan']['question'] = c['scope_review']['narrowed_question']
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'state.json'; save(path, s); before = path.read_bytes()
            report = path.parent/'report.md'; report.write_text('Previous output')
            proc = subprocess.run([sys.executable, str(ROOT/'scripts/research.py'), 'export', str(path), '--final'], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2, proc.stdout+proc.stderr)
            self.assertTrue(json.loads(proc.stdout)['errors'])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(report.read_text(), 'Previous output')

    def test_minimal_pending_and_changed_verdict_preserve_history(self):
        from researchlib.evaluation import record_scope_review
        s = complete(); review = scope_review(s)
        pending = {k: review[k] for k in ('original_question', 'narrowed_question', 'reason', 'next_actions')}
        pending['verdict'] = 'pending'
        record_scope_review(s, 'TEST-C1', pending)
        record_scope_review(s, 'TEST-C1', review)
        history = s['candidates'][0]['scope_review_history']
        self.assertEqual([entry['review']['verdict'] for entry in history], ['pending', 'retain'])
        self.assertEqual(history[0]['review']['original_question'], review['original_question'])
        s['candidates'][0]['scope_review_history'] = None
        before = copy.deepcopy(s)
        with self.assertRaises(ValueError): record_scope_review(s, 'TEST-C1', pending)
        self.assertEqual(s, before)

    def test_shared_methods_and_data_do_not_force_more_narrowing(self):
        s = complete(); c = s['candidates'][0]; c['scope_review'] = scope_review(s)
        c['plan']['question'] = c['scope_review']['narrowed_question']
        for key in ('method', 'data', 'assumptions'):
            c['novelty']['comparison'][key]['difference'] = 'TEST same as prior work; contribution is a meaningful boundary validation'
        self.assertEqual(validate(s, final=True), [])
        self.assertEqual(rank(s)[0]['status'], 'passed')
