# 독립 후보 생성과 검증

## 역할 실행

먼저 후보마다 문제·질문, 가까운 선행 연구 ID, 핵심 장애/확인 과제만 기록한다. `review.stage=screening`에서 데이터·기간·권한의 명백한 실패를 선별한다. 검토 가능 후보를 `detailed`로 승격하고, 막힌 후보는 `hold`와 재개 조건을 남긴다. 선별 점수는 상세 평가 점수와 섞지 않는다. 새로운 근거나 자원·접근권 변화가 순위를 바꾸면 보류 후보도 다시 검토한다.

`review-candidate <state> <ID> <review.json>`의 형식:

```json
{"stage":"screening","reason":"가까운 선행 연구와 실행 조건 우선 확인","main_blocker":"외부 검증 라벨 접근 미확인","next_actions":["접근 조건과 예상 소요 시간 확인"]}
```

`plan.problem`, `plan.question`, `novelty.closest_paper_ids`를 먼저 채운다. detailed에서도 reason과 next_actions를 기록한다. 승격/보류 이력은 review_history에 보존되며 해당 후보의 evaluation 이후는 재검토 대상이다. 기존 review 없는 후보는 상세 검토 형식으로 읽되 기존 필수 검사에 따른다. 최종 선택에는 상세 검토와 전체 근거·설계 검증을 모두 적용한다.

추세·공백·분야 연결·반박/중복·실행 가능성·투고 적합성·종합은 필요한 검토 관점이다. 매 후보에 일곱 역할을 모두 실행하지 않는다. 초기 선별은 함께 수행하고 유망 후보에서 부족하거나 논쟁적인 관점만 추가 검토한다. 에이전트가 허용되고 유용한 경우 독립 입력으로 검토한 뒤 교차 대조하며 호출 예산을 예약한다. 순차 검토를 독립 검증이라 하지 않는다. 결과는 agent_reviews에 role, claims, evidence, inferences, uncertainties, candidate_ids, objections로 기록한다. 하위 에이전트는 상태 파일을 쓰지 않는다.

고정 합성 입력 비교는 저장소 `tests/benchmark_review.py`로 재현한다. 알려진 접근 실패 3개를 먼저 보류하면 동일 예산에서 상세 검색 요청 6→3회이며 선택 후보의 핵심 근거와 필수 필드는 보존됐다. 실제 문헌·LLM 시간이나 토큰 절감 추정은 아니다. 결과와 측정 범위는 `docs/benchmarks/rc07-review-depth.json`에 기록한다.

## 후보별 노벨티 재검색

상세 검토로 진행하는 후보는 초기 검색과 별도로 반드시 `branch=novelty`인 검색을 기록한다.

1. 핵심 기여를 한 문장으로 고정한다.
2. 동일 문제·유사 방법·관련 적용 분야로 재검색한다. 한국어·영어와 동의어를 고려한다.
3. 가장 가까운 선행 연구를 실제로 열람한다.
4. 문제, 방법, 가정, 데이터, 평가, 기여의 6개 축으로 비교한다.
5. 차별성이 없으면 수정 후 다시 검색하거나 `duplicate`로 탈락시킨다.

`novelty`에 contribution, search_ids, closest_paper_ids, comparison, status, uncertainty를 저장한다. 상태는 pending / distinct_within_scope / duplicate. ‘해당 논문이 검색되지 않았다’는 부재 증명이 아니다. 단순 데이터셋·적용 분야 변경은 중요한 학술적 이유가 확인되지 않으면 차별성으로 인정하지 않는다.

뒤늦게 선행 연구를 찾으면 해당 후보의 novelty를 pending/duplicate로 수정하고 `invalidate <state> novelty --candidate <ID> --reason '새 선행 연구 발견'`를 수행한다. 모든 검색 결과를 재활용하되 후보별 비교와 판정은 다시 한다.

## 평가

각 후보의 `gap_ids`를 연구 공백에 연결하고, 공백의 `claim_ids`를 통해 실제 열람한 문헌의 근거까지 추적한다. 연결이 없거나 읽지 않은 근거를 사용하면 조건부로 평가한다. 부족 사유와 다음 확인 작업은 `gap_review`에 기록한다. 최종 추천으로 선택할 때는 연결을 보완한다. 구체적인 형식은 [데이터 계약](data-contract.md)을 따른다.

필수 조건 `data`, `resources`, `falsifiable`, `baseline`, `ethics_rights` 각각 pass/fail/unknown, reason, evidence를 기록한다. 대상 데이터·최소 실험·반증 조건·비교 기준·윤리/권한을 확인해야 한다. 윤리 심의가 필요 없는 것으로 판단한 경우에도 대상·판단 근거를 기록한다. 미확인을 pass로 바꾸지 않는다.

자원 평가는 조건별 실측 시간·평가·준비 비용을 합산하고, 사용자 확인 기간과 주당 가용 시간 및 예상 연구 작업량을 대조한다. 조건 수·반복 수와 파일럿 실행 수도 확인한다. 미확인 자원과 누락된 준비 기록은 확인 과제로 남긴다.

노벨티, 중요성, 관심 관련도, 구현 가능성, 평가 명확성, 재현 가능성, 투고 목표 적합성의 7기준에 0~5점을 준다. 각 점수에 근거·불확실성을 붙인다. 가중치는 `config.weights`로 설정한다. 목표가 미정이면 적합성 점수도 미정일 수 있다.

`evaluate`는 가중 평균과 별개로 필수 조건 실패를 rejected, 미확인·미완료 검증을 conditional로 분류한다. 정렬은 passed → conditional → rejected이다. 주제 자체의 가치와 즉시 실행 가능 여부를 구분한다. 조건부 후보도 확인 과제와 함께 제안할 수 있지만 검증 통과 후보 수에는 포함하지 않는다.

6축 comparison은 문자열 대신 축별 difference와 evidence 배열을 사용한다. [workflow.md](workflow.md)의 1~4절에 따라 버전과 본문 위치, 파일럿, 자원 이력, 연구 설계를 연결한다. 구형 비교나 초록만 있는 비교는 조건부로 남긴다.

후보의 plan은 문제 정의·기존 해결 범위·남은 공백·연구 목적·연구 질문·가설·최소 검증 실험·기대 기여를 연결한다. gap_ids의 실제 근거에서 출발하고 질문의 비교 대상과 관측 결과가 실험에 반영되는지 대조한다. 전체 23개 필드는 [출력 지침](output.md)을 따른다.
