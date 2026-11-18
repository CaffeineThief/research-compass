#!/usr/bin/env python3
"""Run from any directory; Python standard library only."""
import argparse
import json
import sys
from pathlib import Path

from researchlib.evaluation import rank, record_review, record_scope_review
from researchlib.budget import reserve_search, record_search, search_coverage, review_search
from researchlib.literature import merge_papers
from researchlib.output import bibliography, markdown, validate, evidence_cards
from researchlib.planning import pilot_estimate, week_checklist, resource_check
from researchlib.journals import recheck_journals
from researchlib.search import run_search
from researchlib.state import invalidate, load, new_state, reserve_agents, save, update_profile, validate_config


def parser():
    p = argparse.ArgumentParser(description="Research Compass: 검색/근거/평가/내보내기")
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("directory")
    init.add_argument("--topic", required=True)
    init.add_argument("--test-data", action="store_true")
    for name in ("search", "reserve-search", "record-search", "search-review", "import-papers", "profile", "config", "exclude", "invalidate", "reserve-agents", "validate", "evaluate", "export", "coverage", "journal-recheck", "review-candidate", "review-scope", "record-pilot", "pilot-estimate", "checklist"):
        cmd = sub.add_parser(name)
        cmd.add_argument("state", help="state.json 경로")
        if name in ("search", "reserve-search"):
            cmd.add_argument("--query", required=True)
            cmd.add_argument("--branch", choices=("recent", "foundational", "validation", "novelty"), required=True)
            cmd.add_argument("--provider", default="crossref" if name == "search" else "web")
            cmd.add_argument("--limit", type=int, default=10)
            cmd.add_argument("--since")
            cmd.add_argument("--until")
            cmd.add_argument("--refresh", action="store_true")
        if name in ("record-search", "search-review"):
            cmd.add_argument("search_id")
            cmd.add_argument("file")
        if name in ("import-papers", "profile", "config"):
            cmd.add_argument("file", help="JSON 파일")
        if name == "exclude":
            cmd.add_argument("paper_id")
        if name == "invalidate":
            from researchlib.state import STAGES
            cmd.add_argument("stage", choices=STAGES)
            cmd.add_argument("--reason", required=True)
            cmd.add_argument("--candidate", action="append", help="미지정 시 전역 재검토")
        if name == "reserve-agents":
            cmd.add_argument("count", type=int)
        if name == "export":
            cmd.add_argument("--format", choices=("md", "bib", "ris", "cards", "checklist", "all"), default="all")
        if name in ("validate", "export"):
            cmd.add_argument("--final", action="store_true", help="최종 보고서 준비 상태 검증")
        if name in ("record-pilot", "pilot-estimate", "review-candidate", "review-scope"):
            cmd.add_argument("candidate_id")
        if name in ("record-pilot", "review-candidate", "review-scope"):
            cmd.add_argument("file", help="후보별 기록 JSON")
        if name == "checklist":
            cmd.add_argument("--candidate", required=True)
        if name == "journal-recheck":
            cmd.add_argument("--as-of", help="YYYY-MM-DD 또는 UTC offset을 포함한 ISO 시각; 기본값 현재")
            cmd.add_argument("--max-age-days", type=int, default=90)
    return p


def main():
    args = parser().parse_args()
    if args.command == "init":
        path = Path(args.directory) / "state.json"
        if path.exists():
            raise ValueError("기존 세션을 덮어쓸 수 없습니다. 다른 디렉터리를 선택하세요.")
        save(path, new_state(args.topic, args.test_data))
        print(path.resolve())
        return 0
    path = Path(args.state)
    state = load(path)
    result = None
    if args.command == "coverage":
        result = search_coverage(state)
    elif args.command == "journal-recheck":
        result = recheck_journals(state, args.as_of, args.max_age_days)
    elif args.command == "review-scope":
        result = record_scope_review(state, args.candidate_id, json.loads(Path(args.file).read_text(encoding="utf-8")))
    elif args.command == "review-candidate":
        result = record_review(state, args.candidate_id, json.loads(Path(args.file).read_text(encoding="utf-8")))
    elif args.command in ("record-pilot", "pilot-estimate"):
        candidate = next((c for c in state['candidates'] if c['id'] == args.candidate_id), None)
        if candidate is None:
            raise ValueError("후보 ID를 찾을 수 없습니다.")
        pilot = json.loads(Path(args.file).read_text(encoding="utf-8")) if args.command == "record-pilot" else candidate.get("pilot")
        result = pilot_estimate(pilot)
        if args.command == "record-pilot":
            candidate['pilot'] = pilot
            invalidate(state, 'evaluation', '파일럿 측정 갱신: ' + args.candidate_id, [args.candidate_id])
        result["resource_check"] = resource_check(candidate, state)
    elif args.command == "checklist":
        errors = validate(state)
        if errors:
            result = {"errors": errors}
        else:
            content = week_checklist(state, args.candidate)
            dest = path.parent / "first-week.md"
            dest.write_text(content, encoding="utf-8")
            result = {"file": str(dest.resolve()), "candidate_id": args.candidate}
    elif args.command == "search":
        result = run_search(state, path.parent / "cache", args.query, args.branch, args.provider, args.limit, args.since, args.until, args.refresh)
    elif args.command == "reserve-search":
        result = reserve_search(state, args.query, args.branch, args.provider, args.limit)
        result.update(since=args.since, until=args.until)
    elif args.command == "search-review":
        result = review_search(state, args.search_id, json.loads(Path(args.file).read_text(encoding="utf-8")))
    elif args.command == "record-search":
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        result = record_search(state, args.search_id, payload)
    elif args.command == "import-papers":
        incoming = json.loads(Path(args.file).read_text(encoding="utf-8"))
        if not isinstance(incoming, list):
            raise ValueError("논문 JSON 배열이 필요합니다.")
        merged = merge_papers(state["papers"], incoming, state["test_data"])
        if merged != state["papers"]:
            state["papers"] = merged
            invalidate(state, "analysis", "문헌 추가/업데이트")
    elif args.command == "profile":
        update_profile(state, json.loads(Path(args.file).read_text(encoding="utf-8")))
    elif args.command == "config":
        patch = json.loads(Path(args.file).read_text(encoding="utf-8"))
        if not isinstance(patch, dict) or set(patch) - set(state["config"]):
            raise ValueError("지원되지 않는 설정")
        state["config"].update(patch)
        validate_config(state["config"])
        invalidate(state, "evaluation" if set(patch) <= {"weights"} else "search", "설정 변경")
    elif args.command == "exclude":
        paper = next((p for p in state["papers"] if p["id"] == args.paper_id), None)
        if not paper:
            raise ValueError("논문 ID를 찾을 수 없습니다.")
        paper["excluded"] = True
        invalidate(state, "analysis", "논문 제외: " + args.paper_id)
    elif args.command == "invalidate":
        invalidate(state, args.stage, args.reason, args.candidate)
    elif args.command == "reserve-agents":
        reserve_agents(state, args.count)
    elif args.command == "validate":
        result = {"errors": validate(state, args.final)}
    elif args.command in ("evaluate", "export"):
        errors = validate(state, getattr(args, "final", False))
        if errors:
            print(json.dumps({"errors": errors}, ensure_ascii=False, indent=2))
            return 2
        if args.command == "evaluate":
            result = rank(state)
        else:
            formats = ("md", "bib", "ris", "cards", "checklist") if args.format == "all" else (args.format,)
            result = []
            contents = {}
            for fmt in formats:
                name = {"md": "report.md", "cards": "evidence-cards.md", "checklist": "first-week.md"}.get(fmt, "references." + fmt)
                content = markdown(state) if fmt == "md" else evidence_cards(state) if fmt == "cards" else week_checklist(state) if fmt == "checklist" else bibliography(state, fmt)
                contents[name] = content
            for name, content in contents.items():
                dest = path.parent / name
                dest.write_text(content, encoding="utf-8")
                result.append(str(dest.resolve()))
    if args.command not in ("validate", "evaluate", "export", "coverage", "journal-recheck", "pilot-estimate", "checklist"):
        save(path, state)
    print(json.dumps(result if result is not None else {"saved": str(path)}, ensure_ascii=False, indent=2))
    if isinstance(result, dict) and (result.get("errors") or result.get("status") == "failed"):
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, OverflowError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        sys.exit(2)
