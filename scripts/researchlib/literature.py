import copy
import re
from urllib.parse import urlparse

ACCESS = ("unavailable", "abstract_only", "partial", "full_text")


def valid_id_list(value):
    return (isinstance(value, list)
            and all(isinstance(item, str) and item.strip() for item in value)
            and len(value) == len(set(value)))


def doi_key(value):
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.strip(), flags=re.I).lower()


def source_ok(source):
    if not isinstance(source, dict):
        return False
    try:
        url = urlparse(str(source.get("url", "")))
    except ValueError:
        return False
    location = source.get("location")
    date = source.get("checked_at", "")
    try:
        from datetime import date as date_type
        date_type.fromisoformat(date[:10])
    except (TypeError, ValueError):
        return False
    return bool(location and ((url.scheme in ("http", "https") and url.netloc) or source.get("local_file")))


def validate_paper(paper, test_data):
    if not isinstance(paper, dict):
        raise ValueError("문헌과 버전 기록은 객체여야 합니다.")
    for key in ("id", "title", "version", "access", "checked_at", "source"):
        if not paper.get(key):
            raise ValueError(f"논문 {paper.get('id', '?')}: {key} 누락")
    if paper.get("test_data") is not test_data:
        raise ValueError("테스트용 자료와 실제 자료를 혼합할 수 없습니다.")
    if paper["access"] not in ACCESS or not source_ok(paper["source"]):
        raise ValueError("논문의 접근 상태 또는 출처가 잘못되었습니다.")
    if paper["access"] in ("partial", "full_text"):
        if not source_ok(paper.get("read_evidence")):
            raise ValueError("전문/일부 확인에는 실제 읽은 파일 또는 URL과 위치가 필요합니다.")
    if paper["access"] == "abstract_only" and not paper.get("abstract"):
        raise ValueError("초록 확인 상태에는 실제 확보한 초록이 필요합니다.")
    locations = paper.get("read_locations", [])
    if not isinstance(locations, list) or any(not source_ok(loc) for loc in locations):
        raise ValueError("read_locations는 유효한 열람 출처 배열이어야 합니다.")
    versions = paper.get("versions", [])
    if not isinstance(versions, list):
        raise ValueError("versions는 문헌 버전 배열이어야 합니다.")
    for version in versions:
        validate_paper(version, test_data)


def merge_version(current, incoming):
    """Combine reading records only after the caller establishes version identity."""
    locations = []
    for record in (current, incoming):
        if record.get("access") in ("partial", "full_text"):
            for location in record.get("read_locations", []) + [record.get("read_evidence")]:
                if source_ok(location) and location not in locations:
                    locations.append(copy.deepcopy(location))
    for key, value in incoming.items():
        if key not in ("versions", "aliases") and (key not in current or current[key] is None):
            current[key] = copy.deepcopy(value)
    if ACCESS.index(incoming["access"]) > ACCESS.index(current["access"]):
        for key in ("access", "read_evidence", "abstract", "checked_at", "supplements", "code", "data"):
            if key in incoming:
                current[key] = copy.deepcopy(incoming[key])
    if locations and ("read_locations" in current or "read_locations" in incoming
                      or any(location != current.get("read_evidence") for location in locations)):
        current["read_locations"] = locations


def merge_papers(existing, incoming, test_data):
    """Only explicit work identity or an identical DOI permits an automatic merge."""
    result = copy.deepcopy(existing)
    for paper in incoming:
        validate_paper(paper, test_data)
        paper = copy.deepcopy(paper)
        if paper.get("doi"):
            paper["doi"] = doi_key(paper["doi"])
        matches = [p for p in result if p["id"] == paper["id"] or paper["id"] in p.get("aliases", []) or (paper.get("doi") and (p.get("doi") == paper["doi"] or paper["doi"] in p.get("aliases", []))) or (paper.get("work_id") and p.get("work_id") == paper["work_id"])]
        if len(matches) > 1:
            raise ValueError("여러 기존 기록에 걸친 병합입니다. 근거를 대조하고 ID 참조를 먼저 정리하세요.")
        if not matches:
            paper.setdefault("versions", [])
            paper.setdefault("aliases", [paper["doi"]] if paper.get("doi") else [])
            result.append(paper)
            continue
        current = matches[0]
        current.setdefault("versions", [])
        current.setdefault("aliases", [current["doi"]] if current.get("doi") else [])
        if current.get("doi") and paper.get("doi") and current["doi"] != paper["doi"] and not source_ok(paper.get("identity_evidence")):
            raise ValueError("서로 다른 DOI 병합에는 동일 연구라는 확인 근거가 필요합니다.")
        snapshot = {k: v for k, v in paper.items() if k not in ("versions", "aliases")}
        targets = [record for record in [current] + current["versions"]
                   if record["id"] == paper["id"] and record["version"] == paper["version"]
                   and record.get("doi") == paper.get("doi")]
        if targets:
            for target in targets:
                merge_version(target, snapshot)
        else:
            current["versions"].append(snapshot)
        for alias in [paper["id"], paper.get("doi")]:
            if alias and alias != current["id"] and alias not in current["aliases"]:
                current["aliases"].append(alias)
        # A shared DOI identifies the same version even when an import uses another ID.
        if current["version"] == paper["version"] and current.get("doi") and current["doi"] == paper.get("doi"):
            merge_version(current, snapshot)
    return result


def validate_claims(state):
    papers = {p["id"]: p for p in state["papers"] if not p.get("excluded")}
    errors = []
    ids = set()
    for claim in state["claims"]:
        cid = claim.get("id", "?")
        if cid in ids or cid == "?":
            errors.append(f"claim {cid}: 중복/누락 ID")
        ids.add(cid)
        if claim.get("kind") not in ("fact", "author_claim", "interpretation", "hypothesis"):
            errors.append(f"claim {cid}: 사실/저자 주장/해석/가설 구분 필요")
        if not claim.get("text") or "uncertainty" not in claim:
            errors.append(f"claim {cid}: 주장과 불확실성 필요")
        if claim.get("limitation_kind") not in (None, "author_acknowledged", "empirically_confirmed", "agent_inferred"):
            errors.append(f"claim {cid}: 한계 분류 오류")
        if not claim.get("evidence"):
            errors.append(f"claim {cid}: 근거 위치 필요")
        for evidence in claim.get("evidence", []):
            if "version" in evidence or "version_id" in evidence:
                errors.extend(f"claim {cid}: {issue}" for issue in evidence_errors(evidence, state))
                continue
            # Versionless legacy drafts retain their original checks until final validation.
            paper = papers.get(evidence.get("paper_id"))
            if not paper or not evidence.get("location"):
                errors.append(f"claim {cid}: 없거나 제외된 논문/근거 위치")
            elif paper["access"] == "unavailable":
                errors.append(f"claim {cid}: 접근 불가 논문은 내용 근거로 사용 불가")
            elif paper["access"] == "abstract_only" and evidence.get("scope") != "abstract":
                errors.append(f"claim {cid}: 초록 밖의 세부 방법/한계를 주장할 수 없음")
    for conflict in state["conflicts"]:
        if len(conflict.get("claim_ids", [])) < 2 or set(conflict.get("claim_ids", [])) - ids:
            errors.append(f"conflict {conflict.get('id')}: 대조할 주장 참조 필요")
        if conflict.get("status") not in ("unresolved", "resolved"):
            errors.append("충돌 상태 필요")
        if conflict.get("status") == "resolved" and not conflict.get("resolution_evidence"):
            errors.append("충돌 해소 근거 필요")
    return errors


def evidence_version(evidence, state):
    if not isinstance(evidence, dict):
        return None
    paper = next((p for p in state["papers"] if p["id"] == evidence.get("paper_id") and not p.get("excluded")), None)
    if not paper:
        return None
    versions = [paper] + paper.get("versions", [])
    matches = [p for p in versions if p.get("version") == evidence.get("version")
               and p.get("id") == evidence.get("version_id", paper["id"])]
    if not matches or len({p["doi"] for p in matches if p.get("doi")}) > 1:
        return None
    version = copy.deepcopy(matches[0])
    for record in matches[1:]:
        merge_version(version, record)
    return version


def evidence_errors(evidence, state, excerpt=False):
    """Match a citation to a recorded version and a location actually read."""
    version = evidence_version(evidence, state)
    if version is None:
        return ["활성 문헌과 확인한 버전/ID의 근거 객체 필요"]
    access, scope = version.get("access"), evidence.get("scope")
    if access == "unavailable" or scope not in ("abstract", "partial", "full_text"):
        return ["열람 범위 확인 필요"]
    if (access == "abstract_only" and scope != "abstract") or (access == "partial" and scope == "full_text"):
        return ["실제 열람 범위를 초과한 근거"]
    locations = [version.get("read_evidence", {})] + version.get("read_locations", [])
    if scope == "abstract" and version.get("abstract"):
        locations += [{"location": "abstract"}]
    errors = []
    if not evidence.get("location") or not any(isinstance(loc, dict) and loc.get("location") == evidence["location"] for loc in locations):
        errors.append("실제 열람 위치(read_evidence/read_locations)와 대조 필요")
    if excerpt and (not isinstance(evidence.get("excerpt"), str) or not evidence["excerpt"].strip()):
        errors.append("수동 대조용 짧은 발췌 필요")
    return errors
