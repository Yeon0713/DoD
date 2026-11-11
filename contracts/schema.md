# 공통 계약 (contracts/schema.md)

C1 데이터 계약, C2 분석 결과 계약, C3 계획 결과와 API 계약. 각 절은 그 줄의 주인이 고치고, 고치면 나머지 세 명에게 바로 알린다.

- C1 데이터 계약 (지호): 아직 이 파일에 없다. 지금 기준은 `server/db/models.py`.
- C3 계획 결과와 API 계약 (여헌): 아직 이 파일에 없다. 지금 기준은 `server/app/planner/data_shapes.py`의 출력 모양과 `docs/server-api-and-planner-guide.md`.

---

## C2 분석 결과 계약 (태성)

분석 줄이 쓰고, 계획 엔진·API·화면이 읽는다.

- **모양 정의**: `server/app/analysis/result_shapes.py`. 계획 엔진에 이미 있는 모양(`server/app/planner/data_shapes.py`)은 그대로 가져다 쓴다.
- **고정 샘플**: `contracts/fixtures/analysis/<테이블>.example.json` (데모 주간). 설명은 같은 폴더 `README.md`.
- **공통 규칙**: 시각은 서울 기준 ISO 8601에 `+09:00`을 붙인다(`2026-11-17T13:50:00+09:00`). 날짜는 `YYYY-MM-DD`. 코드값은 영어 대문자. 금액은 원 단위 정수.
- **`now` 규칙**: 모든 재계산은 `now`를 받고 `now` 이전에 생긴 데이터만 쓴다. 각 행의 `computed_at`·`labeled_at`·`detected_at`은 그 재계산의 `now`다. 읽는 쪽은 그 시각이 `now` 이전인 행만 쓴다.
- **시간대**: `MORNING`(오픈~11:00), `LUNCH`(11:00~17:00), `DINNER`(17:00~마감). 영업시간 전체가 세 칸에 들어간다. 경계는 매장 설정에서 사장님이 바꿀 수 있고, 설정이 없으면 이 기본 경계를 쓴다. 계획 엔진이 새 코드값을 받을 때까지는 분석 결과에 `NIGHT`도 허용한다(기존 고정 샘플).
- **재계산 시각 [가정]**: 매일 22:30(sales_daily, calendar_day, customer_cycle, sales_anomaly)과 알림 시각 10분 전(review_label, risk_signal).

### sales_daily: 하루 × 시간대 매출 (N2)

키: `(date, daypart)`. 월·주·요일 묶음은 API(`/api/sales`)가 만든다. 마감 시각이 지난 날만 만든다.

| 열 | 타입 | 뜻 |
|---|---|---|
| `date` | date | 서울 기준 날짜 |
| `daypart` | `MORNING` \| `LUNCH` \| `DINNER` | 시간대 |
| `sales_amount` | int | 그 칸에 주문된 매출 합 |
| `qty` | int | 판매 수량 합 |
| `food_cost` | int \| null | 메뉴 원가 합(수량 × 원가). 메뉴 원가가 하나라도 없으면 null |
| `labor_cost` | int \| null | 그 시간대와 겹치는 근무 시간 × 시급. 근무표가 없으면 null |
| `platform_fee` | int \| null | 배달앱 중개수수료 |
| `delivery_fee` | int \| null | 사장님이 내는 배달비 |
| `payment_fee` | int \| null | 결제수수료 |
| `profit` | int | `sales_amount` − 값이 있는 빠지는 항목의 합 |

- 빠지는 항목은 실제로 가져올 수 있는 데이터가 있을 때만 채운다. 비율로 지어내지 않는다.
- 배달앱 수수료는 앱, 매장 매출 구간, 배달 방식에 따라 매장마다 다르다. 정산서 금액이나 매장 설정값이 생기면 채운다.
- 영업시간 밖 주문은 넣지 않고 건수만 센다(목업 v1 에는 없다).

### calendar_day: 우리 매장 달력 (N3)

키: `(date, daypart, computed_at)`. 덮어쓰지 않고 재계산마다 쌓는다. 읽을 때는 같은 `(date, daypart)` 중 `computed_at ≤ now`인 최신 행을 쓴다 [가정]. 오늘부터 35일치.

| 열 | 타입 | 뜻 |
|---|---|---|
| `date`, `daypart` | date, 시간대 | 달력 칸 |
| `signal` | `HIGH` \| `NORMAL` \| `LOW` | `ratio` ≥ 1.15 HIGH, ≤ 0.85 LOW, 나머지 NORMAL |
| `baseline_sales` | int | 최근 8주 같은 요일·시간대 매출의 중앙값(행사·경기·비 온 날 제외) |
| `expected_sales` | int | `baseline_sales × (1 + Σ effect)`. 반올림하지 않는다 [가정] |
| `ratio` | float | `expected_sales / baseline_sales`, 소수 둘째 자리 |
| `reasons` | list[`{tag, ref_id, effect}`] | 이유 목록. 아래 표 |
| `reason_text` | str | 카드에 보일 이유 한 줄. 1차는 템플릿, N7(지호)에서 바꾼다 |
| `computed_at` | datetime | 계산한 재계산 시각 |

| `tag` | `ref_id` 형식 | 붙이는 조건 |
|---|---|---|
| `EVENT` | 행사 id (`event_012`) | 매장에서 2km 안, 시간이 겹치는 칸 |
| `GAME` | 경기 id (`game_031`) | 시작 시각이 속한 시간대와 그다음 시간대 |
| `WEATHER` | `weather:<날짜>:<RAIN\|HEAT\|COLD>` [가정] | 비 5mm 이상, 최고 33도 이상, 최저 영하 12도 이하 |
| `SEASON` | `season_winter` \| `season_summer` | 예보 최고기온이 3일 이어서 10도 아래·25도 위로 넘어간 날부터 다음 전환까지 |

- `effect`는 비율이다(0.21 = +21%). 과거 같은 종류의 날에 실제 매출이 기준선보다 달랐던 정도의 평균이다.
- EVENT·GAME·WEATHER 는 과거 사례가 없거나 효과가 ±10% 안이면 태그를 붙이지 않는다. SEASON 은 이 규칙에서 빠진다 [가정].

### customer_cycle: 손님 주문 주기 (N4)

키: `(customer_key, computed_at)`. 주기가 없는 손님도 `NONE`으로 넣는다.

| 열 | 타입 | 뜻 |
|---|---|---|
| `customer_key` | str | 손님 가명. 이름·전화번호는 다루지 않는다 |
| `cycle` | `WEEKLY` \| `MONTHLY` \| `NONE` | 주간을 먼저 본다 |
| `next_expected_at` | datetime \| null | 다음 예상 주문 시각. `NONE`이면 null |
| `expected_daypart` | 시간대 \| null | 다음 예상 시간대. `NONE`이면 null |
| `intervals_days` | list[int] | 최근 3개 주문 간격(일), 오래된 것부터. 주문이 4번 미만이면 있는 만큼 |
| `computed_at` | datetime | 계산한 재계산 시각 |

- WEEKLY: 최근 4회 중 3회 이상이 같은 요일·비슷한 시간대이고, 최근 3개 간격 중 2개 이상이 5~9일. 다음 예상은 마지막 주문 다음의 같은 요일, 최근 주문 시각의 중앙값.
- MONTHLY: 최근 3개 간격 중 2개 이상이 25~35일. 다음 예상은 마지막 주문에서 28일 뒤 같은 시각.

### review_label: 리뷰 분류 (N1)

키: `review_id`. 한 번 붙인 분류는 다시 계산하지 않는다. 계획 엔진에 넘길 때는 `Review.label`에 넣는다(`ReviewLabelRow.to_label()`).

| 열 | 타입 | 뜻 |
|---|---|---|
| `review_id` | str | 원본 리뷰 id (`rv_118`) |
| `sentiment` | `POSITIVE` \| `NEGATIVE` \| `MIXED` | 감정 |
| `complaint_types` | list | `TASTE`, `PORTION`, `HYGIENE`, `PHOTO_MISMATCH`, `DELIVERY_DELAY`, `SERVICE` 중 0개 이상 |
| `complaint_groups` | list | 코드로 붙인다. TASTE·PORTION·HYGIENE·PHOTO_MISMATCH → `FOOD`, DELIVERY_DELAY → `DELIVERY`, SERVICE → `SERVICE` |
| `is_quick` | bool | 묶음이 하나라도 있으면 true. 별점과 관계없다 |
| `labeler` | `HCX` \| `RULE` | HyperCLOVA X, 또는 모델 실패 시 키워드 규칙 |
| `labeled_at` | datetime | 분류한 재계산 시각 |

- 모델에는 리뷰 본문만 넘긴다. 닉네임, `customer_key`, 별점은 넘기지 않는다.

### risk_signal: 위험 신호 (N5)

키: `risk_id`. 한 번 연 위험 신호는 다시 만들지 않고, 같은 유형이 열려 있으면 `review_ids`와 `last_at`만 늘린다.

| 열 | 타입 | 뜻 |
|---|---|---|
| `risk_id` | str | `risk_` + 숫자 세 자리, 여는 순서대로 [가정]. 계획 id(`REVIEW_FIX:risk_004:...`)에 쓰여서 다시 계산해도 바뀌면 안 된다 |
| `complaint_type` | 불만 유형 | 같은 유형이 7일 안에 3건이면 연다 |
| `review_ids` | list[str] | 근거 리뷰 |
| `first_at`, `last_at` | datetime | 근거 리뷰 중 가장 이른·늦은 작성 시각 |
| `detected_at` | datetime | 찾은 재계산 시각 |
| `status` | `OPEN` | 1차는 OPEN 만 |

### sales_anomaly: 매출 이상 (N8, 지호)

키: `(date, daypart)`. 실제 매출이 기준선과 크게 다른 칸. 

| 열 | 타입 | 뜻 |
|---|---|---|
| `date`, `daypart` | date, 시간대 | 칸 |
| `actual_sales` | int | sales_daily 의 `sales_amount` |
| `baseline_sales` | int | calendar_day 와 같은 기준선 |
| `ratio` | float | `actual_sales / baseline_sales` |
| `known_reasons` | list[tag] | 그날 달력 태그. 비어 있으면 달력으로 설명되지 않는 일이다 |
| `detected_at` | datetime | 찾은 재계산 시각 |
