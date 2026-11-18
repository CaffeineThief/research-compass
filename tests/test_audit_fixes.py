"""Regressions for the six 2026-11-19 audit findings; synthetic inputs only."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_research import ROOT, paper
from test_workflow import complete
from researchlib.output import validate, markdown
from researchlib.state import save


class FinalNoveltyTests(unittest.TestCase):
    def test_bad_novelty_references_block_final_only(self):
        for bad in ('missing_paper', 'excluded_paper', 'unread_version', 'unread_location'):
            with self.subTest(bad=bad):
                s = complete(); c = s['candidates'][0]
                p = paper('TEST-NEAREST'); s['papers'].append(p)
                c['novelty']['closest_paper_ids'] = [p['id']]
                for axis in c['novelty']['comparison'].values():
                    ref = axis['evidence'][0]; ref['paper_id'] = p['id']
                    if bad == 'unread_version': ref['version'] = 'UNREAD'
                    elif bad == 'unread_location': ref['location'] = 'UNREAD section'
                if bad == 'missing_paper': s['papers'].pop()
                if bad == 'excluded_paper': p['excluded'] = True
                self.assertEqual(validate(s), [])
                self.assertTrue(validate(s, final=True))

    def test_secondary_version_and_pending_resources_remain_reportable(self):
        s = complete(); c = s['candidates'][0]
        p = s['papers'][0]; v = paper('TEST-VOR'); v['version'] = 'version-of-record'
        p['versions'] = [v]
        for axis in c['novelty']['comparison'].values():
            axis['evidence'][0].update(version='version-of-record', version_id=v['id'])
        c['pilot'] = {'status': 'pending', 'reason': 'TEST no timing yet', 'measurement_plan': 'TEST first-week timing'}
        self.assertEqual(validate(s, final=True), [])

    def test_cli_final_refusal_preserves_state_and_artifacts(self):
        s = complete()
        s['candidates'][0]['novelty']['closest_paper_ids'] = ['ABSENT-PAPER']
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'state.json'; save(path, s); before = path.read_bytes()
            names = ('report.md', 'evidence-cards.md', 'first-week.md', 'references.bib', 'references.ris')
            for name in names: (path.parent/name).write_text('Previous output')
            for command in ('validate', 'export'):
                result = subprocess.run([sys.executable, str(ROOT/'scripts/research.py'), command, str(path), '--final'], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
                self.assertTrue(json.loads(result.stdout)['errors'])
                self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(path.read_bytes(), before)
            for name in names: self.assertEqual((path.parent/name).read_text(), 'Previous output')


class ResourceValidationTests(unittest.TestCase):
    def test_units_are_input_errors_before_export(self):
        s = complete(); s['candidates'][0]['resource_plan']['scope']['unit'] = 'TEST image'
        self.assertTrue(any('unit' in e for e in validate(s)))
        self.assertTrue(validate(s, final=True))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'state.json'; save(path, s); before = path.read_bytes()
            report = path.parent/'report.md'; report.write_text('Previous output')
            for command in ('validate', 'export'):
                result = subprocess.run([sys.executable, str(ROOT/'scripts/research.py'), command, str(path), '--final'], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
                self.assertTrue(json.loads(result.stdout)['errors'])
                self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(report.read_text(), 'Previous output')

    def test_valid_and_pending_resource_records_export(self):
        for pending in (False, True):
            s = complete()
            if pending:
                s['candidates'][0]['resource_plan'] = {'status': 'pending', 'reason': 'TEST evaluation timing unknown', 'measurement_plan': 'TEST time independent patient evaluation'}
            self.assertEqual(validate(s, final=True), [])
            self.assertIn('## TEST-C1:', markdown(s))


class StageProgressTests(unittest.TestCase):
    def test_global_and_local_status_matrix(self):
        from researchlib.evaluation import rank
        from researchlib.state import candidate_stages, progress_stages
        priority = {'complete': 0, 'partial': 1, 'pending': 2, 'in_progress': 3, 'stale': 4}
        for global_status in priority:
            for local_status in priority:
                with self.subTest(global_status=global_status, local_status=local_status):
                    s = complete(); c = s['candidates'][0]
                    s['stages']['novelty'] = global_status
                    c['stages'] = {'novelty': local_status}
                    s['report']['stage_notes'] = {'novelty': 'TEST explicit remaining work'}
                    c['stage_notes'] = {'novelty': 'TEST candidate scope'}
                    expected = max((global_status, local_status), key=priority.get)
                    self.assertEqual(candidate_stages(s, c)['novelty'], expected)
                    self.assertEqual(progress_stages(s)['novelty'], expected)
                    self.assertEqual(rank(s)[0]['status'], 'passed' if expected == 'complete' else 'conditional')
                    self.assertEqual(bool(validate(s, final=True)), expected not in ('complete', 'partial'))

    def test_unselected_work_does_not_block_selected_final(self):
        from researchlib.evaluation import rank
        from researchlib.state import progress_stages
        s = complete(); other = copy.deepcopy(s['candidates'][0]); other['id'] = 'TEST-C2'
        other['stages'] = {'novelty': 'in_progress'}; s['candidates'].append(other)
        self.assertEqual(progress_stages(s)['novelty'], 'in_progress')
        self.assertEqual({r['id']: r['status'] for r in rank(s)}, {'TEST-C1': 'passed', 'TEST-C2': 'conditional'})
        self.assertEqual(validate(s, final=True), [])
        s['candidates'][0]['stages'] = {'novelty': 'partial'}
        self.assertTrue(validate(s, final=True))
        s['candidates'][0]['stage_notes'] = {'novelty': 'TEST declared limits'}
        self.assertEqual(validate(s, final=True), [])


class DraftShapeTests(unittest.TestCase):
    def test_wrong_parent_shapes_return_errors_without_tracebacks(self):
        cases = [('candidate', key, value) for key in ('plan', 'novelty', 'gates', 'scores') for value in (None, [])]
        cases += [('state', key, None) for key in ('profile', 'usage', 'stages')]
        for kind, key, value in cases:
            with self.subTest(kind=kind, key=key, value=value):
                s = complete(); c = s['candidates'][0]
                c['review'] = {'stage': 'screening', 'reason': 'TEST', 'next_actions': [], 'main_blocker': 'TEST'}
                (c if kind == 'candidate' else s)[key] = value
                self.assertTrue(validate(s))
                with tempfile.TemporaryDirectory() as td:
                    path = Path(td)/'state.json'; save(path, s); before = path.read_bytes()
                    report = path.parent/'report.md'; report.write_text('Previous output')
                    for command in ('validate', 'export'):
                        result = subprocess.run([sys.executable, str(ROOT/'scripts/research.py'), command, str(path)], capture_output=True, text=True)
                        self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
                        self.assertTrue(json.loads(result.stdout)['errors'])
                        self.assertNotIn('Traceback', result.stderr)
                    self.assertEqual(path.read_bytes(), before)
                    self.assertEqual(report.read_text(), 'Previous output')

    def test_review_command_rejects_bad_screening_parents_atomically(self):
        from researchlib.evaluation import record_review
        for key in ('plan', 'novelty'):
            s = complete(); s['candidates'][0][key] = None; before = copy.deepcopy(s)
            with self.assertRaises(ValueError):
                record_review(s, 'TEST-C1', {'stage': 'screening', 'reason': 'TEST', 'next_actions': [], 'main_blocker': 'TEST'})
            self.assertEqual(s, before)
