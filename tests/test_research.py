"""All records in this module are synthetic fixtures, never research evidence."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from researchlib.evaluation import AXES, evaluate, rank
from researchlib.budget import reserve_search, record_search
from researchlib.journals import verified_field
from researchlib.literature import merge_papers, validate_claims
from researchlib.output import bibliography, markdown, validate
from researchlib.search import Crossref, run_search
from researchlib.state import CRITERIA, GATES, invalidate, load, new_state, now, reserve_agents, save, update_profile, validate_config


def source():
    return {"local_file": "/TEST-ONLY/fixture.txt", "location": "Synthetic fixture section", "checked_at": now()}


def paper(pid="TEST-P1", access="full_text", test_data=True):
    return {"id": pid, "title": "TEST ONLY — Synthetic paper " + pid, "authors": ["Test Author"],
            "year": 2020, "version": "preprint", "access": access, "source": source(),
            "read_evidence": source(), "abstract": "Synthetic abstract", "checked_at": now(), "test_data": test_data}


def candidate():
    return {"id": "TEST-C1", "title": "TEST ONLY — Candidate", "paper_ids": ["TEST-P1"], "gap_ids": ["TEST-G1"],
            "pilot": {"status": "not_applicable", "reason": "TEST conceptual study without GPU experiments"},
            "design": {"status": "not_applicable", "reason": "TEST conceptual study", "effect_plan": {"status": "qualitative", "reason": "TEST theoretical", "criteria": "TEST counterexample and proof consistency", "assumptions": "TEST stated axioms", "source": source()}},
            "provenance": {"status": "not_applicable", "reason": "TEST no datasets or checkpoints"},
            "resource_plan": {"status": "estimated", "work_hours": 6, "assumptions": "TEST reading and writing effort", "source": source()},
            "gates": {k: {"status": "pass", "reason": "Fixture confirmation", "evidence": source()} for k in GATES},
            "scores": {k: {"value": 5, "reason": "Fixture reasoning", "uncertainty": "Fixture uncertainty", "evidence": source()} for k in CRITERIA},
            "novelty": {"status": "distinct_within_scope", "search_ids": ["TEST-S1"], "closest_paper_ids": ["TEST-P1"],
                        "comparison": {key: {"difference": "Synthetic difference", "evidence": [{"paper_id": "TEST-P1", "version": "preprint", "scope": "full_text", "location": source()["location"]}]} for key in AXES}, "uncertainty": "Fixture scope only"}}


def state():
    s = new_state("TEST ONLY — research", True)
    s["papers"] = [paper()]
    s["profile"]["resource_budget"] = {"status": "confirmed", "weeks": 8, "gpu_hours_per_week": 20,
                                       "work_hours_per_week": 10, "source": source()}
    s["claims"] = [{"id": "TEST-CL1", "kind": "interpretation", "text": "Synthetic claim",
                    "interpretation": "Synthetic interpretation", "uncertainty": "TEST ONLY",
                    "evidence": [{"paper_id": "TEST-P1", "version": "preprint", "scope": "full_text",
                                  "location": source()["location"], "excerpt": "Synthetic short excerpt."}]}]
    s["gaps"] = [{"id": "TEST-G1", "title": "TEST ONLY — Gap", "claim_ids": ["TEST-CL1"]}]
    s["search_log"] = [{"id": "TEST-S1", "branch": "novelty", "status": "ok", "query": "TEST ONLY"}]
    s["candidates"] = [candidate()]
    return s


class ResearchTests(unittest.TestCase):
    def test_fulltext_requires_read_evidence(self):
        p = paper()
        del p["read_evidence"]
        with self.assertRaises(ValueError):
            merge_papers([], [p], True)

    def test_abstract_cannot_support_detailed_claim(self):
        s = state()
        s["papers"][0]["access"] = "abstract_only"
        s["claims"] = [{"id": "T", "kind": "author_claim", "text": "Test", "uncertainty": "Unknown",
                        "evidence": [{"paper_id": "TEST-P1", "location": "Methods", "scope": "full_text"}]}]
        self.assertTrue(validate_claims(s))
        s["claims"][0]["evidence"][0]["scope"] = "abstract"
        self.assertEqual(validate_claims(s), [])

    def test_unavailable_cannot_support_content(self):
        s = state()
        s["papers"][0]["access"] = "unavailable"
        s["claims"] = [{"id": "T", "kind": "fact", "text": "Test", "uncertainty": "Unknown",
                        "evidence": [{"paper_id": "TEST-P1", "location": "Abstract", "scope": "abstract"}]}]
        self.assertTrue(validate_claims(s))

    def test_versions_merge_with_identity_evidence(self):
        a, b = paper("TEST-A"), paper("TEST-B", "unavailable")
        a.update(doi="doi:10.TEST/ABC", work_id="TEST-W")
        b.update(doi="10.test/def", work_id="TEST-W", version="version-of-record", identity_evidence=source())
        merged = merge_papers([], [a, b], True)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["access"], "full_text")
        self.assertEqual(merged[0]["version"], "preprint")
        self.assertEqual(merged[0]["versions"][0]["id"], "TEST-B")

    def test_distinct_doi_merge_requires_evidence(self):
        a, b = paper("A"), paper("B")
        a.update(doi="10.test/a", work_id="W")
        b.update(doi="10.test/b", work_id="W")
        with self.assertRaises(ValueError):
            merge_papers([], [a, b], True)

    def test_same_title_does_not_merge(self):
        a, b = paper("A"), paper("B")
        b["title"] = a["title"]
        self.assertEqual(len(merge_papers([], [a, b], True)), 2)

    def test_reimport_is_idempotent(self):
        p = paper()
        once = merge_papers([], [p], True)
        self.assertEqual(merge_papers(once, [p], True), once)

    def test_same_version_can_upgrade_access(self):
        a, b = paper(access="unavailable"), paper()
        result = merge_papers([], [a, b], True)
        self.assertEqual(result[0]["access"], "full_text")

    def test_fixture_mixing_rejected(self):
        with self.assertRaises(ValueError):
            merge_papers([], [paper()], False)

    def test_conflict_is_not_resolved_by_consensus(self):
        s = state()
        s["conflicts"] = [{"id": "X", "status": "unresolved"}]
        s["candidates"][0]["conflict_ids"] = ["X"]
        self.assertEqual(evaluate(s["candidates"][0], s)["status"], "conditional")

    def test_late_prior_work_rejects_high_score(self):
        s = state()
        s["candidates"][0]["novelty"]["status"] = "duplicate"
        result = evaluate(s["candidates"][0], s)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["score"], 5)

    def test_gate_failure_beats_score(self):
        s = state()
        s["candidates"][0]["gates"]["data"]["status"] = "fail"
        self.assertEqual(rank(s)[0]["status"], "rejected")

    def test_unverified_gate_is_conditional(self):
        s = state()
        s["candidates"][0]["gates"]["resources"]["evidence"] = None
        self.assertEqual(rank(s)[0]["status"], "conditional")

    def test_separate_novelty_search_required(self):
        s = state()
        s["search_log"][0]["branch"] = "recent"
        self.assertEqual(rank(s)[0]["status"], "conditional")

    def test_few_feasible_candidates_not_padded(self):
        s = state()
        report = markdown(s)
        self.assertIn("후보는 1개", report)
        self.assertEqual(len(rank(s)), 1)

    def test_unknown_journal_not_invented(self):
        j = {"name": "TEST JOURNAL", "issn": "TEST-ONLY", "index": {"value": "SCIE"}, "cost": {"value": 0}}
        self.assertEqual(verified_field(j, "index")["value"], "확인 불가")
        self.assertEqual(verified_field(j, "cost")["value"], "확인 불가")

    def test_official_journal_identity_and_metric_year_required(self):
        src = {"url": "https://example.invalid/TEST-ONLY", "location": "TEST", "checked_at": now(), "official": True, "journal_name": "TEST", "issn": "TEST-ONLY"}
        j = {"name": "TEST", "issn": "TEST-ONLY", "index": {"value": "SCIE", "status": "verified", "source": src}}
        self.assertEqual(verified_field(j, "index")["value"], "SCIE")
        j["issn"] = "OTHER"
        self.assertEqual(verified_field(j, "index")["value"], "확인 불가")
        j["issn"] = "TEST-ONLY"
        j["metrics"] = {"value": "TEST METRIC", "status": "verified", "source": src}
        self.assertEqual(verified_field(j, "metrics")["value"], "확인 불가")

    def test_search_failure_preserves_state_and_log(self):
        s = new_state("TEST ONLY — mocked network")
        with tempfile.TemporaryDirectory() as td, patch.object(Crossref, "search", side_effect=urllib.error.URLError("offline")):
            r = run_search(s, td, "TEST ONLY", "recent")
        self.assertEqual(r["status"], "failed")
        self.assertEqual(s["papers"], [])
        self.assertEqual(s["usage"]["requests"], 1)
        self.assertEqual(len(s["search_log"]), 1)

    def test_search_cache_reuses_without_network_or_duplicate(self):
        s = new_state("TEST ONLY — mocked network")
        with tempfile.TemporaryDirectory() as td, patch.object(Crossref, "search", return_value=[paper(test_data=False)]) as mock:
            run_search(s, td, "TEST ONLY", "recent", limit=1)
            r = run_search(s, td, "TEST ONLY", "recent", limit=1)
            self.assertEqual(mock.call_count, 1)
        self.assertTrue(r["cache_hit"])
        self.assertEqual(len(s["papers"]), 1)

    def test_request_budget_stops_network(self):
        s = new_state("TEST ONLY")
        s["usage"]["requests"] = s["config"]["max_requests"]
        with tempfile.TemporaryDirectory() as td, patch.object(Crossref, "search") as mock:
            r = run_search(s, td, "TEST ONLY", "recent")
            mock.assert_not_called()
        self.assertEqual(r["status"], "failed")


    def test_host_response_is_capped_and_replay_is_idempotent(self):
        s = state()
        s["usage"]["results"] = 97
        reservation = reserve_search(s, "TEST", "novelty", "web", 15)
        self.assertEqual(reservation["limit"], 3)
        payload = {"results": [{"url": f"https://example.invalid/{i}"} for i in range(15)]}
        result = record_search(s, reservation["id"], payload)
        self.assertEqual((result["count"], result["received_count"], result["discarded_count"]), (3, 15, 12))
        self.assertEqual(s["usage"]["results"], 100)
        self.assertEqual(len(result["results"]), 3)
        record_search(s, reservation["id"], payload)
        self.assertEqual(s["usage"]["results"], 100)
        with self.assertRaises(ValueError):
            reserve_search(s, "TEST", "recent", "web", 1)

    def test_pending_search_blocks_other_requests_and_failure_releases_it(self):
        s = state()
        entry = reserve_search(s, "TEST", "recent", "web", 10)
        with self.assertRaises(ValueError):
            reserve_search(s, "TEST", "recent", "web", 10)
        self.assertTrue(validate(s))
        record_search(s, entry["id"], {"error": "TEST network failure"})
        self.assertEqual(s["usage"]["results"], 0)
        self.assertEqual(s["usage"]["requests"], 1)
        reserve_search(s, "TEST", "recent", "web", 10)

    def test_crossref_truncates_unexpected_excess_and_limits_request(self):
        s = new_state("TEST ONLY")
        s["usage"]["results"] = 98
        records = [paper(str(i), test_data=False) for i in range(15)]
        with tempfile.TemporaryDirectory() as td, patch.object(Crossref, "search", return_value=records) as mock:
            result = run_search(s, td, "TEST", "recent", limit=10)
            self.assertEqual(mock.call_args.args[1], 2)
            self.assertEqual(s["usage"]["results"], 100)
            self.assertEqual(len(s["papers"]), 2)
            self.assertEqual(result["discarded_count"], 13)
            run_search(s, td, "TEST", "recent", limit=10)
            self.assertEqual(mock.call_count, 1)
            self.assertEqual(s["usage"]["results"], 100)

    def test_external_cache_respects_remaining_budget(self):
        first = new_state("TEST ONLY")
        second = new_state("TEST ONLY")
        second["usage"]["results"] = 99
        with tempfile.TemporaryDirectory() as td, patch.object(Crossref, "search", return_value=[paper(str(i), test_data=False) for i in range(5)]):
            run_search(first, td, "TEST", "recent", limit=5)
            result = run_search(second, td, "TEST", "recent", limit=5)
        self.assertTrue(result["cache_hit"])
        self.assertEqual(second["usage"]["results"], 100)
        self.assertEqual(len(second["papers"]), 1)

    def test_legacy_over_budget_state_is_detected_not_rewritten(self):
        s = state()
        s["usage"]["results"] = 115
        self.assertTrue(any("상한 초과" in e for e in validate(s)))
        self.assertEqual(s["usage"]["results"], 115)

    def test_zero_weight_does_not_require_a_score(self):
        s = state()
        s["config"]["weights"]["venue_fit"] = 0
        del s["candidates"][0]["scores"]["venue_fit"]
        self.assertEqual(rank(s)[0]["status"], "passed")

    def test_host_search_cli_admits_only_remaining_results(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            s = state()
            s["usage"]["results"] = 99
            save(root / "state.json", s)
            cli = [sys.executable, str(ROOT / "scripts/research.py")]
            reserved = subprocess.run(cli + ["reserve-search", str(root / "state.json"), "--query", "TEST", "--branch", "novelty", "--limit", "15"], check=True, capture_output=True, text=True)
            entry = json.loads(reserved.stdout)
            save(root / "response.json", {"results": [{"url": "https://example.invalid/TEST"}] * 15})
            subprocess.run(cli + ["record-search", str(root / "state.json"), entry["id"], str(root / "response.json")], check=True, capture_output=True)
            self.assertEqual(load(root / "state.json")["usage"]["results"], 100)

    def test_agents_budget(self):
        s = state()
        reserve_agents(s, 7)
        with self.assertRaises(ValueError):
            reserve_agents(s, 1)

    def test_resource_changes_invalidate_only_downstream(self):
        s = state()
        s["stages"] = dict.fromkeys(s["stages"], "complete")
        update_profile(s, {"compute": "TEST resource constraint"})
        self.assertEqual(s["stages"]["search"], "complete")
        self.assertEqual(s["stages"]["analysis"], "complete")
        self.assertEqual(s["stages"]["evaluation"], "stale")
        self.assertEqual(rank(s)[0]["status"], "conditional")

    def test_venue_changes_preserve_literature(self):
        s = state()
        s["stages"] = dict.fromkeys(s["stages"], "complete")
        update_profile(s, {"index_target": "SCI(E)"})
        self.assertEqual(s["profile"]["index_target"], "SCI(E)")
        self.assertEqual(s["stages"]["analysis"], "complete")
        self.assertEqual(s["stages"]["journals"], "stale")
        self.assertEqual(s["stages"]["evaluation"], "stale")
        self.assertEqual(rank(s)[0]["status"], "conditional")

    def test_invalid_weights_and_nan(self):
        for value in (-1, float("nan"), True):
            s = state()
            s["config"]["weights"]["novelty"] = value
            with self.assertRaises(ValueError):
                validate_config(s["config"])

    def test_excluded_paper_cannot_remain_evidence(self):
        s = state()
        s["papers"][0]["excluded"] = True
        self.assertTrue(validate(s))
        self.assertNotIn("Synthetic paper", bibliography(s, "bib"))

    def test_bibliography_escapes_untrusted_content(self):
        s = state()
        s["papers"][0]["title"] = "TEST } \\input{evil}\nER  - injected"
        self.assertIn("\\textbackslash{}input\\{evil\\}", bibliography(s, "bib"))
        self.assertNotIn("\nER  - injected", bibliography(s, "ris"))
        self.assertIn("TEST DATA", bibliography(s, "bib"))

    def test_atomic_save_preserves_previous_on_serialization_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "state.json"
            save(p, state())
            before = p.read_text()
            with self.assertRaises(ValueError):
                save(p, {"bad": float("nan")})
            self.assertEqual(p.read_text(), before)

    def test_cli_init_validate_export_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as td:
            cli = [sys.executable, str(ROOT / "scripts/research.py")]
            subprocess.run(cli + ["init", td, "--topic", "TEST ONLY", "--test-data"], check=True, capture_output=True)
            p = str(Path(td) / "state.json")
            subprocess.run(cli + ["validate", p], check=True, capture_output=True)
            subprocess.run(cli + ["export", p], check=True, capture_output=True)
            for name in ("report.md", "references.bib", "references.ris"):
                self.assertTrue((Path(td) / name).is_file())
            self.assertNotEqual(subprocess.run(cli + ["init", td, "--topic", "overwrite"], capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
