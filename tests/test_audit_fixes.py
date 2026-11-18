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
