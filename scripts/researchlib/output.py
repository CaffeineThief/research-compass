import re
import math
import json
from datetime import date

from .evaluation import rank, gap_errors, review_errors, selected_candidates
from .journals import verified_field, recheck_journals, venue_fields, schedule_check, submission_plan, zone
from .literature import validate_claims, validate_paper, evidence_errors, evidence_version, valid_id_list
from .planning import planning_errors, pilot_estimate, resource_budget, resource_check
from .budget import search_coverage
from .state import validate_config, candidate_stages, progress_stages, STAGES

RESEARCH_FLOW_FIELDS = {
    "problem": "문제 정의", "prior_work": "기존 연구의 해결 범위", "research_gap": "남은 연구 공백",
    "objective": "연구 목적", "question": "한 문장 연구 질문", "hypothesis": "검증 가능한 가설",
    "minimum_experiment": "최소 검증 실험", "expected_contribution": "기대 기여"
}

PLAN_FIELDS = {
    **RESEARCH_FLOW_FIELDS, "importance": "연구의 중요성",
    "difference": "가장 가까운 선행 연구와 차별성", "reading_order": "핵심 선행 연구와 읽는 순서",
    "reading_sections": "확인할 절·방법·실험", "prerequisites": "개념과 사전 지식", "data_plan": "데이터 확보 계획",
    "method": "방법론과 구현 단계", "evaluation_plan": "비교 기준·지표·통제 조건",
    "robustness": "제거 실험·민감도·통계 검증",
    "decision_rules": "성공·수정·중단 기준", "schedule": "단계별 일정과 산출물",
    "resources_risks": "자원과 주요 위험", "fallback": "실패 시 대체 접근", "venues": "예비 투고처와 근거",
    "negative_result_value": "예상과 다른 결과에서 얻을 지식"
}


def validate(state, final=False):
    errors = []
    for collection in ("papers", "claims", "conflicts", "gaps", "candidates", "journals", "search_log"):
        rows = state.get(collection)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            errors.append(f"{collection}: 객체 배열 필요")
        elif any(not isinstance(row.get('id'), str) or not row['id'] for row in rows):
            errors.append(f"{collection}: 문자열 ID 필요")
    for key in ("report", "search_plan"):
        if not isinstance(state.get(key, {}), dict):
            errors.append(f"{key}: 객체 필요")
    if errors:
        return errors
    report = state.get("report", {})
    if "stage_notes" in report and not isinstance(report["stage_notes"], dict):
        errors.append("report.stage_notes: 객체 필요")
    if report.get("as_of") is not None:
        try:
            date.fromisoformat(report["as_of"])
        except (ValueError, TypeError):
            errors.append("report.as_of: YYYY-MM-DD 필요")
    selection = report.get("selected_candidate_ids")
    if selection is not None and (not isinstance(selection, list) or any(not isinstance(s, str) for s in selection)):
        errors.append("report.selected_candidate_ids: 문자열 배열 필요")
    for candidate in state["candidates"]:
        if "stage_notes" in candidate and not isinstance(candidate["stage_notes"], dict):
            errors.append(f"candidate {candidate['id']}.stage_notes: 객체 필요")
        stages = candidate.get("stages", {})
        if (not isinstance(stages, dict) or set(stages) - set(STAGES)
                or any(value not in ("pending", "in_progress", "stale", "complete", "partial") for value in stages.values())):
            errors.append(f"candidate {candidate['id']}.stages: 올바른 단계 상태 필요")
        for key in ("plan", "novelty", "gates", "scores"):
            if key in candidate and not isinstance(candidate[key], dict):
                errors.append(f"candidate {candidate['id']}.{key}: 객체 필요")
        errors.extend(f"candidate {candidate['id']}: {e}" for e in review_errors(candidate))
        if "gap_ids" in candidate and not valid_id_list(candidate["gap_ids"]):
            errors.append(f"candidate {candidate['id']}.gap_ids: 고유한 문자열 ID 배열 필요")
        if "gap_review" in candidate:
            review = candidate["gap_review"]
            if (not isinstance(review, dict)
                    or not isinstance(review.get("reason"), str) or not review["reason"].strip()
                    or not isinstance(review.get("next_actions"), list) or not review["next_actions"]
                    or any(not isinstance(action, str) or not action.strip() for action in review["next_actions"])):
                errors.append(f"candidate {candidate['id']}.gap_review: 부족 사유와 다음 확인 작업 배열 필요")
    for claim in state["claims"]:
        refs = claim.get("evidence", [])
        if not isinstance(refs, list) or any(not isinstance(ref, dict) for ref in refs):
            errors.append(f"claim {claim['id']}: 근거 객체 배열 필요")
    if errors:
        return errors
    try:
        validate_config(state["config"])
        resource_budget(state["profile"])
        zone(state["profile"].get("timezone") or "UTC")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.append(str(exc))
    for key, ceiling in (("requests", "max_requests"), ("results", "max_results"), ("agent_calls", "max_agent_calls")):
        value = state["usage"].get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"usage.{key}: 0 이상의 정수 필요")
        elif value > state["config"][ceiling]:
            errors.append(f"usage.{key}: 상한 초과 ({value}/{state['config'][ceiling]}), 이력 대조 필요")
    seconds = state["usage"].get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
        errors.append("usage.seconds: 0 이상의 유한 수 필요")
    if any(s.get("status") == "pending" for s in state["search_log"]):
        errors.append("완료되지 않은 검색 예약이 있습니다.")
    for collection in ("papers", "claims", "conflicts", "gaps", "candidates", "journals", "search_log"):
        ids = [row.get("id") for row in state[collection]]
        if None in ids or len(ids) != len(set(ids)):
            errors.append(f"{collection}: 누락/중복 ID")
    for paper in state["papers"]:
        try:
            validate_paper(paper, state["test_data"])
        except ValueError as exc:
            errors.append(str(exc))
    errors.extend(validate_claims(state))
    paper_ids = {p["id"] for p in state["papers"] if not p.get("excluded")}
    claim_ids = {c["id"] for c in state["claims"]}
    gap_ids = {g["id"] for g in state["gaps"]}
    for gap in state["gaps"]:
        refs = gap.get("claim_ids")
        if not valid_id_list(refs) or not refs or set(refs) - claim_ids:
            errors.append(f"gap {gap.get('id')}: 근거 주장 참조 필요")
    for candidate in state["candidates"]:
        if not candidate.get("paper_ids") or set(candidate["paper_ids"]) - paper_ids:
            errors.append(f"candidate {candidate.get('id')}: 없거나 제외된 근거 문헌")
        if not candidate.get("title"):
            errors.append("후보 제목 누락")
        if set(candidate.get("gap_ids", [])) - gap_ids:
            errors.append(f"candidate {candidate['id']}.gap_ids: 없는 연구 공백 참조")
        errors.extend(f"candidate {candidate['id']}: {e}" for e in planning_errors(candidate))
        try:
            submission_plan(candidate)
        except (ValueError, OverflowError) as exc:
            errors.append(f"candidate {candidate['id']}: {exc}")
    candidate_ids = {c["id"] for c in state["candidates"]}
    for journal in state["journals"]:
        if journal.get("candidate_id") not in candidate_ids:
            errors.append(f"journal {journal.get('id')}: 후보 참조 필요")
        try:
            schedule_check(state, journal, report.get("as_of"))
        except (ValueError, OverflowError) as exc:
            errors.append(f"venue {journal['id']}: {exc}")
        for key in venue_fields(journal):
            try:
                verified_field(journal, key)
            except ValueError as exc:
                errors.append(str(exc))
    try:
        rank(state)
        selected_candidates(state)
        search_coverage(state)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.append(str(exc))
    if final and not errors:
        report = state.get("report", {})
        if not isinstance(report, dict):
            return errors + ["report: 객체 필요"]
        for key in ("as_of", "scope", "limitations", "next_actions"):
            if not report.get(key):
                errors.append(f"report.{key}: 최종 보고서 필수 항목")
        try:
            date.fromisoformat(report.get("as_of", ""))
        except (ValueError, TypeError):
            errors.append("report.as_of: YYYY-MM-DD 필요")
        for stage, status in state["stages"].items():
            if status not in ("complete", "partial") or (status == "partial" and not report.get("stage_notes", {}).get(stage)):
                errors.append(f"stage {stage}: 완료 또는 사유가 있는 partial 필요")
        selected = report.get("selected_candidate_ids", [])
        if not isinstance(selected, list) or any(not isinstance(s, str) for s in selected) or len(selected) != len(set(selected)) or set(selected) - candidate_ids:
            errors.append("report.selected_candidate_ids: 고유한 후보 ID 배열 필요")
        elif not selected and not report.get("no_candidate_reason"):
            errors.append("추천 후보가 없으면 report.no_candidate_reason 필요")
        else:
            for candidate in state["candidates"]:
                if candidate["id"] not in selected:
                    continue
                if (candidate.get("review") or {}).get("stage", "detailed") != "detailed":
                    errors.append(f"candidate {candidate['id']}: 최종 선택 전 상세 검토 필요")
                for stage, status in candidate_stages(state, candidate).items():
                    if status not in ("complete", "partial") or (status == "partial" and not candidate.get("stage_notes", {}).get(stage) and not report.get("stage_notes", {}).get(stage)):
                        errors.append(f"candidate {candidate['id']}.stage {stage}: 재검토 완료 또는 사유 있는 partial 필요")
                errors.extend(f"candidate {candidate['id']}: {issue}" for issue in gap_errors(candidate, state))
                if next(r for r in rank(state) if r['id'] == candidate['id'])["status"] == "rejected":
                    errors.append(f"candidate {candidate['id']}: 탈락 후보는 최종 추천 불가")
                errors.extend(f"candidate {candidate['id']}: {e}" for e in planning_errors(candidate, final=True))
                for key in PLAN_FIELDS:
                    value = candidate.get("plan", {}).get(key)
                    if not isinstance(value, str) or not value.strip():
                        errors.append(f"candidate {candidate['id']}.plan.{key}: 계획 필요")
        for claim in state["claims"]:
            if not claim.get("interpretation"):
                errors.append(f"claim {claim['id']}: 근거 해석 필요")
            for evidence in claim.get("evidence", []):
                errors.extend(f"claim {claim['id']}: {e}" for e in evidence_errors(evidence, state, excerpt=True))
    return errors


def cell(value):
    return str(value if value is not None else "미정").replace("|", "\\|").replace("\n", " ")


def markdown(state):
    result = rank(state)
    label = "테스트용 데이터 — 실제 연구 근거가 아님" if state["test_data"] else "실제 자료 세션 — 출처 확인 범위 내 해석"
    selected = selected_candidates(state)
    results = {r["id"]: r for r in result}
    lines = [f"# {state['topic']}", "", label, "", "## 후보 선택 요약", "",
             "조건부 후보는 확인 과제를 해결한 뒤 착수합니다. [근거 카드](evidence-cards.md) · [첫 주 작업](first-week.md)", "",
             "| 후보·상태·상세 | 문제 | 연구 질문 | 방법 | 기대 기여 | 주요 위험 | 다음 행동 |",
             "|---|---|---|---|---|---|---|"]
    for index, c in enumerate(selected, 1):
        plan = c.get("plan", {})
        tasks = [t["text"] for t in c.get("first_week", []) if not t.get("done")]
        actions = (c.get("review") or {}).get("next_actions", [])
        risk = plan.get("resources_risks") or "; ".join(results[c["id"]]["reasons"])
        action = next(iter(tasks or actions), "미정 — 첫 주 작업 작성 필요")
        values = [f"[{cell(c['id'])}: {cell(c['title'])}](#candidate-{index}) / {results[c['id']]['status']}",
                  plan.get("problem"), plan.get("question"), plan.get("method") or plan.get("minimum_experiment"),
                  plan.get("expected_contribution"), risk or "미정 — 위험 검토 필요", action]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    if not selected:
        lines += ["", state.get("report", {}).get("no_candidate_reason", "선택 후보 없음 — 근거와 실행 조건을 검토하세요.")]
    lines += ["", "## 진행 상태", ""]
    final_errors = validate(state, final=True)
    lines += ["최종 보고서 검증: " + (f"미완료 ({len(final_errors)}개 확인 과제)" if final_errors else "통과 — 기록 완결성 확인, 연구 타당성 보증 아님"), ""]
    for key in ("as_of", "scope", "limitations", "next_actions"):
        if key in state.get("report", {}):
            lines.append(f"- {key}: {cell(state['report'][key])}")
    lines.extend(f"- {k}: {v}" for k, v in progress_stages(state).items())
    lines += ["", "## 사용자 조건", ""]
    for key, value in state["profile"].items():
        if isinstance(value, dict):
            lines += [f"<details><summary>{key} 기록</summary>", "", "```json", json.dumps(value, ensure_ascii=False, indent=2), "```", "", "</details>", ""]
        else:
            lines.append(f"- {key}: {cell(value)}")
    lines += ["", "## 문헌 및 전문 확인 상태", "", "| ID | 문헌 | 연도 | 접근 | 버전 | 확인일 |", "|---|---|---|---|---|---|"]
    for p in state["papers"]:
        status = "제외됨" if p.get("excluded") else p["access"]
        lines.append(f"| {cell(p['id'])} | {cell(p['title'])} | {cell(p.get('year'))} | {status} | {cell(p['version'])} | {cell(p['checked_at'])} |")
    lines += ["", "문헌 출처:", ""]
    for p in state["papers"]:
        url = p.get("url") or p["source"].get("url") or p["source"].get("local_file")
        lines.append(f"- {cell(p['id'])}: {url}")
        if p.get("analysis"):
            lines.append(f"  - 문헌 분석: {p['analysis']}")
    lines += ["", "## 근거가 연결된 주장과 한계", ""]
    for c in state["claims"]:
        lines.append(f"- **{c['id']} / {c['kind']}**: {c['text']} (한계 분류: {c.get('limitation_kind', '해당 없음')}; 불확실성: {c['uncertainty']})")
        lines.extend(f"  - 근거: {e['paper_id']}, {e['location']} ({e.get('scope', '확인 범위 참조')})" for e in c.get("evidence", []))
    lines += ["", "## 충돌하는 결과", ""]
    for c in state["conflicts"]:
        lines.append(f"- {c['id']}: {c.get('summary', '설명 미정')} / {c['status']} / 주장 {', '.join(c['claim_ids'])} / {c.get('resolution_evidence', '해소 근거 없음')}")
    lines += ["", "## 연구 흐름과 공백", ""]
    for g in state["gaps"]:
        lines.append(f"### {g['id']}: {g.get('title', '제목 미정')}")
        lines.extend(f"- {k}: {g.get(k, '미정')}" for k in ("claim_ids", "importance", "attempted_solutions", "why_unresolved", "strength", "uncertainty"))
    lines += ["", "## 후보 비교", "", "점수는 게재 확률이 아닙니다. 조건부 후보를 실행 가능 후보로 집계하지 않습니다.", "",
              "| 후보 | 상태 | 점수 / 5 | 사유 |", "|---|---|---|---|"]
    for r in result:
        lines.append(f"| {cell(r['id'])} | {r['status']} | {cell(r['score'])} | {cell('; '.join(r['reasons']))} |")
    passed = sum(r["status"] == "passed" for r in result)
    if passed < 2:
        lines += ["", f"검증을 통과한 후보는 {passed}개입니다. 추천 수를 채우기 위해 후보를 추가하지 않습니다."]
    for index, c in enumerate(selected, 1):
        r = results[c["id"]]
        lines += ["", f'<a id="candidate-{index}"></a>', "", f"## {c['id']}: {c['title']} ({r['status']})", "",
                  "후보 진행 상태: " + "; ".join(f"{k}={v}" for k, v in candidate_stages(state, c).items()), ""]
        if c.get("review"):
            lines += [f"검토 단계: {c['review']['stage']} / 이유: {c['review']['reason']}", ""]
        for key, title in RESEARCH_FLOW_FIELDS.items():
            lines += [f"### {title}", "", str(c.get("plan", {}).get(key) or "미정 — 추가 확인 필요"), ""]
        lines += ["### 연구 공백과 문헌 근거 연결", ""]
        missing_links = gap_errors(c, state)
        gaps = {gap["id"]: gap for gap in state["gaps"]}
        claims = {claim["id"]: claim for claim in state["claims"]}
        for gid in c.get("gap_ids", []):
            gap = gaps.get(gid)
            if gap is None:
                continue
            for cid in gap.get("claim_ids", []):
                for ref in claims.get(cid, {}).get("evidence", []):
                    lines.append(f"- {cell(gid)} → {cell(cid)} → {cell(ref.get('paper_id'))} / 버전 {cell(ref.get('version'))} / {cell(ref.get('location'))}")
        if missing_links:
            lines.extend(f"- 확인 과제: {issue}" for issue in missing_links)
            review = c.get("gap_review", {})
            lines.append(f"- 근거 부족 사유: {review.get('reason') or '미작성 — 확인한 부족 사유를 기록하세요.'}")
            lines.extend(f"- 다음 확인 작업: {action}" for action in review.get("next_actions", ["연구 공백·주장·실제 열람 문헌의 연결을 확인하세요."]))
        lines += ["### 평가 근거", "", "가중치: " + ", ".join(f"{k}={v}" for k, v in state['config']['weights'].items()), ""]
        for group, title, number_key in (("gates", "필수 조건", "status"), ("scores", "점수", "value")):
            for key, value in c.get(group, {}).items():
                src = value.get("evidence") or {}
                lines.append(f"- {title} {key}: {value.get(number_key, '미정')} / {value.get('reason', '근거 미정')} / 불확실성: {value.get('uncertainty', '별도 기록 없음')} / 출처: {src.get('url') or src.get('local_file') or '미확인'} / {src.get('location', '위치 미확인')}")
        for key, title in PLAN_FIELDS.items():
            if key in RESEARCH_FLOW_FIELDS:
                continue
            lines += [f"### {title}", "", str(c.get("plan", {}).get(key) or "미정 — 추가 확인 필요"), ""]
        novelty = c.get("novelty", {})
        lines += ["### 후보별 중복 검증", "", f"- 판정: {novelty.get('status', '미완료')}",
                  f"- 가장 가까운 문헌: {', '.join(novelty.get('closest_paper_ids', [])) or '미확인'}",
                  f"- 불확실성: {novelty.get('uncertainty', '미기재')}", "",
                  "<details><summary>축별 비교·근거 기록</summary>", "", "```json", json.dumps(novelty, ensure_ascii=False, indent=2), "```", "", "</details>", ""]
        for key in ("design", "provenance"):
            lines += [f"<details><summary>{key} 상세 기록</summary>", "", "```json", json.dumps(c.get(key), ensure_ascii=False, indent=2), "```", "", "</details>", ""]
        effect = (c.get("design") or {}).get("effect_plan") or {}
        lines += ["### 효과·표본·정밀도 판단", "", f"- 상태: {effect.get('status', '미작성')}"]
        if effect.get("status") == "quantitative":
            precision = effect["precision"]
            lines += [f"- 의미 있는 최소 효과: {effect['minimum_effect']} / {effect['metric']}",
                      f"- 독립 단위: {effect['unit']} / 필요 {effect['required_units']} / 확보 {effect['available_units']}",
                      f"- 판단 목표: {precision['kind']}={precision['target']} / 산정 근거: {effect['basis']}",
                      f"- 가정: {effect['assumptions']}"]
        elif effect.get("status") == "qualitative":
            lines += [f"- 판단 기준: {effect['criteria']}", f"- 사유·가정: {effect['reason']} / {effect['assumptions']}"]
        elif effect.get("status") == "pending":
            lines += [f"- 미산정 사유: {effect['reason']}", f"- 첫 주 측정: {effect['measurement_plan']}"]
        lines += ["", "### 파일럿 기반 자원 추정", ""]
        if c.get("pilot"):
            estimate = pilot_estimate(c['pilot'])
            lines += [f"상태: {estimate['status']} / 예상 전체 GPU시간: {cell(estimate.get('estimated_hours'))}", "",
                      "<details><summary>측정값·가정·계산식</summary>", "", "```json", json.dumps({"inputs": c['pilot'], "estimate": estimate}, ensure_ascii=False, indent=2), "```", "", "</details>", ""]
        else:
            lines += ["미측정 — 실제 GPU 측정 없이 수치를 확정하지 않습니다.", ""]
        comparison = resource_check(c, state)
        lines += ["### 자원과 사용 가능 시간 대조", "", "허용량은 사용자 확인 기간 × 주당 가용 시간으로 계산합니다.", "",
                  f"- GPU시간: 필요 {cell(comparison['gpu_hours_required'])} / 가용 {cell(comparison.get('gpu_hours_available'))}",
                  f"- 연구 작업시간: 필요 {cell(comparison['work_hours_required'])} / 가용 {cell(comparison.get('work_hours_available'))}"]
        lines.extend(f"- 확인 과제: {reason}" for reason in comparison["reasons"])
        lines += ["", "<details><summary>자원 산정 근거</summary>", "", "```json", json.dumps({"resource_plan": c.get("resource_plan"), "comparison": comparison}, ensure_ascii=False, indent=2), "```", "", "</details>", ""]
    lines += ["", "## 투고처", "", "| 연구 후보 | 저널·학술대회명 | 유형 | 회차·트랙 | 적합성 | 보강할 점 |", "|---|---|---|---|---|---|"]
    for j in state["journals"]:
        conference = j.get("category") == "conference"
        kind = "학술대회" if conference else "저널"
        edition_track = " / ".join(str(j[k]) for k in ("edition", "track") if j.get(k))
        edition_track = (edition_track or "확인 불가") if conference else "해당 없음"
        lines.append(f"| {cell(j['candidate_id'])} | {cell(j.get('name'))} | {kind} | {cell(edition_track)} | {cell(j.get('fit'))} | {cell(j.get('strengthening'))} |")
    field_labels = {"index": "색인", "cost": "비용", "schedule": "일정", "metrics": "지표", "guidelines": "투고 규정"}
    for j in state["journals"]:
        lines += ["", f"### {j.get('name', '투고처 미정')}", ""]
        identity = ("organizer", "edition", "track") if j.get("category") == "conference" else ("publisher", "issn")
        for k in ("url", *identity, "recommendation_stage", "related_papers", "article_type", "language_format", "data_code_ethics", "uncertainty"):
            lines.append(f"- {k}: {j.get(k, '확인 불가')}")
        for k in venue_fields(j):
            field = verified_field(j, k)
            lines.append(f"- {field_labels[k]}: {field['value']} / 확인일: {field['checked_at'] or '확인 불가'} / 출처: {field['source'] or '확인 불가'}")
            if k == "metrics" and field["source"]:
                lines.append(f"  - 기준 연도: {j[k]['year']}; 분류: {j[k]['category']}")
    lines += ["", "## 검색 범위와 이력", ""]
    coverage = search_coverage(state)
    lines += [f"실제 요청 {state['usage']['requests']}회 / 신규 채택 {state['usage']['results']}건 / 남은 요청 {coverage['remaining_requests']}회 / 남은 채택 {coverage['remaining_results']}건", "",
              "<details><summary>갈래별 집계·질의별 지속/종료 근거</summary>", "", "```json", json.dumps(coverage, ensure_ascii=False, indent=2), "```", "", "</details>", ""]
    for s in state["search_log"]:
        lines.append(f"- {s['id']} [{s.get('branch')}] {s.get('query')} / {s.get('provider')} / {s.get('since')}–{s.get('until')} / {s.get('status')} / {s.get('at')} / cache={s.get('cache_hit', False)} / {s.get('error', '')}")
    lines += ["", "## 투고처 재확인", "", "기본 90일의 확인일 점검과 구조화된 제출 일정 대조입니다. 최신 사실을 자동 조회한 결과가 아닙니다.", ""]
    for journal in recheck_journals(state, state.get("report", {}).get("as_of")):
        lines.append(f"- {journal['name']} (기준일 {journal['as_of']}): " + "; ".join(f"{key}={value['status']}" for key, value in journal['fields'].items()))
        submission = journal["submission"]
        lines += [f"  - 투고 일정: {submission['status']} / 준비 예정: {submission['ready_at'] or '미정'} / {submission['reason']}"]
        for deadline in submission["deadlines"]:
            lines.append(f"  - {deadline['id']} ({deadline['kind']}): {deadline['at']} [{deadline['timezone']}] / {deadline['timing']} / {deadline['readiness']}")
    if final_errors:
        lines += ["", "## 최종화 전 확인 과제", ""] + [f"- {error}" for error in final_errors]
    lines += ["", "검색 범위 밖의 노벨티, 게재 가능성 및 색인을 보증하지 않습니다.", ""]
    return "\n".join(lines)


def evidence_cards(state):
    lines = ["# 주장별 근거 카드", "", "테스트 자료" if state['test_data'] else "발췌·해석을 원문과 수동 대조하세요. 빈 항목은 확인되지 않았습니다.", ""]
    for claim in state['claims']:
        lines += [f"## {claim['id']}: {claim['text']}", "", f"- 유형: {claim['kind']}", f"- 해석: {claim.get('interpretation') or '미확인'}", f"- 미확인·불확실성: {claim.get('uncertainty') or '미기재'}", ""]
        for ref in claim.get('evidence', []):
            paper = next((p for p in state['papers'] if p['id'] == ref.get('paper_id')), {})
            version = evidence_version(ref, state) or {}
            locations = [version.get('read_evidence', {})] + version.get('read_locations', [])
            src = next((loc for loc in locations if isinstance(loc, dict) and loc.get('location') == ref.get('location')), version.get('source') or {})
            lines += [f"- 문헌: {ref.get('paper_id')} / 버전: {ref.get('version', '미확인')} / 버전 ID: {ref.get('version_id', paper.get('id'))}",
                      f"  - 위치·범위: {ref.get('location')} / {ref.get('scope')}",
                      f"  - 원문: {src.get('url') or src.get('local_file') or '미확인'}",
                      f"  - 짧은 발췌: {ref.get('excerpt') or '미확인'}",
                      f"  - 기록 대조: {'; '.join(evidence_errors(ref, state, excerpt=True)) or '통과 (내용 진위는 수동 대조 필요)'}", ""]
    return '\n'.join(lines) + '\n'


def bib_escape(value):
    mapping = {"\\": "\\textbackslash{}", "{": "\\{", "}": "\\}", "%": "\\%", "&": "\\&", "_": "\\_", "#": "\\#", "$": "\\$", "~": "\\textasciitilde{}", "^": "\\textasciicircum{}"}
    return "".join(mapping.get(c, c) for c in str(value).replace("\n", " "))


def bibliography(state, fmt):
    lines = []
    if state["test_data"]:
        lines.append("% TEST DATA — NOT REAL REFERENCES" if fmt == "bib" else "TY  - GEN\nTI  - TEST DATA — NOT REAL REFERENCES\nER  - \n")
    for i, p in enumerate(state["papers"], 1):
        if p.get("excluded"):
            continue
        if fmt == "bib":
            kind = "article" if p.get("publication_type") == "journal-article" else "misc"
            fields = {"title": p["title"], "author": " and ".join(p.get("authors", [])), "year": p.get("year"), "journal": p.get("venue"), "doi": p.get("doi"), "url": p.get("url")}
            lines.append(f"@{kind}{{ref{i},\n" + ",\n".join(f"  {k} = {{{bib_escape(v)}}}" for k, v in fields.items() if v) + "\n}")
        else:
            clean = lambda x: re.sub(r"[\r\n]+", " ", str(x))
            kind = "JOUR" if p.get("publication_type") == "journal-article" else "GEN"
            record = [f"TY  - {kind}", "TI  - " + clean(p["title"])]
            record += ["AU  - " + clean(a) for a in p.get("authors", [])]
            record += [f"{tag}  - {clean(p[key])}" for tag, key in (("PY", "year"), ("JO", "venue"), ("DO", "doi"), ("UR", "url")) if p.get(key)]
            lines.append("\n".join(record + ["ER  - ", ""]))
    return "\n\n".join(lines) + "\n"
