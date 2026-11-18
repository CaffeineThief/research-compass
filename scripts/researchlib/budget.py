"""Search admission shared by the CLI and host-managed web tools."""
import copy
import hashlib
import json
import uuid

from .state import now


def remaining_results(state):
    return max(0, state["config"]["max_results"] - state["usage"]["results"])


def check_search_budget(state):
    if any(s.get("status") == "pending" for s in state["search_log"]):
        raise ValueError("예약된 검색을 record-search로 완료한 뒤 다음 검색을 시작하세요.")
    if state["usage"]["requests"] >= state["config"]["max_requests"]:
        raise ValueError("검색 요청 상한에 도달했습니다.")
    if state["usage"]["seconds"] >= state["config"]["max_seconds"]:
        raise ValueError("실행 시간 상한에 도달했습니다.")
    if remaining_results(state) == 0:
        raise ValueError("검색 결과 상한에 도달했습니다.")


def admit_results(state, results, limit):
    if not isinstance(results, list):
        raise ValueError("results는 검색 결과 배열이어야 합니다.")
    accepted = results[:min(limit, remaining_results(state))]
    state["usage"]["results"] += len(accepted)
    return accepted


def reserve_search(state, query, branch, provider, limit):
    if not query.strip() or not provider.strip() or branch not in ("recent", "foundational", "validation", "novelty"):
        raise ValueError("검색어, 제공처, 유효한 탐색 갈래가 필요합니다.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("검색당 결과 수는 1~100입니다.")
    check_search_budget(state)
    allocation = search_coverage(state)["branches"][branch]
    entry = {
        "id": "search-" + uuid.uuid4().hex, "query": query, "branch": branch,
        "provider": provider, "limit": min(limit, remaining_results(state)),
        "at": now(), "status": "pending", "test_data": state["test_data"],
        "count": 0, "paper_ids": [], "cache_hit": False,
        "request_count": 1, "admitted_count": 0, "reused_count": 0
    }
    entry["allocation_advice"] = allocation
    state["usage"]["requests"] += 1
    state["search_log"].append(entry)
    return entry


def record_search(state, search_id, payload):
    if not isinstance(payload, dict):
        raise ValueError("검색 응답 JSON 객체가 필요합니다.")
    results = payload.get("results", [])
    if not isinstance(results, list) or any(not isinstance(r, dict) for r in results):
        raise ValueError("results는 결과 객체의 배열이어야 합니다.")
    if payload.get("error") and results:
        raise ValueError("실패 응답에는 results를 비워 주세요.")
    entry = next((s for s in state["search_log"] if s["id"] == search_id), None)
    if entry is None:
        raise ValueError("검색 예약 ID를 찾을 수 없습니다.")
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if entry.get("response_hash") == fingerprint:
        return entry
    if entry.get("status") != "pending":
        raise ValueError("이미 완료된 검색입니다. 다른 응답으로 덮어쓸 수 없습니다.")
    accepted = admit_results(state, results, entry["limit"])
    entry.update(
        status="failed" if payload.get("error") else "ok",
        error=payload.get("error"), results=copy.deepcopy(accepted),
        received_count=len(results), discarded_count=len(results) - len(accepted),
        count=len(accepted), admitted_count=len(accepted), completed_at=now(), response_hash=fingerprint
    )
    return entry


def review_search(state, search_id, review):
    entry = next((s for s in state["search_log"] if s["id"] == search_id), None)
    if entry is None or entry.get("status") not in ("ok", "failed"):
        raise ValueError("완료된 검색 ID가 필요합니다.")
    validate_review(state, review)
    entry["review"] = copy.deepcopy(review)
    return entry


def validate_review(state, review):
    if (not isinstance(review, dict) or review.get("action") not in ("continue", "stop")
            or not isinstance(review.get("reason"), str) or not review["reason"].strip()
            or not isinstance(review.get("unresolved_questions"), list)
            or any(not isinstance(q, str) or not q.strip() for q in review["unresolved_questions"])):
        raise ValueError("검색 검토: continue/stop, 이유, 남은 질문 배열 필요")
    from .literature import valid_id_list
    ids = review.get("relevant_paper_ids")
    known = {p["id"] for p in state["papers"] if not p.get("excluded")}
    if not valid_id_list(ids) or set(ids) - known:
        raise ValueError("검색 검토: 실제 채택 문헌의 고유 relevant_paper_ids 배열 필요")


def accounting(entry):
    cached = bool(entry.get("cache_hit"))
    values = {
        "requests": entry.get("request_count", 0 if cached else 1),
        "admitted": entry.get("admitted_count", 0 if cached else entry.get("count", 0)),
        "reused": entry.get("reused_count", entry.get("count", 0) if cached else 0),
    }
    for key, value in values.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"search {entry.get('id')}.{key}: 0 이상 정수 필요")
    return values


BRANCHES = ("recent", "foundational", "validation", "novelty")
DEFAULT_ALLOCATION = dict(zip(BRANCHES, (0.3, 0.2, 0.2, 0.3)))


def search_coverage(state):
    """Advisory allocation; global limits remain the hard admission boundary."""
    import math
    plan = state.get("search_plan", {})
    allocation = plan.get("allocation", DEFAULT_ALLOCATION)
    if not isinstance(allocation, dict) or set(allocation) != set(BRANCHES) or any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0 for v in allocation.values()) or not math.isclose(sum(allocation.values()), 1):
        raise ValueError("search_plan.allocation: 네 갈래의 비율 합은 1이어야 합니다.")
    rows, seen = {}, set()
    for branch in BRANCHES:
        logs = [s for s in state["search_log"] if s.get("branch") == branch]
        paid = [s for s in logs if accounting(s)["requests"]]
        rows[branch] = {"requests": sum(accounting(s)["requests"] for s in logs), "admitted": sum(accounting(s)["admitted"] for s in logs),
                        "reused": sum(accounting(s)["reused"] for s in logs),
                        "received": sum(s.get("received_count", s.get("count", 0)) for s in logs),
                        "discarded": sum(s.get("discarded_count", 0) for s in logs),
                        "cache_hits": sum(bool(s.get("cache_hit")) for s in logs),
                        "failures": sum(s.get("status") == "failed" for s in logs),
                        "zero_hit_searches": sum(s.get("status") == "ok" and s.get("count", 0) == 0 for s in logs),
                        "target_requests": math.floor(state["config"]["max_requests"] * allocation[branch]),
                        "target_results": math.floor(state["config"]["max_results"] * allocation[branch])}
    duplicates, identified, unidentified = 0, 0, 0
    aliases = {}
    for paper in state["papers"]:
        for alias in [paper["id"], paper.get("doi")] + paper.get("aliases", []):
            if alias:
                aliases[str(alias).casefold()] = paper["id"]
    for search in state["search_log"]:
        if not accounting(search)["admitted"] or search.get("status") != "ok":
            continue
        records = search.get("results", [])
        keys = [(r.get("doi") or r.get("paper_id") or r.get("url")) for r in records] if records else search.get("paper_ids", [])
        unidentified += max(0, search.get("count", 0) - len(keys))
        for key in keys:
            if not key:
                unidentified += 1
                continue
            key = str(key).casefold().removeprefix("https://doi.org/").removeprefix("doi:").rstrip("/")
            key = aliases.get(key, key)
            identified += 1
            duplicates += key in seen
            seen.add(key)
    available_requests = max(0, state["config"]["max_requests"] - state["usage"]["requests"])
    available_results = remaining_results(state)
    for branch, row in rows.items():
        reserve_requests = sum(max(0, rows[b]["target_requests"] - rows[b]["requests"]) for b in ("validation", "novelty") if b != branch)
        reserve_results = sum(max(0, rows[b]["target_results"] - rows[b]["admitted"]) for b in ("validation", "novelty") if b != branch)
        row["suggested_requests_available"] = max(0, available_requests - reserve_requests)
        row["suggested_results_available"] = max(0, available_results - reserve_results)
    queries, relevant_seen = [], set()
    for entry in state["search_log"]:
        review = entry.get("review")
        if review is not None:
            validate_review(state, review)
        relevant = set(review.get("relevant_paper_ids", [])) if review else set()
        queries.append({"id": entry["id"], "query": entry.get("query"), **accounting(entry),
                        "new_relevant": len(relevant - relevant_seen) if review else None,
                        "action": review.get("action") if review else "review_needed",
                        "reason": review.get("reason") if review else "관련성·남은 질문 검토 필요",
                        "unresolved_questions": review.get("unresolved_questions") if review else None})
        relevant_seen.update(relevant)
    return {"allocation_mode": "advisory", "queries": queries,
            "legacy_cache_accounting_unknown": [s["id"] for s in state["search_log"] if s.get("cache_hit") and "admitted_count" not in s],
            "novelty_caution": "신규·관련 결과 0건과 검색 종료는 노벨티의 증명이 아닙니다.", "branches": rows, "duplicate_occurrences": duplicates,
            "identified_occurrences": identified, "unidentified_occurrences": unidentified,
            "duplicate_method": "Exact DOI/URL/paper-ID identity; unresolved versions and URL aliases can be missed.",
            "unreviewed_branches": [b for b in BRANCHES if not any(s.get('branch') == b and s.get('status') == 'ok' for s in state['search_log'])],
            "unreviewed_areas": plan.get("unreviewed_areas", []),
            "remaining_requests": available_requests, "remaining_results": available_results}
