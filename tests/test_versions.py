"""Synthetic regressions for RC-01 version-specific evidence handling."""
import copy
import unittest

from test_research import paper, source, state
from test_workflow import complete
from researchlib.evaluation import rank
from researchlib.literature import evidence_errors, evidence_version, merge_papers, validate_claims
from researchlib.output import evidence_cards, validate


class VersionEvidenceTests(unittest.TestCase):
    def test_secondary_version_is_shared_by_claims_novelty_and_cards(self):
        s = complete()
        original = paper(access='abstract_only')
        published = paper('TEST-PUBLISHED')
        original.update(doi='10.test/preprint', work_id='TEST-W')
        published.update(doi='10.test/published', work_id='TEST-W',
                         version='version-of-record', identity_evidence=source())
        published['read_evidence'] = {**source(), 'url': 'https://example.invalid/TEST-published'}
        s['papers'] = merge_papers([], [original, published], True)
        refs = [s['claims'][0]['evidence'][0]]
        refs += [axis['evidence'][0] for axis in s['candidates'][0]['novelty']['comparison'].values()]
        for ref in refs:
            ref.update(version='version-of-record', version_id='TEST-PUBLISHED')
        self.assertEqual(validate_claims(s), [])
        self.assertEqual(validate(s, final=True), [])
        self.assertEqual(rank(s)[0]['status'], 'passed')
        self.assertIn('https://example.invalid/TEST-published', evidence_cards(s))

    def test_same_version_accumulates_reading_without_reimport_growth(self):
        original, incoming = paper(), paper()
        original['read_locations'] = [source()]
        incoming['read_evidence'] = {**source(), 'location': 'TEST new appendix',
                                     'url': 'https://example.invalid/TEST-appendix'}
        incoming['read_locations'] = [source(), incoming['read_evidence']]
        merged = merge_papers([original], [incoming], True)
        s = complete()
        s['papers'] = merged
        ref = s['claims'][0]['evidence'][0]
        ref['location'] = 'TEST new appendix'
        self.assertEqual(evidence_errors(ref, s), [])
        self.assertIn('https://example.invalid/TEST-appendix', evidence_cards(s))
        self.assertEqual(merge_papers(merged, [incoming], True), merged)
        self.assertEqual(merge_papers(merged, [original], True), merged)
        self.assertEqual(evidence_errors({**ref, 'location': source()['location']}, s), [])

    def test_secondary_version_can_be_updated_without_changing_representative(self):
        original, second = paper(), paper('TEST-PUBLISHED', 'partial')
        original.update(work_id='TEST-W', doi='10.test/preprint')
        second.update(work_id='TEST-W', doi='10.test/published',
                      version='version-of-record', identity_evidence=source())
        merged = merge_papers([], [original, second], True)
        update = copy.deepcopy(second)
        update['access'] = 'full_text'
        update['read_locations'] = [{**source(), 'location': 'TEST published appendix'}]
        merged = merge_papers(merged, [update], True)
        s = state()
        s['papers'] = merged
        ref = {'paper_id': original['id'], 'version': second['version'],
               'version_id': second['id'], 'scope': 'full_text', 'location': 'TEST published appendix'}
        self.assertEqual(evidence_errors(ref, s), [])
        self.assertEqual(merged[0]['version'], 'preprint')
        self.assertEqual(len(merged[0]['versions']), 1)
        self.assertTrue(evidence_errors({**ref, 'version': 'preprint', 'version_id': original['id']}, s))
        self.assertEqual(merge_papers(merged, [update], True), merged)

    def test_legacy_snapshots_are_combined_without_mutating_state(self):
        s = complete()
        original = s['papers'][0]
        original['read_locations'] = [source()]
        snapshot = {k: copy.deepcopy(v) for k, v in original.items() if k != 'versions'}
        snapshot['read_locations'].append({**source(), 'location': 'TEST legacy appendix'})
        original['versions'] = [snapshot]
        ref = {**s['claims'][0]['evidence'][0], 'location': 'TEST legacy appendix'}
        before = copy.deepcopy(s)
        self.assertEqual(evidence_errors(ref, s), [])
        self.assertEqual(s, before)

    def test_access_upgrade_preserves_previous_read_location(self):
        original, incoming = paper(access='partial'), paper()
        incoming['read_evidence'] = {**source(), 'location': 'TEST newly read methods'}
        s = complete()
        s['papers'] = merge_papers([original], [incoming], True)
        ref = s['claims'][0]['evidence'][0]
        self.assertEqual(evidence_errors(ref, s), [])
        self.assertEqual(evidence_errors({**ref, 'location': 'TEST newly read methods'}, s), [])
        self.assertEqual(merge_papers(s['papers'], [incoming], True), s['papers'])

    def test_shared_doi_alias_preserves_representative_and_read_access(self):
        original, incoming = paper(access='unavailable'), paper('TEST-ALIAS')
        original['doi'] = incoming['doi'] = '10.test/shared'
        s = complete()
        s['papers'] = merge_papers([original], [incoming], True)
        self.assertEqual(s['papers'][0]['id'], original['id'])
        self.assertEqual(s['papers'][0]['access'], 'full_text')
        self.assertEqual(validate(s, final=True), [])
        self.assertEqual(merge_papers(s['papers'], [incoming], True), s['papers'])

    def test_different_doi_versions_do_not_share_read_locations(self):
        original, incoming = paper(), paper('TEST-OTHER')
        original.update(work_id='TEST-W', doi='10.test/original')
        incoming.update(work_id='TEST-W', doi='10.test/other', identity_evidence=source())
        incoming['read_evidence'] = {**source(), 'location': 'TEST only in other DOI'}
        s = complete()
        s['papers'] = merge_papers([original], [incoming], True)
        ref = {**s['claims'][0]['evidence'][0], 'location': 'TEST only in other DOI'}
        self.assertTrue(evidence_errors(ref, s))
        self.assertEqual(evidence_errors({**ref, 'version_id': 'TEST-OTHER'}, s), [])
        self.assertEqual(merge_papers(s['papers'], [incoming], True), s['papers'])

    def test_wrong_versions_unread_locations_and_exclusions_are_rejected(self):
        for change in ({'version': 'unread-version'}, {'version_id': 'UNKNOWN'}, {'location': 'Unread table'}):
            with self.subTest(change=change):
                s = complete()
                s['claims'][0]['evidence'][0].update(change)
                self.assertTrue(validate_claims(s))
        s = complete()
        s['papers'][0]['access'] = 'partial'
        self.assertTrue(validate_claims(s))
        s['claims'][0]['evidence'][0]['scope'] = 'partial'
        self.assertEqual(validate_claims(s), [])
        s['papers'][0]['excluded'] = True
        self.assertTrue(validate_claims(s))
        self.assertIsNone(evidence_version(s['claims'][0]['evidence'][0], s))
        self.assertEqual(rank(s)[0]['status'], 'conditional')

    def test_versionless_draft_remains_readable_but_final_requires_version(self):
        s = complete()
        del s['claims'][0]['evidence'][0]['version']
        self.assertEqual(validate(s), [])
        self.assertTrue(validate(s, final=True))
        s['claims'][0]['evidence'][0]['version_id'] = 'TEST-P1'
        self.assertTrue(validate(s))

    def test_invalid_nested_read_records_are_rejected_at_import(self):
        for update in ({'read_locations': [None]}, {'versions': [None]},
                       {'versions': [paper('TEST-BAD', test_data=False)]}):
            with self.subTest(update=update):
                invalid = {**paper(), **update}
                with self.assertRaises(ValueError):
                    merge_papers([], [invalid], True)


if __name__ == '__main__':
    unittest.main()
