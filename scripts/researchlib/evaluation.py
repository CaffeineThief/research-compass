import math
from .literature import source_ok, evidence_errors, valid_id_list, validate_claims
from .state import CRITERIA, GATES, candidate_stages
from .planning import readiness_reasons

AXES = dict(zip(("problem", "method", "assumptions", "data", "evaluation", "contribution"), ("문제", "방법", "가정", "데이터", "평가", "기여")))


def gap_errors(candidate, state):
    gap_ids = candidate.get("gap_ids", [])
    if not valid_id_list(gap_ids) or not gap_ids:
        return ["gap_ids: 후보에서 근거가 연결된 연구 공백을 지정해야 함"]
    gaps = {gap["id"]: gap for gap in state["gaps"]}
    claims = {claim["id"]: claim for claim in state["claims"]}
    errors = []
    for gid in gap_ids:
        gap = gaps.get(gid)
        if gap is None:
            errors.append(f"gap_ids: 없는 연구 공백 {gid}")
            continue
        claim_ids = gap.get("claim_ids")
        if not valid_id_list(claim_ids) or not claim_ids:
            errors.append(f"gap {gid}: 근거 주장 ID 배열 필요")
            continue
        for cid in claim_ids:
            claim = claims.get(cid)
            if claim is None:
                errors.append(f"gap {gid}: 없는 근거 주장 {cid}")
                continue
            refs = claim.get("evidence")
            if not isinstance(refs, list) or not refs or any(not isinstance(ref, dict) for ref in refs):
                errors.append(f"gap {gid} / claim {cid}: 문헌 근거 배열 필요")
                continue
            errors.extend(validate_claims({"papers": state["papers"], "claims": [claim], "conflicts": []}))
            for ref in refs:
                errors.extend(f"gap {gid} / claim {cid}: {issue}" for issue in evidence_errors(ref, state))
    return errors


def novelty_errors(candidate, state):
    novelty = candidate.get("novelty", {})
    comparison = novelty.get("comparison")
    if not isinstance(comparison, dict):
        return ["노벨티: 근거를 연결한 6축 비교 필요"]
    errors, cited = [], set()
    for key, korean in AXES.items():
        axis = comparison.get(key, comparison.get(korean))
        if not isinstance(axis, dict) or not axis.get("difference") or not isinstance(axis.get("evidence"), list) or not axis["evidence"]:
            errors.append(f"노벨티 {key}: 차이와 근거 위치 필요")
            continue
        read_support = False
        for ref in axis["evidence"]:
            issues = evidence_errors(ref, state)
            errors.extend(f"노벨티 {key}: {e}" for e in issues)
            if not issues and ref.get("scope") in ("partial", "full_text"):
                read_support = True
                cited.add(ref.get("paper_id"))
        if not read_support:
            errors.append(f"노벨티 {key}: 비교할 본문 근거 필요")
    closest = novelty.get("closest_paper_ids", [])
    if not closest or any(pid not in cited for pid in closest):
        errors.append("가장 가까운 문헌의 본문과 비교 근거 확인 필요")
    return errors


def evaluate(candidate, state):
    reasons, conditional, failed = [], False, False
    if any(candidate_stages(state, candidate).get(s) == "stale" for s in ("search", "analysis", "gaps", "candidates", "novelty", "evaluation")):
        conditional = True
        reasons.append("관련 단계 변경 후 재검토 필요")
    for name in GATES:
        gate = candidate.get("gates", {}).get(name, {})
        status = gate.get("status", "unknown")
        if status not in ("pass", "fail", "unknown"):
            raise ValueError(f"{name}: gate 상태는 pass/fail/unknown")
        if status == "fail":
            failed = True
            reasons.append(f"필수 조건 실패: {name}: {gate.get('reason', '근거 미기재')}")
        elif status != "pass" or not gate.get("reason") or not source_ok(gate.get("evidence")):
            conditional = True
            reasons.append(f"필수 조건 미확인: {name}")
    novelty = candidate.get("novelty", {})
    searches = {s["id"]: s for s in state["search_log"]}
    search_ids = novelty.get("search_ids", [])
    checked = bool(search_ids) and all(s in searches and searches[s].get("status") == "ok" and searches[s].get("branch") == "novelty" for s in search_ids)
    if novelty.get("status") == "duplicate":
        failed = True
        reasons.append("후보별 재검색에서 차별성 부족")
    elif novelty.get("status") != "distinct_within_scope" or not checked or not novelty.get("comparison") or not novelty.get("uncertainty"):
        conditional = True
        reasons.append("후보별 노벨티 재검색/비교 미완료")
    missing = novelty_errors(candidate, state)
    if missing:
        conditional = True
        reasons.extend(missing)
    readiness = readiness_reasons(candidate, state)
    if readiness:
        conditional = True
        reasons.extend(readiness)
    missing_links = gap_errors(candidate, state)
    if missing_links:
        conditional = True
        reasons.extend(missing_links)
        if not candidate.get("gap_review"):
            reasons.append("gap_review: 근거 부족 사유와 다음 확인 작업을 기록해야 함")
    papers = {p["id"] for p in state["papers"] if not p.get("excluded")}
    closest = novelty.get("closest_paper_ids", [])
    if not closest or set(closest) - papers:
        conditional = True
        reasons.append("가장 가까운 선행 연구를 확인해야 함")
    conflict_ids = set(candidate.get("conflict_ids", []))
    conflicts = {c["id"]: c for c in state["conflicts"]}
    if any(c not in conflicts or conflicts[c].get("status") != "resolved" for c in conflict_ids):
        conditional = True
        reasons.append("관련 주장 충돌이 미해결: 검증 계획 필요")
    score, total, complete = 0, 0, True
    for name in CRITERIA:
        if state["config"]["weights"][name] == 0:
            continue
        value = candidate.get("scores", {}).get(name, {})
        n = value.get("value")
        if n is not None and (isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or not 0 <= n <= 5):
            raise ValueError(f"{name}: 점수는 0~5 또는 null")
        if n is None or not value.get("reason") or not value.get("uncertainty") or not source_ok(value.get("evidence")):
            complete = False
            continue
        weight = state["config"]["weights"][name]
        score += n * weight
        total += weight
    if not complete:
        conditional = True
        reasons.append("평가 점수의 근거/불확실성 미완료")
    return {"id": candidate["id"], "status": "rejected" if failed else "conditional" if conditional else "passed",
            "score": round(score / total, 2) if complete and total else None, "reasons": reasons}


def rank(state):
    result = [evaluate(c, state) for c in state["candidates"]]
    order = {"passed": 0, "conditional": 1, "rejected": 2}
    return sorted(result, key=lambda x: (order[x["status"]], -(x["score"] if x["score"] is not None else -1)))
