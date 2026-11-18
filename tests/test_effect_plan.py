import copy
import unittest
from test_workflow import complete
from researchlib.output import validate, markdown
from researchlib.evaluation import rank
from researchlib.planning import resource_check

class EffectPlanTests(unittest.TestCase):
    def test_units_and_numeric_boundaries(self):
        for key, value in [('minimum_effect', 0), ('required_units', True), ('available_units', -1), ('unit', 'TEST image'), ('source', None)]:
            s = complete(); s['candidates'][0]['design']['effect_plan'][key] = value
            self.assertTrue(validate(s), (key, value))
        s = complete(); s['candidates'][0]['design']['effect_plan']['precision'] = {'kind': 'power', 'target': 1, 'level': 0.05}
        self.assertTrue(validate(s))
        s['candidates'][0]['design']['effect_plan']['precision']['target'] = 0.8
        self.assertEqual(validate(s, final=True), [])

    def test_sample_events_repeats_change_resource_scope(self):
        s = complete(); c = s['candidates'][0]; plan = c['design']['effect_plan']
        plan.update(required_units=160, available_units=155, required_repeated_runs=4)
        c['pilot']['dataset_size'] = 100000
        reasons = resource_check(c, s)['reasons']
        self.assertTrue(any('표본 부족' in r for r in reasons))
        self.assertTrue(any('반복 수보다' in r for r in reasons))
        self.assertTrue(any('자원 산정 범위' in r for r in reasons))
        plan['events'] = {'unit': 'TEST positive patient', 'required': 30, 'available': 10}
        self.assertTrue(any('사건 수 부족' in r for r in resource_check(c, s)['reasons']))
        plan.update(required_units=100, available_units=150, required_repeated_runs=3)
        plan['events']['available'] = 40
        c['resource_plan']['scope']['events'] = {'unit': 'TEST positive patient', 'count': 40}
        self.assertEqual(rank(s)[0]['status'], 'passed')
        c['design']['repeated_runs'] = 4
        self.assertEqual(rank(s)[0]['status'], 'conditional')

    def test_pending_task_link_legacy_and_qualitative(self):
        s = complete(); c = s['candidates'][0]
        del c['design']['effect_plan']
        before = copy.deepcopy(s)
        self.assertEqual(validate(s), [])
        self.assertTrue(validate(s, final=True))
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        self.assertEqual(s, before)
        c['design']['effect_plan'] = {'status': 'pending', 'reason': 'TEST prevalence unknown', 'measurement_plan': 'TEST count independent events and simulate precision'}
        self.assertTrue(validate(s, final=True))
        task = next(t for t in c['first_week'] if t['category'] == 'measurement')
        c['design']['effect_plan']['measurement_task_id'] = task['id']
        self.assertEqual(validate(s, final=True), [])
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        c['design']['effect_plan'] = {'status': 'qualitative', 'reason': 'TEST proof study', 'criteria': 'TEST counterexample/proof review', 'assumptions': 'TEST axioms', 'source': c['pilot']['source']}
        self.assertEqual(validate(s, final=True), [])
        self.assertIn('effect_plan', markdown(s))
