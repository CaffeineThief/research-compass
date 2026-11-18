from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .literature import source_ok

INDEXES = {"SCIE", "SSCI", "AHCI", "ESCI", "KCI 등재", "KCI 등재후보"}


def venue_fields(venue):
    if venue.get("category") == "conference":
        return ("guidelines", "schedule", "cost")
    return ("index", "cost", "guidelines", "schedule", "metrics")


def verified_field(journal, key):
    field = journal.get(key)
    if field is None:
        field = {}
    if not isinstance(field, dict):
        raise ValueError(f"journal.{key}: 객체 또는 null 필요")
    source = field.get("source")
    if source is None:
        source = {}
    if not isinstance(source, dict):
        raise ValueError(f"journal.{key}.source: 객체 또는 null 필요")
    if field.get("status") != "verified" or not source_ok(source) or source.get("official") is not True or not str(source.get("url", "")).startswith("https://"):
        return {"value": "확인 불가", "checked_at": source.get("checked_at"), "source": None}
    if journal.get("category") == "conference":
        identity_matches = (
            bool(journal.get("name") and journal.get("edition"))
            and source.get("venue_name") == journal["name"]
            and source.get("edition") == journal["edition"]
            and source.get("track") == journal.get("track")
            and source.get("round") == journal.get("round")
        )
    else:
        identity_matches = (
            bool(journal.get("issn"))
            and source.get("issn") == journal["issn"]
            and source.get("journal_name") == journal.get("name")
        )
    if not identity_matches:
        return {"value": "확인 불가", "checked_at": source.get("checked_at"), "source": None}
    if key == "index" and field.get("value") not in INDEXES:
        return {"value": "확인 불가", "checked_at": source.get("checked_at"), "source": None}
    if key == "metrics" and (not field.get("year") or not field.get("category")):
        return {"value": "확인 불가", "checked_at": source.get("checked_at"), "source": None}
    if field.get("value") is None:
        return {"value": "확인 불가", "checked_at": source.get("checked_at"), "source": None}
    return {"value": field["value"], "checked_at": source["checked_at"], "source": source["url"]}


def zone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise ValueError("일정: 유효한 IANA 시간대 필요 (예: Asia/Seoul, UTC, Etc/GMT+12)") from exc


def moment(value, timezone_name, allow_date=False):
    local_zone = zone(timezone_name)
    if not isinstance(value, str):
        raise ValueError("일정: ISO 날짜/시각 문자열 필요")
    if allow_date and len(value) == 10:
        return datetime.combine(date.fromisoformat(value), time.max, local_zone)
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() != instant.astimezone(local_zone).utcoffset():
        raise ValueError("일정: 시각의 UTC offset과 명시한 시간대가 일치해야 함")
    return instant.astimezone(local_zone)


def submission_plan(candidate):
    plan = candidate.get("submission_plan") if candidate else None
    if plan is None:
        return None
    if not isinstance(plan, dict):
        raise ValueError("submission_plan: 객체 필요")
    if plan.get("status") == "pending":
        if any(not isinstance(plan.get(k), str) or not plan[k].strip() for k in ("reason", "next_action")):
            raise ValueError("submission_plan: 미정 사유·다음 확인 필요")
        return None
    if plan.get("status") != "estimated" or not source_ok(plan.get("source")) or not isinstance(plan.get("assumptions"), str) or not plan["assumptions"].strip():
        raise ValueError("submission_plan: estimated/pending, 일정 가정과 근거 필요")
    completed = moment(plan.get("experiments_complete"), plan.get("timezone"), allow_date=True)
    days = plan.get("writing_days")
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("submission_plan.writing_days: 원고·검토·형식 준비 기간(0 이상 정수) 필요")
    ready = completed + timedelta(days=days) if days else completed
    roundtrip = ready.astimezone(timezone.utc).astimezone(ready.tzinfo)
    if ready.utcoffset() != roundtrip.utcoffset():
        raise ValueError("submission_plan: 준비 종료가 일광절약시간 전환의 존재하지 않는 시각입니다. 일정을 확인하세요.")
    return ready


def schedule_deadlines(venue):
    schedule = venue.get("schedule") or {}
    if not isinstance(schedule, dict):
        raise ValueError("schedule: 객체 필요")
    mode = schedule.get("mode")
    if mode is None:
        return None
    if mode not in ("fixed", "rolling"):
        raise ValueError("schedule.mode: fixed/rolling 필요")
    deadlines = schedule.get("deadlines", [])
    if not isinstance(deadlines, list) or (mode == "fixed" and (not deadlines or len(deadlines) > 100)) or (mode == "rolling" and deadlines):
        raise ValueError("schedule.deadlines: fixed는 마감 배열, rolling은 빈 배열 필요")
    known = {}
    for item in deadlines:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip() or item["id"] in known:
            raise ValueError("schedule.deadlines: 고유 ID 객체 배열 필요")
        if item.get("kind") not in ("abstract", "submission", "registration", "commitment", "other"):
            raise ValueError("deadline.kind: abstract/submission/registration/commitment/other 필요")
        instant = moment(item.get("at"), item.get("timezone"))
        from .literature import valid_id_list
        if not valid_id_list(item.get("requires", [])):
            raise ValueError("deadline.requires: 고유한 선행 마감 ID 배열 필요")
        known[item["id"]] = (item, instant)
    if mode == "fixed" and not any(d[0]["kind"] in ("submission", "commitment") for d in known.values()):
        raise ValueError("schedule: 원고 제출 또는 commitment 마감 필요")
    visited, visiting = set(), set()
    def visit(did):
        if did in visiting:
            raise ValueError("deadline.requires: 순환 경로")
        if did in visited:
            return
        visiting.add(did)
        item, instant = known[did]
        for required in item.get("requires", []):
            if required not in known or known[required][1].astimezone(timezone.utc) > instant.astimezone(timezone.utc):
                raise ValueError("deadline.requires: 존재하며 제출 전인 선행 마감 필요")
            visit(required)
        visiting.remove(did); visited.add(did)
    for did in known:
        visit(did)
    return known


def schedule_check(state, venue, as_of=None):
    candidate = next((c for c in state["candidates"] if c["id"] == venue.get("candidate_id")), None)
    ready = submission_plan(candidate)
    deadlines = schedule_deadlines(venue)
    profile_zone = zone(state["profile"].get("timezone") or "UTC")
    date_only = isinstance(as_of, str) and len(as_of) == 10
    if date_only:
        reference_date = date.fromisoformat(as_of)
        reference = None
    else:
        reference = datetime.fromisoformat(as_of.replace("Z", "+00:00")) if as_of else datetime.now(timezone.utc)
        if reference.tzinfo is None:
            raise ValueError("as_of: 날짜 또는 UTC offset을 포함한 ISO 시각 필요")
        reference_date = reference.astimezone(profile_zone).date()
    base = {"reference_timezone": str(profile_zone), "ready_at": ready.isoformat() if ready else None,
            "as_of": as_of or reference.isoformat()}
    verified = verified_field(venue, "schedule")
    if not verified["source"]:
        return {**base, "status": "unverified", "reason": "공식 일정·회차·트랙·라운드 확인 필요", "deadlines": []}
    if deadlines is None:
        return {**base, "status": "needs_structure", "reason": "기존 자유 서술 일정: 시간대·마감·준비 기간 구조화 필요", "deadlines": []}
    if (venue.get("schedule") or {}).get("mode") == "rolling":
        if venue.get("category") == "conference":
            return {**base, "status": "needs_recheck", "reason": "학술대회 상시 접수의 회차·제출 경로 재확인 필요", "deadlines": []}
        return {**base, "status": "rolling" if ready else "readiness_unknown", "reason": "상시 접수; 준비 예정일 기준" if ready else "원고 준비 예정일 미정", "deadlines": []}
    completed = set()
    steps = (candidate.get("submission_plan") or {}).get("completed_steps", []) if candidate else []
    if not isinstance(steps, list):
        raise ValueError("submission_plan.completed_steps: 완료 마감의 venue_id/deadline_id/evidence 배열 필요")
    seen_steps = set()
    known_venues = {v["id"] for v in state["journals"] if candidate and v.get("candidate_id") == candidate["id"]}
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get("venue_id"), str) or not isinstance(step.get("deadline_id"), str) or not source_ok(step.get("evidence")):
            raise ValueError("submission_plan.completed_steps: 실제 완료의 ID와 확인 근거 필요")
        identity = (step["venue_id"], step["deadline_id"])
        if identity in seen_steps or step["venue_id"] not in known_venues:
            raise ValueError("completed_steps: 중복 또는 해당 후보에 없는 투고처 ID")
        seen_steps.add(identity)
        if step["venue_id"] == venue["id"]:
            if step["deadline_id"] not in deadlines:
                raise ValueError("completed_steps: 해당 투고처에 없는 마감 ID")
            stamp = step.get("completed_at")
            if not isinstance(stamp, str):
                raise ValueError("completed_steps.completed_at: 실제 완료 시각과 UTC offset 필요")
            completion = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if completion.tzinfo is None:
                raise ValueError("completed_steps.completed_at: UTC offset 필요")
            reference_end = reference or datetime.combine(reference_date, time.max, profile_zone)
            if completion > reference_end:
                raise ValueError("completed_steps: 기준 시각 이후의 완료 기록")
            if completion <= deadlines[step["deadline_id"]][1]:
                completed.add(step["deadline_id"])
    def timing(instant):
        if reference is None:
            local_day = instant.astimezone(profile_zone).date()
            return "expired" if local_day < reference_date else "deadline_day_needs_recheck" if local_day == reference_date else "upcoming"
        return "expired" if instant <= reference else "upcoming"
    def blocked(did):
        return any((timing(deadlines[r][1]) == "expired" and r not in completed) or blocked(r)
                   for r in deadlines[did][0].get("requires", []) if r not in completed)
    rows = []
    for did, (item, instant) in deadlines.items():
        status = timing(instant)
        if did in completed:
            readiness = "completed"
        elif blocked(did):
            readiness = "blocked_prerequisite"
        elif status == "expired":
            readiness = "expired"
        elif status == "deadline_day_needs_recheck":
            readiness = "needs_time_recheck"
        elif item["kind"] in ("submission", "commitment"):
            readiness = "readiness_unknown" if ready is None else "ready_in_time" if ready.astimezone(timezone.utc) <= instant.astimezone(timezone.utc) else "insufficient_preparation_time"
            if readiness == "ready_in_time" and any(r not in completed for r in item.get("requires", [])):
                readiness = "pending_prerequisite"
        else:
            readiness = "action_required"
        rows.append({"id": did, "kind": item["kind"], "at": item["at"], "timezone": item["timezone"],
                     "timing": status, "readiness": readiness, "requires": item.get("requires", [])})
    paths = [r for r in rows if r["kind"] in ("submission", "commitment")]
    status = "ready_in_time" if any(r["readiness"] == "ready_in_time" for r in paths) else "needs_action"
    return {**base, "status": status, "reason": "선행 마감·원고 준비·현재 시각을 함께 확인하세요. 예정일은 추정입니다.", "deadlines": rows}


def recheck_journals(state, as_of=None, max_age_days=90):
    if isinstance(max_age_days, bool) or not isinstance(max_age_days, int) or max_age_days < 0:
        raise ValueError("max_age_days: 0 이상의 정수 필요")
    if as_of and len(as_of) == 10:
        target = date.fromisoformat(as_of)
    else:
        reference = datetime.fromisoformat(as_of.replace("Z", "+00:00")) if as_of else datetime.now(timezone.utc)
        if reference.tzinfo is None:
            raise ValueError("as_of: 날짜 또는 UTC offset을 포함한 ISO 시각 필요")
        target = reference.astimezone(zone(state["profile"].get("timezone") or "UTC")).date()
    results = []
    for journal in state["journals"]:
        fields = {}
        for key in venue_fields(journal):
            verified = verified_field(journal, key)
            checked = date.fromisoformat(verified["checked_at"][:10]) if verified["source"] else None
            age = (target - checked).days if checked else None
            status = "unverified" if checked is None else "future_date" if age < 0 else "stale" if age > max_age_days else "current"
            fields[key] = {**verified, "status": status, "age_days": age, "needs_recheck": status != "current"}
        results.append({"id": journal["id"], "name": journal.get("name"), "as_of": target.isoformat(), "max_age_days": max_age_days,
                        "fields": fields, "submission": schedule_check(state, journal, as_of)})
    return results
