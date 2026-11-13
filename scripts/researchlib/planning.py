"""Research readiness records and estimates from measured pilot inputs."""
import math
from .literature import source_ok

DESIGN_FIELDS = ("primary_comparison", "primary_outcome", "independent_unit", "controls", "uncertainty", "budget_rationale")
WEEK_CATEGORIES = ("data", "environment", "minimum_experiment", "measurement", "decision")


def number(record, key, positive=True, integer=False):
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (value <= 0 if positive else value < 0) or (integer and not isinstance(value, int)):
        raise ValueError(f"{key}: {'양의' if positive else '0 이상의'} 유한 {'정수' if integer else '수'} 필요")
    return value


def pilot_estimate(pilot):
    if not isinstance(pilot, dict):
        raise ValueError("pilot: 객체 필요")
    status = pilot.get("status")
    if status in ("pending", "not_applicable"):
        if not pilot.get("reason") or (status == "pending" and not pilot.get("measurement_plan")):
            raise ValueError("pilot: 미측정/해당 없음 사유와 측정 계획 필요")
        return {"status": status, "estimated_hours": None, "reason": pilot["reason"]}
    if status != "measured":
        raise ValueError("pilot.status: measured/pending/not_applicable 필요")
    for key in ("hardware", "precision", "input_shape", "assumptions"):
        if not pilot.get(key):
            raise ValueError(f"pilot.{key}: 측정 조건 필요")
    if not source_ok(pilot.get("source")):
        raise ValueError("pilot.source: 실제 측정 로그 위치와 날짜 필요")
    values = {key: number(pilot, key, integer=True) for key in ("batch_size", "dataset_size", "steps_per_run", "runs", "measured_steps")}
    elapsed = number(pilot, "elapsed_seconds")
    peak = number(pilot, "peak_memory_gib")
    capacity = number(pilot, "available_memory_gib")
    overhead = number(pilot, "overhead_fraction", positive=False)
    seconds_per_step = elapsed / values["measured_steps"]
    hours = seconds_per_step * values["steps_per_run"] * values["runs"] * (1 + overhead) / 3600
    if not math.isfinite(hours):
        raise ValueError("pilot: 계산 가능한 범위를 초과한 시간")
    return {"status": "estimated_from_pilot", "estimated_hours": round(hours, 4),
            "seconds_per_step": seconds_per_step, "samples_per_second": values["measured_steps"] * values["batch_size"] / elapsed,
            "epochs_per_run": values["steps_per_run"] * values["batch_size"] / values["dataset_size"],
            "total_steps": values["steps_per_run"] * values["runs"], "memory_fits": peak <= capacity,
            "memory_headroom_gib": capacity - peak,
            "formula": "elapsed_seconds / measured_steps * steps_per_run * runs * (1 + overhead_fraction) / 3600",
            "assumptions": pilot["assumptions"]}


def planning_errors(candidate, final=False):
    errors = []
    for key in ("pilot", "design", "provenance"):
        value = candidate.get(key)
        if value is None and not final:
            continue
        if not isinstance(value, dict):
            errors.append(f"{key}: 기록 객체 필요")
            continue
        if key == "pilot":
            try:
                pilot_estimate(value)
            except ValueError as exc:
                errors.append(str(exc))
            continue
        if value.get("status") == "not_applicable":
            if not value.get("reason"):
                errors.append(f"{key}: 해당 없음 사유 필요")
            continue
        if key == "design":
            for field in DESIGN_FIELDS:
                if not isinstance(value.get(field), str) or not value[field].strip():
                    errors.append(f"design.{field}: 연구 설계 설명 필요")
            if value.get("matched_budget") not in ("steps", "gpu_time", "other"):
                errors.append("design.matched_budget: steps/gpu_time/other 필요")
            try:
                number(value, "repeated_runs", integer=True)
            except ValueError as exc:
                errors.append("design." + str(exc))
        else:
            assets = value.get("assets")
            if not isinstance(assets, list) or not assets:
                errors.append("provenance.assets: 데이터/체크포인트 이력 배열 필요")
                continue
            ids = set()
            for asset in assets:
                if not isinstance(asset, dict):
                    errors.append("provenance.assets: 객체 필요")
                    continue
                aid = asset.get("id")
                if not isinstance(aid, str) or not aid or aid in ids:
                    errors.append("provenance.assets: 고유 ID 필요")
                if isinstance(aid, str):
                    ids.add(aid)
                if asset.get("kind") not in ("dataset", "checkpoint"):
                    errors.append(f"asset {aid}: dataset/checkpoint 필요")
                for field in ("name", "version", "identifier_strategy", "split", "pretraining_exposure"):
                    if not isinstance(asset.get(field), str) or not asset[field].strip():
                        errors.append(f"asset {aid}.{field}: 내용 또는 미확인 범위 필요")
                if not source_ok(asset.get("source")):
                    errors.append(f"asset {aid}: 출처 필요")
                for field, statuses in (("rights", ("verified", "unknown", "restricted")), ("leakage", ("passed", "pending", "failed"))):
                    item = asset.get(field)
                    if not isinstance(item, dict) or item.get("status") not in statuses or not item.get("reason"):
                        errors.append(f"asset {aid}.{field}: 상태와 사유 필요")
                    elif item["status"] in ("verified", "passed", "failed") and not source_ok(item.get("source")):
                        errors.append(f"asset {aid}.{field}: 검증 기록 필요")
    tasks = candidate.get("first_week")
    if tasks is not None or final:
        if not isinstance(tasks, list) or not tasks:
            errors.append("first_week: 첫 주 작업 배열 필요")
        else:
            categories, ids = set(), set()
            for task in tasks:
                if not isinstance(task, dict):
                    errors.append("first_week: 작업 객체 필요")
                    continue
                tid = task.get("id")
                if not isinstance(tid, str) or not tid or tid in ids:
                    errors.append("first_week: 고유 작업 ID 필요")
                if isinstance(tid, str):
                    ids.add(tid)
                if isinstance(task.get("category"), str):
                    categories.add(task["category"])
                if task.get("category") not in WEEK_CATEGORIES or not task.get("text") or not isinstance(task.get("done"), bool):
                    errors.append("first_week: category/text/done 필요")
                day = task.get("day")
                if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= 7:
                    errors.append("first_week.day: 1~7 정수 필요")
                if task.get("done") and not source_ok(task.get("evidence")):
                    errors.append("first_week: 완료 작업의 확인 근거 필요")
            if final and set(WEEK_CATEGORIES) - categories:
                errors.append("first_week: 데이터·환경·최소 실험·측정·결정 작업 필요")
    return errors


def readiness_reasons(candidate):
    """Unknown readiness remains conditional; a report can still document it."""
    reasons = planning_errors(candidate)
    pilot = candidate.get("pilot", {})
    if isinstance(pilot, dict):
        if pilot.get("status") == "pending":
            reasons.append("파일럿 실측 대기")
        elif pilot.get("status") == "measured":
            try:
                if not pilot_estimate(pilot)["memory_fits"]:
                    reasons.append("측정 최대 메모리가 가용 메모리를 초과함")
            except ValueError:
                pass
    provenance = candidate.get("provenance", {})
    if isinstance(provenance, dict) and isinstance(provenance.get("assets", []), list):
        for asset in provenance.get("assets", []):
            if not isinstance(asset, dict):
                continue
            rights, leakage = asset.get("rights"), asset.get("leakage")
            if isinstance(rights, dict) and isinstance(leakage, dict) and (rights.get("status") != "verified" or leakage.get("status") != "passed"):
                reasons.append(f"asset {asset.get('id')}: 이용권/누출 확인 미완료")
    return reasons


def week_checklist(state, candidate_id=None):
    selected = [c for c in state["candidates"] if c["id"] == candidate_id] if candidate_id else [c for c in state["candidates"] if c["id"] in state.get("report", {}).get("selected_candidate_ids", [])]
    if candidate_id and not selected:
        raise ValueError("후보 ID를 찾을 수 없습니다.")
    lines = ["# 첫 주 실행 체크리스트", "", "테스트 자료" if state["test_data"] else "완료 표시는 확인 근거가 있는 작업에만 사용합니다.", ""]
    if not selected:
        lines += ["후보를 --candidate로 선택하거나 report.selected_candidate_ids에 지정하세요."]
    for candidate in selected:
        lines += [f"## {candidate['id']}: {candidate['title']}", ""]
        tasks = candidate.get("first_week", [])
        if not tasks:
            lines += ["작업 미작성 — 계획의 데이터 확보·환경 준비·최소 실험·자원 측정·중단 기준을 구체적인 작업으로 기록하세요."]
        for task in tasks:
            lines.append(f"- [{'x' if task['done'] else ' '}] Day {task['day']} / {task['category']}: {task['text']}")
            if task.get("evidence"):
                src = task["evidence"]
                lines.append(f"  - 확인: {src.get('url') or src.get('local_file')} / {src.get('location')} / {src.get('checked_at')}")
    return "\n".join(lines) + "\n"
