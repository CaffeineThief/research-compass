import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .state import invalidate, now, save
from .budget import admit_results, check_search_budget, remaining_results, search_coverage
from .literature import merge_papers


class Crossref:
    name = "crossref"

    def search(self, query, limit, since, until, timeout):
        params = {"query.bibliographic": query, "rows": limit}
        filters = []
        if since:
            filters.append("from-pub-date:" + since)
        if until:
            filters.append("until-pub-date:" + until)
        if filters:
            params["filter"] = ",".join(filters)
        email = os.environ.get("CROSSREF_MAILTO")
        if email:
            params["mailto"] = email
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": "research-compass/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(10_000_001)
        if len(raw) > 10_000_000:
            raise ValueError("검색 응답이 10 MB 상한을 초과했습니다.")
        records = json.loads(raw)["message"]["items"]
        papers = []
        for item in records:
            doi = item.get("DOI")
            title = item.get("title") or []
            if not doi or not title:
                continue
            dates = item.get("published", {}).get("date-parts", [[]])[0]
            checked = now()
            papers.append({
                "id": "doi:" + doi.lower(), "doi": doi, "title": title[0],
                "authors": [" ".join(filter(None, [a.get("given"), a.get("family")])) or a.get("name", "") for a in item.get("author", [])],
                "year": dates[0] if dates else None,
                "venue": (item.get("container-title") or [None])[0],
                "publication_type": item.get("type"),
                "version": "preprint" if item.get("type") == "posted-content" else "unspecified",
                "url": "https://doi.org/" + doi,
                "abstract": item.get("abstract"),
                "access": "abstract_only" if item.get("abstract") else "unavailable",
                "supplements": "unknown", "code": "unknown", "data": "unknown",
                "checked_at": checked, "test_data": False,
                "source": {"url": url, "location": "Crossref metadata: " + doi, "checked_at": checked},
                "relation": item.get("relation", {}), "references": item.get("reference", []),
                "full_text_links": item.get("link", [])
            })
        return papers


PROVIDERS = {"crossref": Crossref}


def run_search(state, cache_dir, query, branch, provider="crossref", limit=10, since=None, until=None, refresh=False):
    if branch not in ("recent", "foundational", "validation", "novelty") or not query.strip():
        raise ValueError("검색어와 유효한 탐색 갈래가 필요합니다.")
    for value in (since, until):
        if value:
            datetime.strptime(value, "%Y-%m-%d")
    if since and until and since > until:
        raise ValueError("검색 시작일이 종료일보다 늦습니다.")
    if state["test_data"]:
        raise ValueError("테스트 세션에서 실제 검색은 지원하지 않습니다.")
    cfg, usage = state["config"], state["usage"]
    if limit < 1 or limit > 100:
        raise ValueError("검색당 결과 수는 1~100입니다.")
    if provider not in PROVIDERS:
        raise ValueError("지원되지 않는 provider; 호스트 검색 결과는 import-papers로 가져오세요.")
    adapter = PROVIDERS[provider]()
    key = hashlib.sha256(json.dumps([provider, query, limit, since, until]).encode()).hexdigest()
    cache_file = Path(cache_dir) / (key + ".json")
    entry = {"id": "search-" + str(len(state["search_log"]) + 1), "query": query,
             "branch": branch, "provider": provider, "since": since, "until": until,
             "limit": limit, "at": now(), "test_data": False, "cache_hit": False}
    start = time.monotonic()
    try:
        cached = None
        if cache_file.exists() and not refresh:
            try:
                value = json.loads(cache_file.read_text(encoding="utf-8"))
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(value["fetched_at"])).total_seconds()
                if 0 <= age < cfg["cache_hours"] * 3600:
                    cached = value
            except (ValueError, KeyError, TypeError):
                pass
        if usage["seconds"] >= cfg["max_seconds"]:
            raise ValueError("실행 시간 상한에 도달했습니다.")
        if cached is not None:
            papers = cached["papers"]
            fingerprint = hashlib.sha256(json.dumps(papers, sort_keys=True).encode()).hexdigest()
            previous = next((s for s in reversed(state["search_log"]) if s.get("cache_key") == key and s.get("cache_version") == fingerprint and s.get("status") == "ok"), None)
            entry.update(cache_hit=True, fetched_at=cached["fetched_at"], cache_version=fingerprint)
            entry["received_count"] = len(papers)
            if previous:
                papers = [p for p in papers if p["id"] in previous["paper_ids"]]
            else:
                papers = admit_results(state, papers, limit)
            entry["discarded_count"] = entry["received_count"] - len(papers)
        else:
            check_search_budget(state)
            entry["allocation_advice"] = search_coverage(state)["branches"][branch]
            effective_limit = min(limit, remaining_results(state))
            entry["limit"] = effective_limit
            usage["requests"] += 1
            papers = adapter.search(query, effective_limit, since, until, min(cfg["request_timeout"], cfg["max_seconds"] - usage["seconds"]))
            entry["received_count"] = len(papers)
            papers = admit_results(state, papers, effective_limit)
            entry["discarded_count"] = entry["received_count"] - len(papers)
            # Cache only admitted records so excess responses cannot re-enter later.
            merge_papers(state["papers"], papers, False)
            entry["cache_version"] = hashlib.sha256(json.dumps(papers, sort_keys=True).encode()).hexdigest()
            save(cache_file, {"fetched_at": now(), "papers": papers})
        merged = merge_papers(state["papers"], papers, False)
        if merged != state["papers"]:
            state["papers"] = merged
            invalidate(state, "analysis", "검색에서 신규 문헌/버전 발견")
        entry.update(status="ok", cache_key=key, paper_ids=[p["id"] for p in papers], count=len(papers))
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as exc:
        entry.update(status="failed", error=str(exc), count=0, paper_ids=[])
    finally:
        usage["seconds"] += round(time.monotonic() - start, 3)
        state["search_log"].append(entry)
    return entry
