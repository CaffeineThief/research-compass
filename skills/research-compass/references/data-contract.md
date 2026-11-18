# 저장 형식과 CLI

이 플러그인은 **호스트 에이전트가 연구를 수행하는 스킬 + Python 보조 도구**다. Python이 LLM을 호출하거나 논문을 스스로 읽지는 않는다. 도구 없는 환경에서는 스킬 절차와 JSON/Markdown 응답만 사용한다.

`SCRIPT`는 이 스킬 기준 `../../scripts/research.py`를 해석한 절대 경로로 둔다. 아래 명령의 예시 디렉터리는 사용자의 작업 공간에서 정한다.

```sh
python3 "$SCRIPT" init ./research-run --topic '관심 연구 주제'
python3 "$SCRIPT" search ./research-run/state.json --query 'topic replication' --branch validation --limit 5
python3 "$SCRIPT" import-papers ./research-run/state.json ./papers.json
python3 "$SCRIPT" profile ./research-run/state.json ./profile-patch.json
python3 "$SCRIPT" config ./research-run/state.json ./config-patch.json
python3 "$SCRIPT" reserve-agents ./research-run/state.json 3
python3 "$SCRIPT" exclude ./research-run/state.json '<실제 논문 ID>'
python3 "$SCRIPT" invalidate ./research-run/state.json novelty --reason '새 선행 연구 발견'
python3 "$SCRIPT" validate ./research-run/state.json
python3 "$SCRIPT" evaluate ./research-run/state.json
python3 "$SCRIPT" export ./research-run/state.json --format all
```

`search`는 `--since YYYY-MM-DD --until YYYY-MM-DD --refresh`도 받는다. 날짜 범위는 검색 계획에서 계산하여 전달한다. 최근 연구에만 최근 연도 필터를 기본 적용한다. 검색 오류는 기록 후 종료 코드 2, 성공은 0이다. 서버 응답은 최대 10 MB, 각 호출 결과는 최대 100건. 캐시 디렉터리는 세션 옆 `cache/`다. 초기 `usage`는 세션 전체의 누적 사용량이다. 재개한다고 초기화하지 않는다.

`profile` patch의 키는 init으로 생성한 profile 키를 따른다. 예: `{"duration":"12주","compute":"사용자 확인: GPU 1대","preferred_venues":["ACL","NAACL"]}`. 사용자 발언에 있는 조건만 입력한다. 설정 예: `{"recent_years":3,"max_requests":12}`. `weights`를 변경할 때는 7개 기준 전체를 넣는다.

## state.json

`schema_version=1`; `test_data=false`가 실제 자료 세션, `init --test-data`는 테스트 전용. 세션 간 테스트/실제 자료 혼합은 거부한다. 연구 자료는 로컬에 저장된다. API에 전송되는 것은 검색어·기간·건수와 선택 연락 이메일이며 로컬 PDF나 전체 상태 파일은 자동 전송하지 않는다. 호스트의 외부 도구를 쓸 때에는 그 도구의 데이터 전송 범위도 확인한다.

컬렉션: papers, claims, conflicts, gaps, agent_reviews, candidates, journals, search_log. 각 주요 컬렉션 항목에는 고유한 `id`가 필요하다. 단계 상태: pending / in_progress / complete / partial / stale. 완료 표시는 실제 업무를 마친 뒤 주 에이전트가 한다. 구조화된 분석은 호스트가 상태 JSON을 읽고 기존 데이터를 보존하여 갱신한다. **동시 쓰기는 지원하지 않는다**. 한 주 에이전트만 쓰고 하위 에이전트는 결과만 반환한다. 스크립트 저장은 원자적 교체를 사용한다.

## source 및 문헌

공통 출처: `{"url":"실제 확인한 https URL","location":"절/페이지/표 또는 사용자 답변 위치","checked_at":"ISO 날짜/시각"}`. 로컬 자료는 url 대신 `local_file`의 절대 경로를 쓸 수 있다. 사용자 자원 확인은 사용자 발언을 로컬 intake.md에 저장하고 그 파일·절을 참조한다. 공식 저널 정보는 실제 공식 URL이 필요하다.

`papers.json`은 배열이다. 필수 필드: id, title, version, access, checked_at, source, test_data. 추가 필드: authors(문자열 배열), year, venue, doi, url, publication_type, abstract, supplements, code, data, analysis. 모르는 저자·연도·출판처·DOI를 만들어 채우지 말고 null/누락으로 둔다. `doi`가 없으면 확인한 안정적인 식별자나 로컬 내부 ID를 사용한다.

- `version`: preprint / version-of-record / revised 또는 확인한 버전명; 미확인은 unspecified.
- `access`: unavailable / abstract_only / partial / full_text.
- partial/full_text에는 공통 source 형식의 `read_evidence` 필요. abstract_only에는 확보한 `abstract` 필요.
- 동일 버전의 문헌을 다시 가져오면 실제 읽은 위치를 중복 제거해 병합한다. 대표 기록의 ID·버전은 보존한다. 다른 ID가 같은 DOI·버전명을 가리키면 대표 기록에서도 그 열람 근거를 사용한다.
- 동일 연구의 서로 다른 DOI: 공통 `work_id`와 공통 source 형식의 `identity_evidence` 필요. 병합은 원래 대표 ID·열람 버전을 보존하고 다른 버전을 `versions`에 기록한다.
- `excluded=true`는 기록을 삭제하지 않고 추천 근거에서 제외한다. 제외된 문헌을 참조하는 주장·후보는 재검토 전 검증 오류가 된다.

## 분석

아래는 **스키마 설명용 형태**이며 실제 근거가 아니다. P1/C1 등은 저장된 실제 ID로 대체한다.

```json
{
  "id": "C1",
  "text": "확인한 주장 또는 명시적으로 구분한 해석",
  "kind": "author_claim",
  "limitation_kind": "author_acknowledged",
  "evidence": [{"paper_id":"P1","version":"실제로 읽은 버전명","location":"실제로 읽은 절·표","scope":"full_text"}],
  "uncertainty": "적용 범위 및 확인하지 못한 조건"
}
```

버전이 명시된 주장은 노벨티·근거 카드와 같은 버전 선택 및 위치·범위 검사로 검증한다. 대표 문헌이 초록 상태여도 인용한 다른 버전의 본문을 실제 열람했다면 그 버전을 검사한다. 버전명이 같고 ID가 다른 기록은 `version_id`로 지정한다. 같은 ID·버전명에 서로 다른 DOI가 연결되어 모호하면 각 버전의 ID를 정리해야 한다.

버전 정보가 전혀 없는 기존 주장은 일반 초안 검증에서 기존 접근 상태 검사를 유지한다. `version` 또는 `version_id`를 하나라도 지정하면 명시적 버전 검사를 적용하고, 최종 검증에는 버전·열람 위치·범위를 모두 기록해야 한다.

`kind`: fact / author_claim / interpretation / hypothesis. `limitation_kind`는 해당 없으면 null, 아니면 author_acknowledged / empirically_confirmed / agent_inferred. 초록 근거는 `scope=abstract`만 허용한다. partial이면 실제 확인한 절에 한정해 `scope=partial`로 기록한다.

충돌: id, claim_ids(2개 이상), summary, status(unresolved/resolved), resolution_evidence. 해소 근거 없이 resolved 금지.

공백: id, title, claim_ids, importance, attempted_solutions, why_unresolved, strength, uncertainty. 관련 문헌은 주장 참조를 통해 추적한다.

## 후보

id, title, paper_ids(활성 문헌), gap_ids(연구 공백 ID 배열), conflict_ids, gates, scores, novelty, plan.

- `gap_ids`는 중복 없는 공백 ID 배열이다. `gaps[].claim_ids`를 통해 주장과 실제 열람한 문헌 버전·위치에 연결한다. 공백의 `claim_ids`도 비어 있지 않은 고유 ID 배열이어야 한다. 연결된 모든 공백과 주장의 근거를 검사한다. 잘못된 ID·형식은 일반 검증에서도 오류다.
- 연결 미완료 후보에는 `gap_review={"reason":"실제 근거 부족 사유","next_actions":["다음 확인 작업"]}`를 기록한다. 기존 세션에서 `gap_ids`가 없거나 빈 배열이면 초안으로 읽고 `conditional`로 평가하며, 누락된 검토 기록도 보고서에 표시한다. 연결 정보는 호스트가 원문 확인 후 추가한다.
- 최종 선택 후보는 유효한 `gap_ids → claim_ids → evidence` 연결이 필요하다. 연결 부족 후보는 보완 과제를 포함한 초안으로 제공하고, 최종 추천 수에 포함하기 전 연결을 보완한다. 추천 후보가 없을 때는 `report.selected_candidate_ids=[]`, `no_candidate_reason`, `next_actions`로 결과를 기록할 수 있다.
- gates 키: data, resources, falsifiable, baseline, ethics_rights. 각 값은 `{"status":"unknown","reason":"확인 과제","evidence":null}`로 시작한다. pass에는 reason과 유효 source가 필요하다.
- scores 키: novelty, importance, relevance, feasibility, evaluation, reproducibility, venue_fit. 각 값은 `{"value":null,"reason":"미확인","uncertainty":"남은 불확실성","evidence":null}`. 값 범위 0~5; 근거가 충분하면 source를 기록한다.
- novelty: contribution, status, search_ids, closest_paper_ids, comparison(문제·방법·가정·데이터·평가·기여 6축), uncertainty. `search_ids`는 별도의 성공한 branch=novelty 검색을 참조한다. status는 pending / distinct_within_scope / duplicate. 실패 검색만으로 검증 완료 불가.
- plan은 [output.md](output.md)의 23개 키. 문자열로 쓰고 근거 문헌 ID/URL을 포함한다.
- `resource_plan`은 예상 연구 작업시간과 근거 또는 미산정 사유·측정 계획을 기록한다. 가용 시간은 `profile.resource_budget`에 관리한다. 조건별 파일럿 집계·실행 수 대조·입력 형식은 [실행 절차](workflow.md)의 2절을 따른다.

## 투고처

저널과 학술대회 모두 기존 `journals` 배열에 기록한다. 공통 필드는 id, candidate_id, name(공식 저널명 또는 학술대회명), url(공식 페이지), category(journal/conference), recommendation_stage(preliminary/detailed), fit, related_papers(실제로 확인한 문헌 ID/링크), article_type, strengthening, language_format, data_code_ethics, uncertainty다. 저널에는 publisher, issn을, 학술대회에는 organizer, edition(회차 또는 연도), track을 추가한다.

저널의 index, cost, schedule, metrics, guidelines와 학술대회의 guidelines, schedule, cost는 같은 검증 구조를 사용한다. 아래는 저널의 예다.

```json
{
  "status": "unverified",
  "value": null,
  "source": {
    "url": null,
    "location": null,
    "checked_at": null,
    "official": false,
    "journal_name": null,
    "issn": null
  }
}
```

`verified`는 공식 출처를 실제로 열어 확인한 경우에만 기록한다. 저널 출처는 `source.journal_name`, `source.issn`이 기록과 일치해야 한다. 학술대회 출처는 대신 `source.venue_name`, `source.edition`, `source.track`을 쓰고 해당 회차·트랙과 일치시킨다. `schedule`에는 해당 투고 경로의 마감일과 시간대를 명시한다. 아래 색인·지표 필드는 저널에 적용한다. index 값은 SCIE/SSCI/AHCI/ESCI/KCI 등재/KCI 등재후보 중 확인한 값. 지표는 year와 category 추가. 여러 색인 또는 ISSN이 있으면 기본 확인 레코드를 하나 선택하고 나머지는 별도 출처와 함께 추가 기록한다. 내보내기는 기본 레코드를 표시하므로 여러 색인의 상세 표는 호스트가 보완한다.

## 호스트 검색 기록

id, query, branch, provider, since, until, at, status(ok/failed), paper_ids, count, test_data, cache_hit, error. 문헌을 확인하지 못한 검색은 failed/미완료로 기록한다. DOI 목록을 가져오는 성공과 전문 확보는 별도 상태다. 외부 도구 실패도 사용량에 포함한다. 성공한 0건 검색은 검색 성공일 뿐 노벨티 입증이 아니다.

## 검증 범위

자동 검증: 필드·고유 ID·인용 참조, 접근 상태, 초록 밖 근거 사용, 테스트 혼합, 필수 조건, 후보별 검색 유무, 가중치, 저널 공식 확인 필드. 자동으로 논문 내용을 이해하거나 웹 출처 진위를 인증하지 않는다. `stale` 단계가 남으면 후보를 조건부로 낮춘다. 최종 연구 계획의 학술적 타당성·모든 필드의 의미는 호스트가 원문과 대조해야 한다.

## 호스트 웹 검색의 상한 처리

웹 검색마다 먼저 실행한다.

```sh
python3 "$SCRIPT" reserve-search ./research-run/state.json --query '검색어' --branch novelty --provider web --limit 15
```

반환된 id와 limit을 사용한다. 한 예약은 한 질의이며, 병렬 검색·배치 질의는 예약별로 순차 실행한다. limit은 남은 결과 예산으로 자동 축소된다. 예약 시 요청 1회가 사용된다. 미완료 예약이 있으면 다음 검색은 차단된다. 실행 중단 후 재개 시 해당 요청을 실제로 실행했는지 확인하고 응답 또는 취소 오류로 마감한다.

원래 검색 순서의 결과를 JSON으로 저장한다. 각 결과는 url, title 등 호스트가 실제 반환한 필드가 있는 객체다. 예시 형태는 `{"results":[{"url":"실제 URL","title":"실제 제목"}]}`이다. 네트워크 오류나 취소는 `{"error":"실제 오류/취소 사유","results":[]}`로 저장한다.

```sh
python3 "$SCRIPT" record-search ./research-run/state.json '<예약 id>' ./search-response.json
```

반환된 results만 후속 분석과 import-papers에 사용한다. count와 usage.results는 채택 건수, received_count는 수신 건수, discarded_count는 초과 제외 건수다. 원래 응답이 15건이고 남은 예산이 3건이면 앞의 3건만 채택한다. 초과분의 원문을 열거나 근거로 쓰지 않는다. 같은 응답을 같은 ID에 재기록하면 사용량을 중복 계산하지 않는다. 서로 다른 응답으로 완료 기록을 덮어쓸 수 없다. 단일 주 에이전트만 상태를 수정한다.

Crossref도 남은 예산만 요청하고, 제공처의 초과 응답을 제외한다. 같은 세션에서 이미 채택한 캐시 결과 재사용은 중복 계상하지 않는다. 다른 세션의 캐시는 새 세션 예산에 맞춰 채택한다. 스크립트를 직접 통하지 않는 호스트 도구에는 프로세스 수준의 강제 차단이 없으므로 위 예약·기록 절차를 준수한다.

검색 예산을 초과한 기존 세션을 읽을 수는 있지만 validate는 초과를 보고한다. 과거 기록을 임의로 100으로 줄여 수정하지 않는다. 기존 결과의 재검토 또는 사용자 승인에 따른 예산 변경 후 재개한다.

## 실행 준비 기록

[workflow.md](workflow.md)에 근거 카드, 6축 비교, pilot, provenance, design, first_week, report, 검색 배분과 저널 재확인 명령을 정의한다. schema_version=1과 기존 데이터를 유지하는 추가 필드이며, 이전 문자열 비교는 읽을 수 있지만 조건부로 평가한다. `source=null`인 미확인 저널 필드는 정상적으로 내보낸다. 일반 validate는 초안을 허용하고 --final은 보고서 완결성을 별도로 검사한다.
