"""Synthetic regression cases for the research workflow."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_research import state, paper, source, ROOT
from researchlib.evaluation import AXES, rank
from researchlib.literature import evidence_errors
from researchlib.output import PLAN_FIELDS, validate, markdown, evidence_cards
from researchlib.planning import pilot_estimate, week_checklist, WEEK_CATEGORIES
from researchlib.journals import recheck_journals
from researchlib.search import Crossref, run_search
from researchlib.budget import search_coverage
from researchlib.state import new_state, save, load, update_profile


def measured():
    return {"status": "measured", "hardware": "TEST GPU", "precision": "TEST fp16", "input_shape": "TEST 224px", "assumptions": "Synthetic timing excludes IO; overhead is an assumption.",
            "batch_size": 16, "dataset_size": 1000, "steps_per_run": 1000, "runs": 3,
            "measured_steps": 100, "elapsed_seconds": 200, "peak_memory_gib": 8,
            "available_memory_gib": 12, "overhead_fraction": 0.2, "source": source()}


def complete():
    s = state()
    s['report'] = {"as_of": "2026-11-12", "scope": "TEST ONLY", "limitations": "Synthetic evidence", "next_actions": "Do not use as research", "selected_candidate_ids": ["TEST-C1"]}
    s['stages'] = dict.fromkeys(s['stages'], 'complete')
    ref = {"paper_id": "TEST-P1", "version": "preprint", "scope": "full_text", "location": source()['location'], "excerpt": "Synthetic short excerpt."}
    s['claims'] = [{"id": "TEST-CL1", "text": "Synthetic claim", "kind": "interpretation", "interpretation": "Synthetic interpretation", "uncertainty": "TEST ONLY", "evidence": [ref]}]
    c = s['candidates'][0]
    c['plan'] = dict.fromkeys(PLAN_FIELDS, 'TEST ONLY: recorded plan')
    c['pilot'] = measured()
    c['pilot']['runs'] = 6
    c['pilot']['assumptions'] = 'TEST same measured step cost for both conditions; six runs total'
    c['design'] = {"primary_comparison": "TEST A vs B", "primary_outcome": "TEST outcome", "independent_unit": "TEST patient", "controls": "TEST fixed split", "uncertainty": "TEST patient bootstrap", "budget_rationale": "TEST matched steps; record elapsed time separately", "matched_budget": "steps", "repeated_runs": 3}
    c['design']['conditions'] = 2
    c['design']['effect_plan'] = {'status': 'quantitative', 'metric': 'TEST AUROC difference', 'minimum_effect': 0.02, 'unit': 'TEST patient', 'required_units': 100, 'available_units': 150, 'basis': 'TEST synthetic simulation, not a real sample calculation', 'assumptions': 'TEST patient clusters, fixed baseline', 'source': source(), 'precision': {'kind': 'ci_half_width', 'target': 0.01, 'level': 0.95}, 'required_repeated_runs': 3}
    c['resource_plan']['scope'] = {'unit': 'TEST patient', 'evaluation_units': 150, 'repeated_runs': 3}
    c['provenance'] = {"assets": [{"id": "TEST-D1", "kind": "dataset", "name": "TEST DATA", "version": "TEST v1", "source": source(), "identifier_strategy": "TEST manifest hash; no patient IDs stored here", "split": "TEST patient split", "pretraining_exposure": "TEST no other checkpoint", "rights": {"status": "verified", "reason": "TEST permission only", "source": source()}, "leakage": {"status": "passed", "reason": "TEST overlap check", "source": source()}}]}
    c['first_week'] = [{"id": f"TEST-T{i}", "category": cat, "day": i + 1, "text": "TEST ONLY task", "done": False} for i, cat in enumerate(WEEK_CATEGORIES)]
    return s


class WorkflowTests(unittest.TestCase):
    def test_refresh_cache_uses_new_generation(self):
        s = new_state('TEST')
        with tempfile.TemporaryDirectory() as td, patch.object(Crossref, 'search', side_effect=[[paper('A', test_data=False)], [paper('B', test_data=False)]]) as mock:
            run_search(s, td, 'TEST', 'recent', limit=1)
            run_search(s, td, 'TEST', 'recent', limit=1, refresh=True)
            result = run_search(s, td, 'TEST', 'recent', limit=1)
        self.assertEqual(result['paper_ids'], ['B'])
        self.assertEqual(s['usage']['results'], 2)
        self.assertEqual(mock.call_count, 2)

    def test_novelty_rejects_string_and_unread_closest(self):
        s = state()
        s['candidates'][0]['novelty']['comparison'] = 'Arbitrary comparison'
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        s = state()
        s['papers'][0]['access'] = 'unavailable'
        self.assertEqual(rank(s)[0]['status'], 'conditional')

    def test_korean_axes_and_zero_results_with_read_evidence(self):
        s = state()
        comparison = s['candidates'][0]['novelty']['comparison']
        s['candidates'][0]['novelty']['comparison'] = {AXES[k]: v for k, v in comparison.items()}
        s['search_log'][0]['count'] = 0
        self.assertEqual(rank(s)[0]['status'], 'passed')
        del s['candidates'][0]['novelty']['comparison']['방법']['evidence'][0]['version']
        self.assertEqual(rank(s)[0]['status'], 'conditional')

    def test_exact_read_location_and_scope(self):
        s = complete()
        ref = s['claims'][0]['evidence'][0]
        self.assertEqual(evidence_errors(ref, s, excerpt=True), [])
        ref['location'] = 'Unread appendix'
        self.assertTrue(evidence_errors(ref, s))
        s['papers'][0]['read_locations'] = [{**source(), 'location': ref['location'], 'url': 'https://example.invalid/TEST-appendix'}]
        self.assertFalse(evidence_errors(ref, s))
        self.assertIn('https://example.invalid/TEST-appendix', evidence_cards(s))
        s['papers'][0]['access'] = 'partial'
        self.assertTrue(evidence_errors(ref, s))
        ref['scope'] = 'partial'
        self.assertFalse(evidence_errors(ref, s))

    def test_null_journal_fields_export_and_wrong_types(self):
        s = state()
        s['journals'] = [{'id': 'TEST-J1', 'candidate_id': 'TEST-C1', 'cost': {'status': 'unverified', 'value': None, 'source': None}, 'index': None}]
        self.assertEqual(validate(s), [])
        self.assertIn('확인 불가', markdown(s))
        for bad in ('wrong', [1], 4, [], False):
            s['journals'][0]['cost']['source'] = bad
            self.assertTrue(validate(s))

    def test_final_is_stricter_than_draft(self):
        s = state()
        self.assertEqual(validate(s), [])
        self.assertTrue(validate(s, final=True))
        s = complete()
        self.assertEqual(validate(s, final=True), [])
        del s['candidates'][0]['plan']['minimum_experiment']
        self.assertTrue(any('minimum_experiment' in e for e in validate(s, final=True)))
        s = complete()
        s['stages']['plan'] = 'partial'
        self.assertTrue(validate(s, final=True))
        s['report']['stage_notes'] = {'plan': 'TEST pending measurements explicitly documented'}
        self.assertEqual(validate(s, final=True), [])

    def test_final_can_report_no_candidates(self):
        s = complete()
        s['candidates'] = []
        s['report']['selected_candidate_ids'] = []
        self.assertTrue(validate(s, final=True))
        s['report']['no_candidate_reason'] = 'TEST insufficient evidence'
        self.assertEqual(validate(s, final=True), [])

    def test_invalid_elapsed_time(self):
        for value in (-1, float('nan'), float('inf'), True, None):
            s = state()
            s['usage']['seconds'] = value
            self.assertTrue(any('usage.seconds' in e for e in validate(s)))

    def test_cards_require_excerpt_version_and_interpretation(self):
        s = complete()
        self.assertIn('Synthetic short excerpt.', evidence_cards(s))
        self.assertIn('TEST-P1', evidence_cards(s))
        del s['claims'][0]['evidence'][0]['excerpt']
        self.assertTrue(validate(s, final=True))
        self.assertEqual(validate(s), [])

    def test_pilot_calculation_and_boundaries(self):
        p = measured()
        r = pilot_estimate(p)
        self.assertEqual(r['estimated_hours'], 2)
        self.assertEqual(r['samples_per_second'], 8)
        self.assertEqual(r['epochs_per_run'], 16)
        self.assertEqual(r['memory_headroom_gib'], 4)
        for field, value in [('elapsed_seconds', 0), ('runs', True), ('steps_per_run', 1.5), ('overhead_fraction', -0.1), ('peak_memory_gib', float('inf')), ('source', None)]:
            invalid = {**p, field: value}
            with self.assertRaises(ValueError):
                pilot_estimate(invalid)
        s = complete()
        s['candidates'][0]['pilot']['peak_memory_gib'] = 13
        self.assertEqual(rank(s)[0]['status'], 'conditional')

    def test_pending_pilot_and_rights_are_conditional_but_reportable(self):
        s = complete()
        c = s['candidates'][0]
        c['pilot'] = {'status': 'pending', 'reason': 'TEST not run', 'measurement_plan': 'TEST log steps, time and memory'}
        c['provenance']['assets'][0]['rights'] = {'status': 'unknown', 'reason': 'TEST license check pending'}
        self.assertEqual(rank(s)[0]['status'], 'conditional')
        self.assertEqual(validate(s, final=True), [])
        self.assertIsNone(pilot_estimate(c['pilot'])['estimated_hours'])

    def test_design_provenance_and_checked_tasks_need_evidence(self):
        s = complete()
        c = s['candidates'][0]
        c['design']['matched_budget'] = 'both magically'
        self.assertTrue(validate(s))
        c['design']['matched_budget'] = 'gpu_time'
        c['provenance']['assets'][0]['leakage']['source'] = None
        self.assertTrue(validate(s))
        c['provenance']['assets'][0]['leakage']['source'] = source()
        c['first_week'][0]['done'] = True
        self.assertTrue(validate(s))
        c['first_week'][0]['evidence'] = source()
        self.assertEqual(validate(s), [])
        checklist = week_checklist(s, 'TEST-C1')
        self.assertIn('- [x] Day 1', checklist)
        self.assertIn('- [ ] Day 2', checklist)

    def test_coverage_reserves_critical_work_and_reports_duplicates(self):
        s = new_state('TEST')
        s['search_log'] = [{'id': 'A', 'branch': 'recent', 'status': 'ok', 'count': 3, 'received_count': 4, 'discarded_count': 1, 'results': [{'doi': '10.test/a'}, {'url': 'https://doi.org/10.test/a'}, {}]}]
        s['usage'].update(requests=1, results=3)
        coverage = search_coverage(s)
        self.assertEqual(coverage['duplicate_occurrences'], 1)
        self.assertEqual(coverage['unidentified_occurrences'], 1)
        self.assertEqual(coverage['branches']['recent']['suggested_results_available'], 47)
        self.assertIn('novelty', coverage['unreviewed_branches'])
        s['search_plan']['allocation'] = {'novelty': 1}
        with self.assertRaises(ValueError):
            search_coverage(s)

    def test_journal_recheck_date_boundary_future_and_unknown(self):
        s = state()
        src = {**source(), 'url': 'https://example.invalid/TEST', 'official': True, 'journal_name': 'TEST', 'issn': 'TEST', 'checked_at': '2026-08-14'}
        s['journals'] = [{'id': 'J', 'name': 'TEST', 'issn': 'TEST', 'index': {'status': 'verified', 'value': 'SCIE', 'source': src}}]
        self.assertEqual(recheck_journals(s, '2026-11-12')[0]['fields']['index']['status'], 'current')
        self.assertEqual(recheck_journals(s, '2026-11-13')[0]['fields']['index']['status'], 'stale')
        self.assertEqual(recheck_journals(s, '2026-08-13')[0]['fields']['index']['status'], 'future_date')
        self.assertEqual(recheck_journals(s, '2026-11-12')[0]['fields']['guidelines']['status'], 'unverified')

    def test_named_conference_uses_edition_and_track_instead_of_issn(self):
        s = state()
        conference = {
            'id': 'TEST-V1', 'candidate_id': 'TEST-C1', 'category': 'conference',
            'name': 'TEST Conference', 'edition': '2027', 'track': 'Main',
            'schedule': {
                'status': 'verified', 'value': 'TEST deadline (UTC)',
                'source': {
                    **source(), 'url': 'https://example.invalid/TEST-CFP',
                    'official': True, 'checked_at': '2026-11-12',
                    'venue_name': 'TEST Conference', 'edition': '2027', 'track': 'Main',
                },
            },
        }
        s['journals'] = [conference]
        self.assertEqual(validate(s), [])
        self.assertIn('| TEST Conference | 학술대회 | 2027 / Main |', markdown(s))
        self.assertIn('일정: TEST deadline (UTC)', markdown(s))
        fields = recheck_journals(s, '2026-11-12')[0]['fields']
        self.assertEqual(fields['schedule']['status'], 'current')
        self.assertNotIn('index', fields)
        for field, mismatch in [('edition', '2026'), ('track', 'Workshop')]:
            with self.subTest(field=field):
                conference[field] = mismatch
                fields = recheck_journals(s, '2026-11-12')[0]['fields']
                self.assertEqual(fields['schedule']['status'], 'unverified')
                conference[field] = conference['schedule']['source'][field]

    def test_preferred_venues_can_be_added_to_older_session(self):
        s = state()
        del s['profile']['preferred_venues']
        s['stages'] = dict.fromkeys(s['stages'], 'complete')
        update_profile(s, {'preferred_venues': ['TEST Conference']})
        self.assertEqual(s['profile']['preferred_venues'], ['TEST Conference'])
        self.assertEqual(s['stages']['analysis'], 'complete')
        self.assertEqual(s['stages']['journals'], 'stale')

    def test_malformed_extension_metadata_is_reported(self):
        for patch in ({'as_of': 'not-a-date'}, {'stage_notes': None}, {'selected_candidate_ids': 7}):
            s = complete()
            s['report'].update(patch)
            self.assertTrue(validate(s))
        for key in ('plan', 'novelty'):
            s = complete()
            s['candidates'][0][key] = None
            self.assertTrue(validate(s))

    def test_secondary_read_version_can_support_comparison(self):
        s = state()
        s['papers'][0]['access'] = 'abstract_only'
        version = paper('TEST-V2')
        version['version'] = 'version-of-record'
        s['papers'][0]['versions'] = [version]
        for axis in s['candidates'][0]['novelty']['comparison'].values():
            axis['evidence'][0].update(version='version-of-record', version_id='TEST-V2')
        s['claims'][0]['evidence'][0].update(version='version-of-record', version_id='TEST-V2')
        self.assertEqual(rank(s)[0]['status'], 'passed')

    def test_final_export_failure_preserves_previous_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'state.json'
            save(path, state())
            report = Path(td) / 'report.md'
            report.write_text('Previous verified output')
            cli = [sys.executable, str(ROOT / 'scripts/research.py')]
            result = subprocess.run(cli + ['export', str(path), '--final'], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(report.read_text(), 'Previous verified output')

    def test_cli_full_workflow_read_only_reports_and_atomic_pilot(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'state.json'
            save(path, complete())
            before = path.read_bytes()
            cli = [sys.executable, str(ROOT / 'scripts/research.py')]
            for args in (['validate', str(path), '--final'], ['coverage', str(path)], ['pilot-estimate', str(path), 'TEST-C1'], ['journal-recheck', str(path), '--as-of', '2026-11-12'], ['checklist', str(path), '--candidate', 'TEST-C1'], ['export', str(path), '--final']):
                result = subprocess.run(cli + args, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(path.read_bytes(), before)
            for name in ('report.md', 'evidence-cards.md', 'first-week.md', 'references.bib', 'references.ris'):
                self.assertTrue((Path(td) / name).is_file())
            pilot = Path(td) / 'pilot.json'
            save(pilot, {**measured(), 'elapsed_seconds': 0})
            self.assertEqual(subprocess.run(cli + ['record-pilot', str(path), 'TEST-C1', str(pilot)], capture_output=True).returncode, 2)
            self.assertEqual(path.read_bytes(), before)
            save(pilot, measured())
            subprocess.run(cli + ['record-pilot', str(path), 'TEST-C1', str(pilot)], capture_output=True, check=True)
            self.assertEqual(load(path)['candidates'][0]['stages']['evaluation'], 'stale')
            self.assertEqual(load(path)['stages']['evaluation'], 'complete')


if __name__ == '__main__':
    unittest.main()
