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

    def test_final_requires_completed_candidate_novelty_search(self):
        for change in ('missing_search', 'failed_search', 'wrong_branch', 'pending_verdict'):
            s = complete(); c = s['candidates'][0]
            if change == 'missing_search': c['novelty']['search_ids'] = ['ABSENT-SEARCH']
            elif change == 'failed_search': s['search_log'][0]['status'] = 'failed'
            elif change == 'wrong_branch': s['search_log'][0]['branch'] = 'recent'
            else: c['novelty']['status'] = 'pending'
            self.assertTrue(validate(s, final=True), change)

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


class WritingTimezoneTests(unittest.TestCase):
    def schedule(self, completion, days, deadline, zone='America/New_York'):
        from test_submission_schedule import scheduled
        s = scheduled(); c = s['candidates'][0]; v = s['journals'][0]
        c['submission_plan'].update(experiments_complete=completion, writing_days=days, timezone=zone)
        v['schedule']['deadlines'] = [{'id': 'paper', 'kind': 'submission', 'at': deadline, 'timezone': zone}]
        return s, v

    def test_calendar_days_across_spring_and_fall(self):
        from researchlib.journals import schedule_check
        for completion, deadline, expected, readiness in (
            ('2027-03-13T12:00:00-05:00', '2027-03-15T12:30:00-04:00', '2027-03-15T12:00:00-04:00', 'ready_in_time'),
            ('2027-11-06T12:00:00-04:00', '2027-11-08T11:30:00-05:00', '2027-11-08T12:00:00-05:00', 'insufficient_preparation_time'),
        ):
            s, v = self.schedule(completion, 2, deadline)
            result = schedule_check(s, v, '2027-01-01T00:00:00Z')
            self.assertEqual(result['ready_at'], expected)
            self.assertEqual(result['deadlines'][0]['readiness'], readiness)

    def test_repeated_hour_uses_actual_instant_and_zero_days_preserve_fold(self):
        from researchlib.journals import schedule_check
        for completion, deadline, expected in (
            ('2027-11-07T01:45:00-04:00', '2027-11-07T01:30:00-05:00', 'ready_in_time'),
            ('2027-11-07T01:15:00-05:00', '2027-11-07T01:30:00-04:00', 'insufficient_preparation_time'),
        ):
            s, v = self.schedule(completion, 0, deadline)
            result = schedule_check(s, v, '2027-01-01T00:00:00Z')
            self.assertEqual(result['ready_at'], completion)
            self.assertEqual(result['deadlines'][0]['readiness'], expected)
        s, v = self.schedule('2027-11-06T12:00:00-04:00', 0, '2027-11-07T01:30:00-05:00')
        v['schedule']['deadlines'].insert(0, {'id': 'abstract', 'kind': 'abstract', 'at': '2027-11-07T01:45:00-04:00', 'timezone': 'America/New_York'})
        v['schedule']['deadlines'][1]['requires'] = ['abstract']
        self.assertEqual(schedule_check(s, v, '2027-01-01T00:00:00Z')['deadlines'][1]['readiness'], 'pending_prerequisite')

    def test_fixed_zones_date_inputs_and_deadline_boundaries(self):
        from researchlib.journals import schedule_check, submission_plan
        for zone, offset in (('UTC', '+00:00'), ('Asia/Seoul', '+09:00'), ('Etc/GMT+12', '-12:00')):
            s, v = self.schedule('2027-01-01', 2, '2027-01-04T00:00:00'+offset, zone)
            self.assertEqual(submission_plan(s['candidates'][0]).isoformat(), '2027-01-03T23:59:59.999999'+offset)
            for current, expected in (('2027-01-03T23:59:59', 'upcoming'), ('2027-01-04T00:00:00', 'expired'), ('2027-01-04T00:00:01', 'expired')):
                self.assertEqual(schedule_check(s, v, current+offset)['deadlines'][0]['timing'], expected)

    def test_nonexistent_ready_time_is_flagged(self):
        from researchlib.journals import submission_plan
        s, v = self.schedule('2027-03-13T02:30:00-05:00', 1, '2027-03-15T12:00:00-04:00')
        with self.assertRaisesRegex(ValueError, '일광절약시간'):
            submission_plan(s['candidates'][0])
