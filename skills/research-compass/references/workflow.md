# 근거에서 첫 주 실행까지

실제 측정·원문 확인을 구조화하는 형식이다. 빈칸을 통과용 문구나 추정 사실로 채우지 않는다. 기존 schema_version=1 파일은 그대로 읽으며, 새 필드는 재검토한 범위에서 추가한다. 예전 결과를 자동으로 검증 완료 상태로 바꾸지 않는다.

## 1. 근거 카드와 6축 비교

`claims`의 기존 text/kind/uncertainty에 `interpretation`(발췌가 주장을 어떻게 뒷받침하는지)을 추가한다. 각 evidence에는 다음 필드를 기록한다.

- paper_id: 활성 문헌 대표 ID.
- version: 실제 읽은 버전명. 대표 문헌과 다른 버전이면 `version_id`도 기록한다. `papers[].versions`에 저장된 ID와 일치해야 한다. 주장·노벨티·근거 카드는 이 버전을 공통 기준으로 검사한다. 과거의 동일 ID·버전 스냅샷에 나뉜 열람 위치도 함께 확인한다.
- location: 실제 읽은 절·페이지·표. 동일 버전을 다시 가져오면 추가 열람 위치를 병합하며 다른 버전의 위치는 해당 버전에 연결한다. `read_evidence.location` 또는 `read_locations[].location`과 정확히 일치시킨다. read_locations는 공통 source 객체의 배열이며, 실제 원문을 확인한 뒤 추가한다.
- scope: abstract / partial / full_text. 읽은 범위보다 넓게 설정하지 않는다. 초록은 location=abstract도 허용한다.
- excerpt: 수동 대조에 필요한 짧은 원문 발췌. 출처별 인용 허용 범위 안에서 최소한만 사용한다. 긴 본문을 복사하지 않는다.

`export --format cards`는 기존 claims로 `evidence-cards.md`를 만든다. 카드마다 주장·해석·미확인 사항·버전·위치·원문 링크·발췌를 보여 준다. 출처의 진실성과 해석의 타당성은 원문 대조가 필요하다.

`novelty.comparison`은 problem/method/assumptions/data/evaluation/contribution 6개 키를 사용한다. 기존 한국어 키 문제/방법/가정/데이터/평가/기여도 지원한다. 각 값은 `{"difference":"확인한 차이와 비교 범위","evidence":[근거 객체]}`다. 모든 축에 실제 본문 근거를 연결하고 closest_paper_ids의 각 문헌을 비교에서 인용한다. 문자열만 있는 기존 비교는 조건부로 남는다. 성공한 0건 검색은 정상 이력이지만 그 자체로 노벨티 증거가 되지 않는다.

## 2. 파일럿 측정과 자원 추정

후보의 `pilot`은 다음 중 하나다.

- `status=pending`: reason, measurement_plan 필수. 계산 결과는 null이며 후보는 조건부다.
- `status=not_applicable`: reason 필수. 연산 실험이 없는 연구처럼 해당하지 않는 경우에 사용한다.
- `status=measured`: 아래 필드를 모두 기록한다.

| 필드 | 의미 |
|---|---|
| hardware, precision, input_shape | 측정한 장비·정밀도·입력 크기 |
| batch_size, dataset_size | 배치당 표본 수·훈련 고유 표본 수, 양의 정수 |
| measured_steps, elapsed_seconds | 실제 측정 스텝 수·소요 초 |
| steps_per_run, runs | 계획한 실행당 스텝·전체 실행 횟수(조건과 seed 포함) |
| peak_memory_gib, available_memory_gib | 같은 장비에서 측정한 최대 사용량·실제 가용량 |
| overhead_fraction | 준비·평가 등 추가 시간 가정. 0.2는 20%; 근거는 assumptions에 명시 |
| assumptions | 측정 범위, 워밍업/입출력 포함 여부, 처리량 변동과 추정 한계 |
| source | 실측 로그 파일/URL·위치·확인일 |

예상 시간 = elapsed_seconds / measured_steps × steps_per_run × runs × (1 + overhead_fraction) / 3600.

같은 측정 조건에서의 외삽이다. 다른 모델·해상도·장비로 환산하지 않는다. 조건별 비용이 다르면 대표 측정의 보수적 범위를 명시하거나 별도 후보/측정 기록으로 계산하고 계획에 합산 근거를 남긴다. 학습 이외의 시간과 GPU 점유 가능 시간을 구분한다. 최대 메모리 초과는 조건부 판정이다.

```sh
python3 "$SCRIPT" record-pilot ./research-run/state.json C1 ./pilot.json
python3 "$SCRIPT" pilot-estimate ./research-run/state.json C1
```

record-pilot은 입력을 검증한 뒤 저장하고 evaluation 이후를 stale로 바꾼다. 측정치와 계획을 다시 검토해야 완료 상태로 되돌릴 수 있다. 연구 탐색 요청만으로 데이터 다운로드나 긴 GPU 실험을 실행하지 않는다.

## 3. 데이터·체크포인트 이력

후보의 `provenance.assets` 배열에 각 자원을 기록한다. 해당 자원이 없는 연구는 `provenance={"status":"not_applicable","reason":"실제 사유"}`로 설명한다.

- id(고유), kind(dataset/checkpoint), name, version, source(공통 출처).
- identifier_strategy: 환자/영상의 식별·중복 검사 방식 또는 비민감 manifest 경로/해시. 환자 원본 ID, 인증정보, 제한된 데이터를 상태 파일에 복사하지 않는다.
- split: 훈련/개발/평가 분할 단위·버전·고정 시점·교집합 검사.
- pretraining_exposure: 체크포인트의 사전학습 데이터와 평가 데이터 노출 여부, 확인하지 못한 범위. 데이터 자원도 연결된 체크포인트 노출을 설명한다.
- rights: `{status: verified/unknown/restricted, reason, source}`. verified에는 실제 이용조건의 확인 출처가 필요하다.
- leakage: `{status: passed/pending/failed, reason, source}`. passed/failed에는 실제 검사 기록이 필요하다.

이용권 미확인/제한 또는 누출 검사 미완료/실패는 조건부다. 해당 실험 자체를 수행할 수 없는 실패는 기존 gates에도 fail로 반영해 탈락 처리한다. 데이터가 공개라는 사실만으로 권한·윤리·누출을 pass로 하지 않는다.

## 4. 연구 설계

후보의 `design`에 primary_comparison(핵심 비교), primary_outcome(주요 지표), independent_unit(독립 표본 단위), controls(통제 조건), repeated_runs(양의 정수), uncertainty(불확실성 추정), matched_budget(steps/gpu_time/other), budget_rationale(비교 예산의 근거)를 쓴다.

동일 스텝과 동일 GPU시간을 동시에 맞췄다고 가정하지 않는다. 선택한 예산에 따른 해석과 다른 비용의 실측 보고 방법을 설명한다. 환자 단위 분할과 영상 단위 평가처럼 단위가 다르면 상관을 처리할 방법을 명시한다. 실험 설계가 해당하지 않는 경우 `status=not_applicable`과 reason을 기록한다.

## 5. 검색 범위와 예산

`coverage`는 네 갈래의 요청/채택/수신/제외/실패/캐시/0건 횟수, 식별 가능한 중복, 미검색 갈래와 `search_plan.unreviewed_areas`를 보여 준다. 중복은 DOI·URL·문헌 ID의 일치만 검사하므로 누락된 식별자와 서로 다른 URL은 한계로 남긴다.

`search_plan.allocation`은 합이 1인 비율이다. 기본값은 recent 0.3, foundational 0.2, validation 0.2, novelty 0.3이다. 남은 전체 예산에서 다른 검증·노벨티 갈래의 미사용 목표를 빼서 권장 가용량을 계산한다. 요청/결과 상한은 기존대로 강제하며, 갈래별 배분은 권장값이다.

```sh
python3 "$SCRIPT" coverage ./research-run/state.json
```

새 검색 전 coverage의 suggested_requests_available/suggested_results_available을 보고 후반 검증 예산을 남긴다. 권장량이 0이면 다른 미완료 갈래를 먼저 수행하거나 배분 변경 사유를 search_plan에 기록한다. reserve-search와 Crossref search 응답의 allocation_advice에서도 확인할 수 있다. 캐시 재사용은 새 요청으로 세지 않는다. 예산 부족 시 미탐색 분야를 명시하고 탐색 범위를 좁힌다.

## 6. 투고처 재확인

투고 규정은 `journals[].guidelines`에 index/cost와 같은 verified/unverified 형식으로 기록한다.

```sh
python3 "$SCRIPT" journal-recheck ./research-run/state.json --as-of 2026-11-12 --max-age-days 90
```

위 날짜는 사용 예시이며 실행 시 실제 추천 기준일로 대체한다. 기준일 생략 시 실행 환경의 오늘을 사용한다. 저널은 index/cost/guidelines/schedule/metrics를, 학술대회는 guidelines/schedule/cost를 검사하고 결과를 current/stale/unverified/future_date로 출력한다. 기본 90일은 재열람 우선순위를 정하는 작업 기준이며 사실의 유효기간이 아니다. 최신 정보 요청이나 실제 투고 전에는 current여도 공식 페이지를 다시 확인한다. 이 명령 자체는 웹 조회나 verified 날짜 갱신을 하지 않는다.

## 7. 첫 주 체크리스트와 최종화

후보의 `first_week`은 `{id, category, day, text, done, evidence}` 작업 배열이다. category는 data/environment/minimum_experiment/measurement/decision. day는 1~7, done은 boolean이며 true일 때 확인 근거 source가 필요하다. 최종 선택 후보에는 다섯 범주의 작업이 모두 있어야 한다. 실험이 없는 연구에서는 같은 범주에 자료 확보·분석 환경·최소 검증·작업량 측정·진행 결정을 분야에 맞게 쓴다.

```sh
python3 "$SCRIPT" checklist ./research-run/state.json --candidate C1
```

`first-week.md`의 체크 항목으로 내보낸다. 실행 결과는 state에 반영한 뒤 다시 내보낸다. Markdown 체크만으로 상태가 역으로 변경되지는 않는다.

최상위 `report` 필드: as_of(YYYY-MM-DD), scope, limitations, next_actions, selected_candidate_ids. 선택 후보가 없으면 no_candidate_reason도 필요하다. stages는 complete 또는 사유가 있는 partial이어야 하며, partial의 사유는 report.stage_notes[단계명]에 쓴다. stale/pending을 완료로 숨기지 않는다.

```sh
python3 "$SCRIPT" validate ./research-run/state.json
python3 "$SCRIPT" validate ./research-run/state.json --final
python3 "$SCRIPT" export ./research-run/state.json --final --format all
```

일반 validate/export는 초안 저장용이다. --final은 메타데이터, 단계 상태, 선택 후보의 18개 계획 필드, 설계·이력·파일럿 상태·첫 주 작업, 주장 카드의 버전·발췌·해석을 추가 검사한다. 조건부 후보도 미확인 사항을 기록한 최종 제안으로 낼 수 있다. 완성된 제안과 실험 착수 가능성은 다른 판정이다. 최종 검증 실패 시 초안을 제공하고 빠진 정보를 알리며, 통과를 위해 근거를 만들어 내지 않는다.
