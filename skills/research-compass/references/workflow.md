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
| evaluation_hours, setup_hours | 해당 조건의 전체 반복에 추가할 평가·준비 시간. 생략 시 0이며 포함 범위를 assumptions에 명시 |
| assumptions | 측정 범위, 워밍업/입출력 포함 여부, 처리량 변동과 추정 한계 |
| source | 실측 로그 파일/URL·위치·확인일 |

예상 시간 = elapsed_seconds / measured_steps × steps_per_run × runs × (1 + overhead_fraction) / 3600 + evaluation_hours + setup_hours.

같은 측정 조건에서 외삽한다. overhead_fraction에 이미 포함한 평가·준비 시간을 evaluation_hours/setup_hours에 중복 가산하지 않으며, 포함 범위를 assumptions에 쓴다. 비용이 다른 비교 조건은 `pilot={"status":"measured","conditions":[조건별 측정 객체]}`로 기록한다. 각 조건에는 고유 id와 status=measured 및 위 측정 필드가 필요하다. 조건별 예상 시간을 합산하며, 메모리는 모든 조건을 검사한다.

기존 단일 측정 형식도 사용할 수 있다. 이 경우 runs는 모든 조건과 반복을 합친 전체 실행 수이며, 같은 측정 비용을 적용할 수 있다는 근거를 assumptions에 적는다. `design.conditions`는 비교 조건 수, `design.repeated_runs`는 조건당 반복 수다. 전체 실행 수는 두 수의 곱과 일치해야 하며, 조건별 측정을 제공하면 각 조건의 반복 수까지 일치해야 한다.

```sh
python3 "$SCRIPT" record-pilot ./research-run/state.json C1 ./pilot.json
python3 "$SCRIPT" pilot-estimate ./research-run/state.json C1
```

record-pilot은 입력을 검증한 뒤 저장하고 evaluation 이후를 stale로 바꾼다. 측정치와 계획을 다시 검토해야 완료 상태로 되돌릴 수 있다. 연구 탐색 요청만으로 데이터 다운로드나 긴 GPU 실험을 실행하지 않는다.

### 기간·가용 시간과 연구 작업량

`profile.resource_budget`에 사용자가 확인한 가용 시간을 기록한다. 자연어 duration 값과 구분해 관리하며, ‘2개월’ 같은 표현에서 실제 사용 가능 시간을 임의로 산정하지 않는다.

- status=confirmed일 때 weeks는 양의 유한 수다. gpu_hours_per_week와 work_hours_per_week는 주당 0 이상의 유한 시간이다. source는 사용자 답변 또는 일정 확인 기록의 공통 출처 형식이다.
- 주당 값이 누락되거나 null이면 그 가용량은 미확인이다. status=pending일 때 reason과 measurement_plan을 기록한다. 기존 세션에 resource_budget이 없으면 가용 시간을 확인할 과제로 표시한다.
- 가용 GPU 시간 = weeks × gpu_hours_per_week. 가용 연구 작업시간 = weeks × work_hours_per_week.

후보의 `resource_plan`에는 사람이 수행하는 전체 연구 작업량을 기록한다. `status=estimated`, `work_hours`, `assumptions`, `source`가 필요하다. 작업량을 아직 산정하지 못했으면 `status=pending`, `reason`, `measurement_plan`으로 기록한다.

GPU 실험이 없는 연구는 pilot에 status=not_applicable과 사유를 적고, resource_plan의 작업시간을 연구 작업시간 예산과 대조한다. 설계나 데이터 자원이 해당하지 않는 경우도 해당 기록에 실제 사유를 적는다. GPU 실험이 있는 연구에서도 문헌 검토·구현·분석·원고 작성 등 사람이 수행할 작업시간을 산정한다.

예산은 같은 GPU 자원에서 순차 실행하는 실험의 점유 시간과 확인한 연구 작업시간을 각각 비교한다. 병렬 장비나 다른 하드웨어에 대한 처리량 환산은 실제 측정·자원 할당에 근거해야 한다. 각 예산에 들어가더라도 실제 선후 관계와 달력 일정은 schedule에서 확인한다.

```sh
python3 "$SCRIPT" profile ./research-run/state.json ./profile.json
python3 "$SCRIPT" pilot-estimate ./research-run/state.json C1
```

pilot-estimate와 record-pilot은 측정 기반 예상치와 resource_check를 반환한다. 보고서는 작업량의 가정·출처와 가용 시간 대조를 출력한다. 시간·메모리 초과, 미측정, 가용 시간 미확인, 실행 수 불일치와 준비 기록 누락은 conditional 판정에 반영한다. 명시한 기록의 형식 오류는 validate에서 보고한다. 초안은 새 기록의 누락을 표시하면서 읽을 수 있고, 최종 선택 후보에는 resource_plan의 예상 또는 미산정 사유·측정 계획이 필요하다.

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

후보의 `design`에 primary_comparison(핵심 비교), primary_outcome(주요 지표), independent_unit(독립 표본 단위), controls(통제 조건), repeated_runs(양의 정수), uncertainty(불확실성 추정), matched_budget(steps/gpu_time/other), conditions(실측 GPU 실험의 비교 조건 수), budget_rationale(비교 예산의 근거)를 쓴다.

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

위 날짜는 사용 예시이며 실행 시 실제 추천 기준일로 대체한다. 기준일은 offset 포함 ISO 시각도 허용한다. 생략 시 현재 시각을 profile.timezone(미지정 UTC)으로 해석한다. 저널은 index/cost/guidelines/schedule/metrics를, 학술대회는 guidelines/schedule/cost를 검사하고 결과를 current/stale/unverified/future_date로 출력한다. 기본 90일은 재열람 우선순위를 정하는 작업 기준이며 사실의 유효기간이 아니다. 최신 정보 요청이나 실제 투고 전에는 current여도 공식 페이지를 다시 확인한다. 이 명령 자체는 웹 조회나 verified 날짜 갱신을 하지 않는다. 구조화한 마감·선행 제출·실험 완료와 원고 준비 기간의 대조는 [투고처 일정 형식](journals.md)을 따른다.

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

일반 validate/export는 초안 저장용이다. --final은 메타데이터, 단계 상태, 선택 후보의 23개 계획 필드, 설계·이력·파일럿 상태·첫 주 작업, 주장 카드의 버전·발췌·해석을 추가 검사한다. 최종 선택 후보에는 공백·주장·실제 열람 문헌의 유효한 연결이 필요하다. 연결이 부족하면 조건부 초안으로 제공하고 gap_review에 부족 사유와 다음 확인 작업을 기록한다. 데이터·자원 등 실행 조건이 미확인인 조건부 후보도 이 연결을 갖추면 미확인 사항을 적은 최종 제안으로 낼 수 있다. 선택 후보가 없으면 no_candidate_reason과 next_actions에 확인 범위와 다음 행동을 기록한다. 완성된 제안과 실험 착수 가능성은 다른 판정이다. 최종 검증 실패 시 초안을 제공하고 빠진 정보를 알리며, 통과를 위해 근거를 만들어 내지 않는다.

## 8. 의미 있는 효과와 표본·정밀도

최종 선택 후보의 `design.effect_plan`을 기록한다. 분야·자료·지표에 맞는 근거를 직접 확인하며, 모든 연구에 같은 검정력 공식을 적용하지 않는다. 계산은 해당 통계 설계의 공인 도구·시뮬레이션 등으로 별도 수행하고 방법·가정·위치를 남긴다. 이 CLI는 표본 수를 자동 산출하거나 통계적 타당성을 인증하지 않는다.

- 정량 연구: `status=quantitative`, metric(효과 척도), minimum_effect(의미 있는 최소 변화의 양의 크기), unit(독립 단위, design.independent_unit과 정확히 일치), required_units(필요 독립 표본 양의 정수), available_units(확보 수 0 이상), basis(산정 방법·근거), assumptions, source.
- precision: `{kind: ci_half_width/power/simulation, target: 양수, level: 신뢰수준 또는 power의 alpha}`. power의 target과 level은 0과 1 사이. simulation은 target의 의미·단위와 통과 기준을 basis에 설명한다. 사건 중심 분석은 events `{unit, required, available}`도 기록하고 필요한 경우 required_repeated_runs를 쓴다. 환자·영상·모델 반복을 독립 표본으로 혼용하지 않는다. 군집·대응·반복 구조는 assumptions와 uncertainty에 처리 방법을 적는다.
- 미산정: `status=pending`, reason, measurement_plan, measurement_task_id. 측정 계획은 유병률·불일치 사건·분산 등을 첫 주에 어떻게 셀지 구체화하고 실제 `first_week`의 measurement 작업 ID에 연결한다. 숫자를 추정해 완성하지 않는다.
- 정성·이론 연구: `status=qualitative`, reason, criteria(예: 반례 탐색·증명 검토·자료 포화 기준), assumptions, source. design 자체가 not_applicable인 경우에도 이 판단 기준은 설명한다.

정량 계획의 `resource_plan.scope`에는 unit(같은 독립 평가 단위), evaluation_units(비용에 포함한 평가 표본 수), repeated_runs(설계와 같은 반복 수)를 기록한다. 사건 계획이 있으면 scope.events `{unit,count}`도 포함한다. 표본·반복 확대가 산정 범위를 벗어나면 conditional이며 평가·준비·작업시간과 파일럿 실행 수를 다시 계산한다. 훈련 영상 수 pilot.dataset_size를 환자 단위 평가 표본 수로 비교하지 않는다. 변경 후 `invalidate <state> evaluation --candidate <ID> --reason '표본/반복 계획 변경'`으로 재검토를 기록한다. 기존 계획 누락 초안은 읽으며 미작성 과제를 표시하고 최종 선택에서 명시적 계획을 요구한다.
