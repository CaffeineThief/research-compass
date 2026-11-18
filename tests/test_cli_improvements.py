"""Exercise new host bookkeeping commands as a connected CLI workflow."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_research import ROOT
from test_submission_schedule import scheduled
from researchlib.state import save, load

class ImprovedCliTests(unittest.TestCase):
    def test_review_search_pilot_and_scheduled_final_export(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td); path = directory / 'state.json'
            s = scheduled(); save(path, s)
            def run(*args, code=0):
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/research.py'), *map(str, args)], capture_output=True, text=True)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                return json.loads(result.stdout)
            def payload(name, data):
                file = directory / name; save(file, data); return file
            review = payload('review.json', {'stage': 'screening', 'reason': 'TEST screen', 'main_blocker': 'TEST comparison', 'next_actions': ['TEST detail']})
            run('review-candidate', path, 'TEST-C1', review)
            run('validate', path, '--final', code=2)
            review = payload('review.json', {'stage': 'detailed', 'reason': 'TEST comparison checked', 'next_actions': []})
            run('review-candidate', path, 'TEST-C1', review)
            reservation = run('reserve-search', path, '--query', 'TEST comparator', '--branch', 'novelty', '--limit', 1)
            response = payload('response.json', {'results': [{'paper_id': 'TEST-P1'}]})
            run('record-search', path, reservation['id'], response)
            run('record-search', path, reservation['id'], response)
            decision = payload('decision.json', {'action': 'stop', 'reason': 'TEST scoped comparison sufficient; limits remain', 'unresolved_questions': ['TEST out-of-scope populations'], 'relevant_paper_ids': ['TEST-P1']})
            run('search-review', path, reservation['id'], decision)
            coverage = run('coverage', path)
            self.assertEqual(coverage['queries'][-1]['admitted'], 1)
            self.assertEqual(coverage['queries'][-1]['action'], 'stop')
            run('record-pilot', path, 'TEST-C1', payload('pilot.json', s['candidates'][0]['pilot']))
            updated = load(path)
            self.assertEqual(updated['stages']['evaluation'], 'complete')
            self.assertEqual(updated['candidates'][0]['stages']['evaluation'], 'stale')
            updated['candidates'][0]['stages'] = dict.fromkeys(updated['stages'], 'complete')
            save(path, updated)
            before = path.read_bytes()
            run('validate', path, '--final')
            outputs = run('export', path, '--final')
            self.assertEqual(len(outputs), 5)
            status = run('journal-recheck', path, '--as-of', '2026-12-08T12:00:00+09:00')
            self.assertEqual(status[0]['submission']['deadlines'][1]['readiness'], 'blocked_prerequisite')
            report = (directory / 'report.md').read_text()
            self.assertIn('## 후보 선택 요약', report)
            self.assertIn('effect_plan', report)
            self.assertEqual(path.read_bytes(), before)
            run('invalidate', path, 'novelty', '--candidate', 'TEST-C1', '--reason', 'TEST new closest study')
            self.assertTrue(run('validate', path, '--final', code=2)['errors'])
