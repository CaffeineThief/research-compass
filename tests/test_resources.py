"""Synthetic regressions for RC-03 measured costs and available time."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_research import ROOT, source, state
from test_workflow import complete, measured
from researchlib.evaluation import rank
from researchlib.output import validate, markdown
from researchlib.planning import pilot_estimate, resource_check
from researchlib.state import save


class ResourceTests(unittest.TestCase):
    def test_missing_preparation_records_cannot_pass(self):
        for key in ('pilot', 'design', 'provenance', 'resource_plan'):
            with self.subTest(key=key):
                s = complete()
                del s['candidates'][0][key]
                self.assertEqual(validate(s), [])
                self.assertEqual(rank(s)[0]['status'], 'conditional')

    def test_measured_hours_are_compared_with_confirmed_gpu_capacity(self):
        s = complete()
        s['candidates'][0]['pilot']['steps_per_run'] = 1_000_000_000
        result = rank(s)[0]
        self.assertEqual(result['status'], 'conditional')
        self.assertTrue(any('GPU' in reason and '시간' in reason for reason in result['reasons']))
        self.assertIn('GPU', markdown(s))
        s['candidates'][0]['pilot']['steps_per_run'] = 1000
        self.assertEqual(rank(s)[0]['status'], 'passed')

    def test_exact_time_and_memory_boundaries_pass_and_excess_is_reported(self):
        s = complete()
        budget = s['profile']['resource_budget']
        budget.update(weeks=1, gpu_hours_per_week=4, work_hours_per_week=6)
        pilot = s['candidates'][0]['pilot']
        pilot['available_memory_gib'] = pilot['peak_memory_gib']
        self.assertEqual(rank(s)[0]['status'], 'passed')
        budget['gpu_hours_per_week'] = 3.99
        pilot['peak_memory_gib'] += 1
        reasons = rank(s)[0]['reasons']
        self.assertTrue(any('시간' in reason and '초과' in reason for reason in reasons))
        self.assertTrue(any('메모리' in reason and '초과' in reason for reason in reasons))

    def test_unknown_capacity_and_unmeasured_pilots_remain_conditional(self):
        for value in (None, {'status': 'pending', 'reason': 'TEST availability unknown', 'measurement_plan': 'TEST confirm weekly hours'}):
            with self.subTest(value=value):
                s = complete()
                s['profile']['resource_budget'] = value
                self.assertEqual(validate(s), [])
                self.assertEqual(rank(s)[0]['status'], 'conditional')
        s = complete()
        s['profile']['resource_budget'].pop('gpu_hours_per_week')
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        s['candidates'][0]['pilot'] = {'status': 'pending', 'reason': 'TEST not measured', 'measurement_plan': 'TEST time 100 steps'}
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        self.assertEqual(validate(s, final=True), [])

    def test_condition_costs_evaluation_and_setup_are_summed(self):
        a, b = measured(), measured()
        a.update(id='TEST-A', evaluation_hours=0.5, setup_hours=0.25)
        b.update(id='TEST-B', elapsed_seconds=400, evaluation_hours=1, setup_hours=0.5)
        result = pilot_estimate({'status': 'measured', 'conditions': [a, b]})
        self.assertAlmostEqual(result['estimated_hours'], 8.25)
        self.assertEqual(result['runs'], 6)
        self.assertEqual(len(result['conditions']), 2)
        self.assertTrue(result['memory_fits'])
        b['peak_memory_gib'] = 13
        self.assertFalse(pilot_estimate({'status': 'measured', 'conditions': [a, b]})['memory_fits'])
        s = complete()
        s['candidates'][0]['pilot'] = {'status': 'measured', 'conditions': [a, b]}
        self.assertEqual(rank(s)[0]['status'], 'conditional')

    def test_design_repeats_match_each_condition_and_total_runs(self):
        s = complete()
        s['candidates'][0]['pilot']['runs'] = 3
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        s = complete()
        a, b = measured(), measured()
        a.update(id='TEST-A', runs=2)
        b.update(id='TEST-B', runs=4)
        s['candidates'][0]['pilot'] = {'status': 'measured', 'conditions': [a, b]}
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        a['runs'] = b['runs'] = 3
        self.assertEqual(rank(s)[0]['status'], 'passed')
        s['candidates'][0]['design']['conditions'] = 3
        self.assertEqual(rank(s)[0]['status'], 'conditional')

    def test_non_gpu_study_uses_work_hours_and_explains_applicability(self):
        s = state()
        s['profile']['resource_budget'].pop('gpu_hours_per_week')
        self.assertEqual(rank(s)[0]['status'], 'passed')
        s['profile']['resource_budget']['work_hours_per_week'] = 0
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        s['candidates'][0]['pilot'].pop('reason')
        self.assertTrue(validate(s))

    def test_pending_workload_is_reportable_and_cannot_pass(self):
        s = complete()
        s['candidates'][0]['resource_plan'] = {
            'status': 'pending', 'reason': 'TEST workload unknown',
            'measurement_plan': 'TEST time the first analysis',
        }
        self.assertEqual(validate(s, final=True), [])
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        self.assertFalse(resource_check(s['candidates'][0], s)['fits'])
        for key in ('resource_plan', 'pilot'):
            s['candidates'][0][key] = {'status': 'pending', 'reason': 7, 'measurement_plan': 'TEST measure'}
            self.assertTrue(validate(s))

    def test_unknown_legacy_capacity_is_not_inferred_or_saved(self):
        s = complete()
        del s['profile']['resource_budget']
        s['profile']['duration'] = 'TEST two months, availability undecided'
        s['candidates'][0]['pilot']['setup_hours'] = 0.00001
        before = json.dumps(s, sort_keys=True)
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        self.assertEqual(json.dumps(s, sort_keys=True), before)
        s['profile']['resource_budget'] = {'status': 'confirmed', 'weeks': 1,
                                          'gpu_hours_per_week': 4, 'work_hours_per_week': 6,
                                          'source': source()}
        self.assertEqual(rank(s)[0]['status'], 'conditional')

    def test_invalid_budget_and_workload_are_errors(self):
        for key in ('weeks', 'gpu_hours_per_week', 'work_hours_per_week'):
            for value in (-1, True, float('nan'), '8'):
                with self.subTest(key=key, value=value):
                    s = complete()
                    s['profile']['resource_budget'][key] = value
                    self.assertTrue(validate(s))
        s = complete()
        s['candidates'][0]['resource_plan']['work_hours'] = -1
        self.assertTrue(validate(s))
        s = complete()
        s['profile']['resource_budget']['source'] = None
        self.assertTrue(validate(s))

    def test_invalid_condition_records_and_additional_costs_are_rejected(self):
        a = {**measured(), 'id': 'TEST-A'}
        for conditions in ([], [a, a], [None], [{**a, 'status': 'pending'}], [{**a, 'conditions': [a]}]):
            with self.subTest(conditions=conditions):
                with self.assertRaises(ValueError):
                    pilot_estimate({'status': 'measured', 'conditions': conditions})
        for field in ('evaluation_hours', 'setup_hours'):
            with self.assertRaises(ValueError):
                pilot_estimate({**measured(), field: -1})

    def test_cli_profile_validation_and_resource_estimate_preserve_state_on_error(self):
        with tempfile.TemporaryDirectory(prefix='rc03-cli-') as td:
            path, patch = Path(td) / 'state.json', Path(td) / 'profile.json'
            s = complete()
            save(path, s)
            before = path.read_bytes()
            cli = [sys.executable, str(ROOT / 'scripts/research.py')]
            save(patch, {'resource_budget': {**s['profile']['resource_budget'], 'weeks': 0}})
            result = subprocess.run(cli + ['profile', str(path), str(patch)], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_bytes(), before)
            result = subprocess.run(cli + ['pilot-estimate', str(path), 'TEST-C1'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['resource_check']['gpu_hours_available'], 160)
            self.assertEqual(path.read_bytes(), before)
            save(patch, {'resource_budget': {**s['profile']['resource_budget'], 'weeks': 1}})
            subprocess.run(cli + ['profile', str(path), str(patch)], capture_output=True, check=True)
            self.assertEqual(json.loads(path.read_text())['stages']['evaluation'], 'stale')


if __name__ == '__main__':
    unittest.main()
