"""Research readiness records and estimates from measured pilot inputs."""
import math
from .literature import source_ok, valid_id_list

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
        if (not isinstance(pilot.get("reason"), str) or not pilot["reason"].strip()
                or (status == "pending" and (not isinstance(pilot.get("measurement_plan"), str)
                                             or not pilot["measurement_plan"].strip()))):
            raise ValueError("pilot: 미측정/해당 없음 사유와 측정 계획 필요")
        return {"status": status, "estimated_hours": None, "reason": pilot["reason"]}
    if status != "measured":
        raise ValueError("pilot.status: measured/pending/not_applicable 필요")
    if "conditions" in pilot:
        conditions = pilot["conditions"]
        if (not isinstance(conditions, list) or not conditions
                or any(not isinstance(c, dict) or c.get("status") != "measured" or "conditions" in c for c in conditions)
                or not valid_id_list([c.get("id") for c in conditions])):
            raise ValueError("pilot.conditions: 고유 ID가 있는 측정 조건 배열 필요")
        estimates = [{"id": c["id"], **pilot_estimate(c)} for c in conditions]
        hours = sum(e["estimated_hours"] for e in estimates)
        if not math.isfinite(hours):
            raise ValueError("pilot: 계산 가능한 범위를 초과한 시간")
        return {"status": "estimated_from_pilot", "estimated_hours": hours,
                "runs": sum(e["runs"] for e in estimates), "conditions": estimates,
                "total_steps": sum(e["total_steps"] for e in estimates),
                "memory_fits": all(e["memory_fits"] for e in estimates),
                "memory_headroom_gib": min(e["memory_headroom_gib"] for e in estimates)}
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
    evaluation = number({"evaluation_hours": pilot.get("evaluation_hours", 0)}, "evaluation_hours", positive=False)
    setup = number({"setup_hours": pilot.get("setup_hours", 0)}, "setup_hours", positive=False)
    seconds_per_step = elapsed / values["measured_steps"]
    training = seconds_per_step * values["steps_per_run"] * values["runs"] * (1 + overhead) / 3600
    hours = training + evaluation + setup
    if not math.isfinite(hours):
        raise ValueError("pilot: 계산 가능한 범위를 초과한 시간")
    return {"status": "estimated_from_pilot", "estimated_hours": hours, "runs": values["runs"],
            "training_hours": training, "evaluation_hours": evaluation, "setup_hours": setup,
            "seconds_per_step": seconds_per_step, "samples_per_second": values["measured_steps"] * values["batch_size"] / elapsed,
            "epochs_per_run": values["steps_per_run"] * values["batch_size"] / values["dataset_size"],
            "total_steps": values["steps_per_run"] * values["runs"], "memory_fits": peak <= capacity,
            "memory_headroom_gib": capacity - peak,
            "formula": "elapsed_seconds / measured_steps * steps_per_run * runs * (1 + overhead_fraction) / 3600 + evaluation_hours + setup_hours",
            "assumptions": pilot["assumptions"]}


def resource_budget(profile):
    budget = profile.get("resource_budget")
    if budget is None:
        return {"status": "pending", "reason": "연구 기간과 주당 가용 시간을 확인해야 함"}
    if not isinstance(budget, dict):
        raise ValueError("resource_budget: 객체 필요")
    if budget.get("status") == "pending":
        if any(not isinstance(budget.get(key), str) or not budget[key].strip() for key in ("reason", "measurement_plan")):
            raise ValueError("resource_budget: 미확인 사유와 확인 계획 필요")
        return budget
    if budget.get("status") != "confirmed" or not source_ok(budget.get("source")):
        raise ValueError("resource_budget: confirmed/pending 상태와 사용자 확인 출처 필요")
    weeks = number(budget, "weeks")
    capacities = {}
    for key in ("gpu", "work"):
        weekly = budget.get(key + "_hours_per_week")
        capacity = weeks * number({"hours": weekly}, "hours", positive=False) if weekly is not None else None
        if capacity is not None and not math.isfinite(capacity):
            raise ValueError("resource_budget: 계산 가능한 범위를 초과한 가용 시간")
        capacities[key + "_hours_available"] = capacity
    return {"status": "confirmed", "weeks": weeks, **capacities}


def work_estimate(plan):
    if not isinstance(plan, dict):
        raise ValueError("resource_plan: 예상 연구 작업량 기록 필요")
    if plan.get("status") == "pending":
        if any(not isinstance(plan.get(key), str) or not plan[key].strip() for key in ("reason", "measurement_plan")):
            raise ValueError("resource_plan: 미산정 사유와 측정 계획 필요")
        return None
    if (plan.get("status") != "estimated" or not isinstance(plan.get("assumptions"), str)
            or not plan["assumptions"].strip() or not source_ok(plan.get("source"))):
        raise ValueError("resource_plan: estimated/pending 상태, 작업량 가정과 출처 필요")
    return number(plan, "work_hours", positive=False)


def effect_check(design, final=False):
    plan = design.get("effect_plan") if isinstance(design, dict) else None
    if plan is None:
        if final:
            raise ValueError("design.effect_plan: 효과·표본·정밀도 또는 분야별 판단 기준 필요")
        return ["효과·표본·정밀도 계획 미작성"]
    if not isinstance(plan, dict):
        raise ValueError("design.effect_plan: 객체 필요")
    status = plan.get("status")
    if status == "pending":
        if any(not isinstance(plan.get(k), str) or not plan[k].strip() for k in ("reason", "measurement_plan")):
            raise ValueError("effect_plan: 미산정 사유와 파일럿에서 측정할 작업 필요")
        return ["효과·표본 계획 확인 대기: " + plan["measurement_plan"]]
    if status == "qualitative":
        if any(not isinstance(plan.get(k), str) or not plan[k].strip() for k in ("reason", "criteria", "assumptions")) or not source_ok(plan.get("source")):
            raise ValueError("effect_plan: 정성·이론 연구의 사유·판단 기준·가정·출처 필요")
        return []
    if status != "quantitative":
        raise ValueError("effect_plan.status: quantitative/qualitative/pending 필요")
    for key in ("metric", "unit", "basis", "assumptions"):
        if not isinstance(plan.get(key), str) or not plan[key].strip():
            raise ValueError(f"effect_plan.{key}: 기준값의 근거·단위·가정 필요")
    if not source_ok(plan.get("source")):
        raise ValueError("effect_plan.source: 기준·표본 산정의 근거 필요")
    if plan["unit"] != design.get("independent_unit"):
        raise ValueError("effect_plan.unit: design.independent_unit과 일치해야 함; 영상·환자·실행 단위를 구분하세요.")
    number(plan, "minimum_effect")
    required = number(plan, "required_units", integer=True)
    available = number(plan, "available_units", integer=True, positive=False)
    precision = plan.get("precision")
    if not isinstance(precision, dict) or precision.get("kind") not in ("ci_half_width", "power", "simulation"):
        raise ValueError("effect_plan.precision: ci_half_width/power/simulation과 target 필요")
    target = number(precision, "target")
    if precision["kind"] == "power" and target >= 1:
        raise ValueError("effect_plan.precision: power는 0과 1 사이")
    if precision["kind"] in ("ci_half_width", "power"):
        level = number(precision, "level")
        if level >= 1:
            raise ValueError("effect_plan.precision.level: 신뢰수준 또는 alpha는 0과 1 사이")
    reasons = []
    if available < required:
        reasons.append(f"독립 표본 부족: 확보 {available:g} / 필요 {required:g} {plan['unit']}")
    if "required_repeated_runs" in plan:
        repeats = number(plan, "required_repeated_runs", integer=True)
        if design.get("repeated_runs", 0) < repeats:
            reasons.append("효과 계획에 필요한 반복 수보다 설계의 반복 수가 적음")
    if "events" in plan:
        events = plan["events"]
        if not isinstance(events, dict) or not isinstance(events.get("unit"), str) or not events["unit"].strip():
            raise ValueError("effect_plan.events: 사건 단위·required·available 필요")
        needed = number(events, "required", integer=True, positive=False)
        count = number(events, "available", integer=True, positive=False)
        if count < needed:
            reasons.append(f"사건 수 부족: 확보 {count:g} / 필요 {needed:g} {events['unit']}")
    return reasons


def resource_check(candidate, state):
    capacity = resource_budget(state["profile"])
    design = candidate.get("design") or {}
    reasons = effect_check(design)
    effect = design.get("effect_plan") or {}
    work_hours = work_estimate(candidate["resource_plan"]) if candidate.get("resource_plan") is not None else None
    if capacity["status"] == "pending":
        reasons.append("연구 기간·주당 가용 시간 미확인: " + capacity["reason"])
    work_available = capacity.get("work_hours_available")
    if work_hours is None:
        reasons.append("연구 작업시간 산정 필요: resource_plan에 작업량과 확인 계획을 기록하세요.")
    elif work_available is None:
        reasons.append("주당 연구 작업시간 확인 필요")
    elif work_hours > work_available:
        reasons.append(f"연구 작업시간 초과: 예상 {work_hours:g}시간 / 가용 {work_available:g}시간")
    pilot = candidate.get("pilot")
    estimate = pilot_estimate(pilot) if isinstance(pilot, dict) else None
    gpu_hours = None
    if estimate is None:
        reasons.append("pilot: 실행 준비 기록 미확인")
    elif estimate["status"] == "pending":
        reasons.append("파일럿 실측 대기: " + estimate["reason"])
    if estimate and estimate["status"] == "estimated_from_pilot":
        gpu_hours = estimate["estimated_hours"]
        available = capacity.get("gpu_hours_available")
        if available is None:
            reasons.append("주당 GPU 가용 시간 확인 필요")
        elif gpu_hours > available:
            reasons.append(f"GPU 시간 초과: 예상 {gpu_hours:g}시간 / 가용 {available:g}시간")
        if not estimate["memory_fits"]:
            reasons.append("측정 최대 메모리가 가용 메모리를 초과함")
        design = candidate.get("design")
        if not isinstance(design, dict) or design.get("status") == "not_applicable":
            reasons.append("실측 GPU 실험의 조건 수·반복 수를 연구 설계에 기록해야 함")
        else:
            try:
                conditions = number(design, "conditions", integer=True)
                repeats = number(design, "repeated_runs", integer=True)
                if estimate["runs"] != conditions * repeats:
                    reasons.append("파일럿 전체 실행 수와 설계의 조건 수 × 반복 수가 일치하지 않음")
                if "conditions" in estimate and (len(estimate["conditions"]) != conditions
                                                or any(e["runs"] != repeats for e in estimate["conditions"])):
                    reasons.append("파일럿 조건별 실행 수와 설계의 조건 수·반복 수가 일치하지 않음")
            except ValueError as exc:
                reasons.append("design: " + str(exc))
    if effect.get("status") == "quantitative":
        scope = (candidate.get("resource_plan") or {}).get("scope")
        if scope is None:
            reasons.append("resource_plan.scope: 표본·반복 수 변경에 따른 평가·작업 비용 재산정 필요")
        elif not isinstance(scope, dict):
            raise ValueError("resource_plan.scope: 객체 필요")
        else:
            if scope.get("unit") != effect["unit"]:
                raise ValueError("resource_plan.scope.unit: 효과 계획의 독립 평가 단위와 일치해야 함")
            units = number(scope, "evaluation_units", integer=True, positive=False)
            repeats = number(scope, "repeated_runs", integer=True)
            events = effect.get("events")
            events_fit = True
            if events is not None:
                scoped_events = scope.get("events")
                events_fit = (isinstance(scoped_events, dict) and scoped_events.get("unit") == events["unit"]
                              and number(scoped_events, "count", integer=True, positive=False) >= events["required"])
            if units < effect["required_units"] or repeats != design.get("repeated_runs") or not events_fit:
                reasons.append("표본·반복 수가 자원 산정 범위를 벗어남; 평가시간·작업시간·파일럿 실행 수 갱신 필요")
    return {**capacity, "gpu_hours_required": gpu_hours, "work_hours_required": work_hours,
            "fits": not reasons, "reasons": reasons}


def planning_errors(candidate, final=False):
    errors = []
    try:
        effect_check(candidate.get("design"), final)
    except ValueError as exc:
        errors.append(str(exc))
    design = candidate.get("design")
    if isinstance(design, dict) and isinstance(design.get("effect_plan"), dict):
        effect = design["effect_plan"]
        if final and effect.get("status") == "pending":
            tasks = candidate.get("first_week", [])
            if not isinstance(tasks, list) or not any(isinstance(t, dict) and t.get("id") == effect.get("measurement_task_id") and t.get("category") == "measurement" for t in tasks):
                errors.append("effect_plan.measurement_task_id: 첫 주 measurement 작업에 연결 필요")
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
                if "conditions" in value:
                    number(value, "conditions", integer=True)
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
    if candidate.get("resource_plan") is not None or final:
        try:
            work_estimate(candidate.get("resource_plan"))
            scope = candidate.get("resource_plan", {}).get("scope")
            if scope is not None:
                if not isinstance(scope, dict) or not isinstance(scope.get("unit"), str) or not scope["unit"].strip():
                    raise ValueError("resource_plan.scope: 독립 단위·평가 표본 수·반복 수 필요")
                number(scope, "evaluation_units", integer=True, positive=False)
                number(scope, "repeated_runs", integer=True)
        except ValueError as exc:
            errors.append(str(exc))
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


def readiness_reasons(candidate, state):
    """Unknown readiness remains conditional; a report can still document it."""
    reasons = planning_errors(candidate)
    for key in ("design", "provenance"):
        if candidate.get(key) is None:
            reasons.append(f"{key}: 실행 준비 기록 미확인")
    try:
        reasons.extend(resource_check(candidate, state)["reasons"])
    except ValueError as exc:
        reasons.append(str(exc))
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
    from .evaluation import selected_candidates
    selected = [c for c in state["candidates"] if c["id"] == candidate_id] if candidate_id else selected_candidates(state)
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
