"""Synthetic research-flow and legacy-plan regressions for RC-04."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_research import ROOT
from test_workflow import complete
from researchlib.output import PLAN_FIELDS, RESEARCH_FLOW_FIELDS, markdown, validate
from researchlib.state import save

NEW_FIELDS = ('problem', 'prior_work', 'research_gap', 'objective', 'expected_contribution')

class ResearchFlowTests(unittest.TestCase):
    def test_flow_is_first_ordered_unique_and_has_23_plan_fields(self):
        s = complete()
        report = markdown(s)
        start = report.index('## TEST-C1:')
        headings = [f'### {title}\n' for title in RESEARCH_FLOW_FIELDS.values()]
        positions = [report.index(title, start) for title in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(positions[-1], report.index('### 평가 근거', start))
        self.assertEqual(len(PLAN_FIELDS), 23)
        for title in headings:
            self.assertEqual(report.count(title), 1)
        self.assertIn('TEST-G1 → TEST-CL1 → TEST-P1', report)

    def test_missing_flow_fields_fail_final_only_without_mutation(self):
        for key in NEW_FIELDS:
            s = complete()
            s['candidates'][0]['plan'].pop(key)
            before = copy.deepcopy(s)
            self.assertEqual(validate(s), [])
            self.assertTrue(any('plan.' + key in e for e in validate(s, final=True)))
            self.assertIn('미정 — 추가 확인 필요', markdown(s))
            self.assertEqual(s, before)

    def test_legacy_18_field_plan_remains_exportable_as_draft(self):
        s = complete()
        for key in NEW_FIELDS:
            s['candidates'][0]['plan'].pop(key)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'state.json'
            save(path, s)
            before = path.read_bytes()
            cli = [sys.executable, str(ROOT/'scripts/research.py')]
            result = subprocess.run(cli + ['export', str(path)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(cli + ['validate', str(path), '--final'], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_bytes(), before)
