import copy
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

CRITERIA = ("novelty", "importance", "relevance", "feasibility", "evaluation", "reproducibility", "venue_fit")
GATES = ("data", "resources", "falsifiable", "baseline", "ethics_rights")
STAGES = ("search", "analysis", "gaps", "candidates", "novelty", "evaluation", "plan", "journals")
PROFILE = ("field", "population", "purpose", "duration", "team", "experience", "compute", "budget", "data", "data_restrictions", "contribution", "language", "index_target", "open_access", "apc_budget", "deadline", "read_papers", "excluded_topics", "preferred_journals", "preferred_venues", "resource_budget", "timezone")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_state(topic, test_data=False):
    if not topic.strip():
        raise ValueError("관심 주제가 필요합니다.")
    return {
        "schema_version": 1, "topic": topic, "test_data": test_data,
        "created_at": now(), "profile": dict.fromkeys(PROFILE),
        "config": {"recent_years": 5, "max_requests": 20, "max_results": 100,
                   "max_seconds": 900, "request_timeout": 15, "cache_hours": 24,
                   "max_agent_calls": 7, "max_parallel_agents": 3,
                   "weights": dict.fromkeys(CRITERIA, 1)},
        "usage": {"requests": 0, "results": 0, "agent_calls": 0, "seconds": 0},
        "capabilities": {}, "search_plan": {}, "search_log": [],
        "papers": [], "claims": [], "conflicts": [], "gaps": [],
        "agent_reviews": [], "candidates": [], "journals": [],
        "stages": {s: "pending" for s in STAGES}, "changes": []
    }


def load(path):
    state = json.loads(Path(path).read_text(encoding="utf-8"))
    if state.get("schema_version") != 1:
        raise ValueError("지원하지 않는 schema_version")
    if not isinstance(state.get("test_data"), bool):
        raise ValueError("test_data는 명시적인 boolean이어야 합니다.")
    validate_config(state["config"])
    return state


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement preserves the previous checkpoint on interrupted writes.
    fd, name = tempfile.mkstemp(prefix=".research-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def validate_config(config):
    for key in ("recent_years", "max_requests", "max_results", "max_seconds", "request_timeout", "cache_hours", "max_agent_calls", "max_parallel_agents"):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"config.{key}: 양의 유한 수가 필요합니다.")
    for key in ("recent_years", "max_requests", "max_results", "max_agent_calls", "max_parallel_agents"):
        if not isinstance(config[key], int):
            raise ValueError(f"config.{key}: 정수가 필요합니다.")
    weights = config["weights"]
    if set(weights) != set(CRITERIA):
        raise ValueError("평가 가중치의 기준이 일치하지 않습니다.")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("가중치는 0 이상이며 합계가 양수여야 합니다.")


def invalidate(state, stage, reason, candidate_ids=None):
    targets = [state]
    if candidate_ids is not None:
        known = {c["id"]: c for c in state["candidates"]}
        if not candidate_ids or set(candidate_ids) - known.keys():
            raise ValueError("재검토할 후보 ID를 확인하세요.")
        targets = [known[cid] for cid in candidate_ids]
    for target in targets:
        stages = target.setdefault("stages", {})
        for name in STAGES[STAGES.index(stage):]:
            stages[name] = "stale"
    state["changes"].append({"at": now(), "from": stage, "reason": reason,
                             "candidate_ids": candidate_ids})


def candidate_stages(state, candidate):
    # A local completion cannot erase a global invalidation.
    local = candidate.get("stages", {})
    return {name: "stale" if state["stages"].get(name) == "stale" else local.get(name, state["stages"].get(name, "pending"))
            for name in STAGES}


def progress_stages(state):
    progress = dict(state["stages"])
    for candidate in state["candidates"]:
        for name, status in candidate_stages(state, candidate).items():
            if status == "stale":
                progress[name] = "stale"
    return progress


def update_profile(state, patch):
    if not isinstance(patch, dict) or set(patch) - set(PROFILE):
        raise ValueError("알 수 없는 사용자 조건입니다.")
    if patch.get("timezone") is not None:
        from .journals import zone
        zone(patch["timezone"])
    if "resource_budget" in patch:
        from .planning import resource_budget
        resource_budget(patch)
    changed = {k for k, v in patch.items() if state["profile"].get(k) != v}
    if not changed:
        return
    state["profile"].update(copy.deepcopy(patch))
    stage = "evaluation"
    if changed & {"field", "population", "excluded_topics", "contribution", "purpose", "data", "data_restrictions"}:
        stage = "search"
    invalidate(state, stage, "사용자 조건 변경: " + ", ".join(sorted(changed)))


def reserve_agents(state, count):
    if count < 1 or state["usage"]["agent_calls"] + count > state["config"]["max_agent_calls"]:
        raise ValueError("에이전트 호출 상한입니다. 남은 역할은 순차 수행하거나 범위를 줄이세요.")
    state["usage"]["agent_calls"] += count
