# 저널·학술대회 투고 전략

주제 제안에서는 `recommendation_stage=preliminary`, 주제 선택·설계 이후에는 `detailed`로 기록한다. 분야, 기여 유형, 원고·검증 수준, 언어, 일정, 비용을 기준으로 실제 투고할 수 있는 저널이나 학술대회를 고른다. 선호 투고처가 있으면 먼저 적합성을 검토하고, 범위가 맞지 않으면 이유와 대안을 제시한다. 색인 목표가 미정이어도 구체적인 투고처를 비교한다.

## 추천 단위

- **저널**(`category=journal`): 공식 저널명과 출판사 또는 발행 학회를 기록한다. Nature Portfolio 요청은 `Nature`, `Nature Communications` 등 개별 저널의 범위를 비교한다.
- **국내 학회**: 학회명을 단서로 해당 학회의 논문지와 회차별 학술대회를 구분한다. 예를 들어 `한국정보기술학회논문지`와 한국정보기술학회가 주최하는 해당 회차의 종합학술대회는 별개 투고처다.
- **학술대회**(`category=conference`): AAAI Conference on Artificial Intelligence, ACL 연례 학술대회, NAACL 연례 학술대회 등 공식 행사명을 사용하고 확인한 회차·연도와 트랙을 명시한다. 메인 트랙, 워크숍, 기타 논문 유형을 구분한다. 새 회차의 공고가 없으면 조사 후보로 표시한다.

SCIE·KCI 등은 확인된 저널에 덧붙이는 색인 정보다. 사용자가 색인을 필수 조건으로 지정하면 그 조건을 별도로 대조한다. 예시 투고처는 분야와 원고가 맞는 경우에만 후보에 포함한다. 관련 문헌이 있는 분야라는 사실만으로 해당 논문의 적합성을 단정하지 않는다.

## 공식 확인

- **저널**: 공식 Aims & Scope, 투고 규정, 최근 유사 논문, 논문 유형, OA·비용을 확인하고 저널명과 ISSN을 대조한다. 색인은 [Clarivate Master Journal List](https://mjl.clarivate.com/) 또는 [KCI](https://www.kci.go.kr/)에서 확인한다. 지표는 확인한 경우에만 기준 연도·분류와 함께 기록한다.
- **학술대회**: 해당 회차의 공식 논문 모집 공고(CFP), 트랙별 범위·논문 유형, 제출 경로, 마감일과 시간대, 등록비·참석 요건을 확인한다. 필요한 경우 심사 제출과 학회 커밋 마감을 구분한다. 다른 회차나 트랙의 마감·비용을 가져오지 않는다. 실제 투고 경로가 확인되지 않으면 미확인으로 표시한다.

변동 정보는 `value`, `status`, `source`로 저장한다. 공식 페이지를 읽고 투고처와 일치함을 대조한 경우만 `verified`로 기록한다. 회차·트랙별 출처 키는 [데이터 계약](data-contract.md)을 따른다. 비용에는 통화와 적용 조건을 적는다. 일정과 비용은 확인일을 출력하고 실제 투고 전 다시 확인한다.

## 추천 결과

각 연구 후보에 **공식 투고처명 · 유형 · 회차/트랙(해당 시) · 적합한 이유 · 유사 게재 논문 · 원고에 필요한 보강**을 먼저 제시한다. 공식 링크와 확인일을 함께 적고, 확인된 마감·비용·색인은 상세 정보로 덧붙인다. 해당 분야, 요구 검증 수준과 사용자의 제약으로 우선순위를 정한다. 확인하지 못한 항목은 표시하고, 명성이나 색인만으로 순위를 정하거나 게재 확률을 추정하지 않는다.

`journal-recheck`는 저널과 학술대회의 저장된 확인 날짜를 점검한다. [실행 절차](workflow.md)의 재확인 절을 따른다.

## 구조화된 제출 일정

정확한 회차·트랙·라운드의 공식 일정을 확인한 뒤 schedule의 기존 status/value/source에 mode를 추가한다. `fixed`의 deadlines는 최대 100개로, id, kind(abstract/submission/registration/commitment/other), at(UTC offset 포함 ISO 시각), timezone(IANA 시간대), requires(선행 마감 ID 배열)를 쓴다. 서로 다른 라운드는 별도 투고처 항목으로 기록한다. venue.round를 지정하면 공식 source.round도 일치해야 한다.

```json
{
  "mode": "fixed",
  "deadlines": [
    {"id":"abstract","kind":"abstract","at":"2027-01-05T23:59:59-12:00","timezone":"Etc/GMT+12"},
    {"id":"paper","kind":"submission","at":"2027-01-10T23:59:59-12:00","timezone":"Etc/GMT+12","requires":["abstract"]}
  ]
}
```

이 날짜는 형식 예시이며 실제 행사 정보가 아니다. AoE는 공식 페이지가 명시했을 때 UTC−12:00/Etc/GMT+12로 기록한다. 원문에 시간이 없으면 자의적으로 자정을 채우지 말고 기존 문자열과 확인 과제로 남긴다. IANA 시간대와 시각의 offset이 맞지 않으면 오류다. 초록 등록·원고 제출·ARR commitment 등 필수 경로를 requires로 연결하고, 순환·뒤늦은 선행 마감은 허용하지 않는다. 필수가 아닌 대안 경로는 별도 투고처 항목으로 분리한다.

후보의 submission_plan:

```json
{"status":"estimated","experiments_complete":"2027-01-01","timezone":"Asia/Seoul","writing_days":7,"assumptions":"원고 작성·공저자 검토·형식 준비 포함","source":{"local_file":"실제 계획 파일 절대 경로","location":"일정 가정","checked_at":"실제 확인일"}}
```

준비 예정일은 실험 완료 + 원고 준비 달력일이다. 날짜만 있는 완료 예정은 해당 시간대의 하루 끝으로 보수적으로 해석한다. 실제 작업량과 가용 시간도 별도 resource_plan에서 확인한다. 불명확하면 `{status:pending, reason, next_action}`으로 남긴다. 완료한 선행 제출은 completed_steps에 `{venue_id,deadline_id,completed_at(UTC offset 포함),evidence(source)}`로 기록하며, 기준 시각 이후 기록이나 근거 없는 완료를 허용하지 않는다. 마감 후 완료는 필수 경로를 충족시키지 않는다.

`journal-recheck --as-of <날짜 또는 offset 포함 시각>`은 문헌 확인일의 경과와 제출 가능 일정을 별도 출력한다. expired, blocked_prerequisite, pending_prerequisite, insufficient_preparation_time, readiness_unknown, ready_in_time 등을 구분한다. 날짜만 지정하고 같은 날 마감이면 정확한 시각을 재확인해야 한다. profile.timezone 미지정 시 기준일 해석에 UTC를 쓰며 출력에 명시한다. 상시 접수 저널은 공식 확인된 mode=rolling, deadlines=[]로 표시한다. 자유 서술 기존 일정은 needs_structure로 읽고 최종 보고서에도 확인 과제로 남긴다. 이 검사는 웹의 최신 일정을 조회하거나 실제 제출을 수행하지 않는다.
