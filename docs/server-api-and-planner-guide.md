# 서버 API와 계획 엔진 사용 안내

도나 서버의 **API 6개**와 **계획 엔진**을 처음 보는 사람이 바로 쓰고 고칠 수 있도록 정리한 문서입니다.

- 화면을 만드는 사람(프론트엔드): [1. 빠르게 시작하기](#1-빠르게-시작하기), [4. API 사용법](#4-api-사용법)
- 서버를 고치는 사람: [3. 폴더 구조](#3-폴더-구조와-파일-역할), [5. 계획 엔진](#5-계획-엔진), [8. 자주 하는 작업](#8-자주-하는-작업)

---

## 0. 지금 상태 한눈에 보기

| 무엇 | 상태 |
|---|---|
| API 6개 (`today`, `plan`, `calendar`, `sales`, `reviews`, `settings`) | ✅ 동작함. 지금은 **예시 데이터**를 돌려줌 |
| 계획 엔진 (언제 무엇을 알릴지 계산) | ✅ 동작함. 데모 주간 정답과 일치 (테스트 24개 통과) |
| API ↔ 계획 엔진 연결 | ⏳ 아직. `today`, `plan` API는 계산 결과가 아닌 예시 파일을 돌려줌 |
| DB 연결 | ⏳ 아직. 지호의 DB가 나오면 연결 |

**지금 API가 돌려주는 데이터는 전부 예시입니다.** 모든 응답에 `"is_example": true`가 붙어 있습니다. 실제 데이터로 바뀌면 `false`가 됩니다.

---

## 1. 빠르게 시작하기

### 1-1. 처음 한 번만

```bash
cd DoD/server
```
> server 폴더로 이동합니다. 아래 명령은 모두 이 폴더에서 실행합니다.

```bash
python3 -m venv .venv
```
> 이 프로젝트 전용 파이썬 가상환경을 `.venv` 폴더에 만듭니다. (Windows는 `python -m venv .venv`)

```bash
source .venv/bin/activate
```
> 가상환경을 켭니다. 터미널 앞에 `(.venv)`가 보이면 켜진 것입니다. (Windows Git Bash는 `source .venv/Scripts/activate`)

```bash
pip install -r requirements.txt
```
> 서버에 필요한 패키지(FastAPI, pytest 등)를 설치합니다.

예시 데이터만 쓰는 지금 단계에서는 **`.env` 파일과 API 키가 없어도 서버가 켜집니다.**

### 1-2. 서버 켜기

```bash
uvicorn app.main:app --reload
```
> 서버를 `http://127.0.0.1:8000`에서 켭니다. `--reload`를 붙이면 코드를 저장할 때마다 자동으로 다시 켜집니다. 끌 때는 `Ctrl + C`.

### 1-3. 잘 켜졌는지 확인

브라우저에서 아래 주소를 엽니다.

| 주소 | 보이는 것 |
|---|---|
| http://127.0.0.1:8000/health | `{"status":"ok"}` 이면 서버가 살아 있음 |
| http://127.0.0.1:8000/docs | **API 설명서**. 모든 API의 주소, 넣는 값, 응답 모양을 보고 직접 호출해 볼 수 있음 |
| http://127.0.0.1:8000/api/today | 오늘의 카드 예시 응답 |

### 1-4. 테스트 돌리기

```bash
python -m pytest -v
```
> 계획 엔진 테스트 24개를 실행합니다. 모두 `PASSED`면 규칙대로 계산되고 있는 것입니다. 반드시 `server/` 폴더에서 실행해야 합니다.

---

## 2. 전체 그림

### 2-1. 요청 하나가 처리되는 흐름

```
사장님 화면(프론트)
   │  GET http://서버주소/api/today
   ▼
modules/today/router.py          주소를 받는 곳
   │
   ▼
modules/today/data_provider.py   데이터를 가져오는 곳
   │   지금: contracts/sample_responses/today_response.example.json 읽기
   │   나중: 계획 엔진(planner/make_plan.py) 결과 쓰기
   ▼
modules/today/response_format.py 응답 모양 검사 (필드가 빠지거나 틀리면 서버 오류)
   │
   ▼
JSON 응답 → 화면이 카드로 그림
```

### 2-2. 팀 안에서의 위치

```
지호: 가게 데이터 (매출, 리뷰, 행사, 날씨 …)
   ↓
태성: 분석 (달력 수요 신호, 손님 주문 주기, 리뷰 분류, 위험 신호)
   ↓
계획 엔진 (server/app/planner): 언제 무엇을 알릴지 계산
   ↓
API (server/app/modules): 화면에 데이터 전달
   ↓
영웅: 화면 (오늘의 카드, 이번 주 달력, 설정)
```

---

## 3. 폴더 구조와 파일 역할

```
DoD/
├── contracts/
│   └── sample_responses/            화면에 보낼 응답 예시 (API가 지금 돌려주는 데이터)
│       ├── today_response.example.json
│       ├── plan_response.example.json
│       ├── calendar_response.example.json
│       ├── sales_response.example.json
│       ├── reviews_response.example.json
│       └── settings_response.example.json
│
├── docs/
│   └── server-api-and-planner-guide.md   지금 보고 있는 문서
│
└── server/
    ├── requirements.txt             필요한 패키지 목록
    ├── app/
    │   ├── main.py                  서버 시작점. 모듈 자동 등록, CORS, 오류 응답 등록
    │   ├── core/                    모든 곳에서 같이 쓰는 도구
    │   │   ├── config.py            .env 설정 읽기
    │   │   ├── seoul_time.py        서울 시각 도구, 날짜 기간 확인
    │   │   ├── error_response.py    오류 응답 모양 통일, 기간 검사
    │   │   ├── sample_response_loader.py  응답 예시 JSON 읽기
    │   │   └── ncloud.py, clova.py, maps.py, api_hub.py, sens.py  네이버 API 호출
    │   │
    │   ├── modules/                 API 창구. 폴더 하나 = API 하나
    │   │   ├── today/  plan/  calendar/  sales/  reviews/  settings/
    │   │   └── _template/           새 모듈을 만들 때 복사하는 틀
    │   │
    │   └── planner/                 계획 엔진 (FastAPI 없이 순수 파이썬)
    │       ├── data_shapes.py       입력·출력 데이터 모양, 코드값 목록
    │       ├── notification_time_helpers.py  "다음 알림 시각 찾기" 같은 도우미
    │       ├── rule_review_reply.py    ① 리뷰 답글 규칙
    │       ├── rule_reorder_nudge.py   매달 단골 재주문 권유 규칙
    │       ├── rule_menu_order.py      ② 메뉴판 바꾸기 규칙
    │       ├── rule_poster.py          ③ 포스터 규칙
    │       ├── rule_complaint_fix.py   ④ 반복 불만 개선 규칙
    │       ├── info_alerts.py          승인 없는 알림 (월요일 주간 예고, 매출 이상)
    │       ├── priority_and_grouping.py  우선순위 매기고 알림 시각별로 묶기
    │       └── make_plan.py            입구. 위 파일들을 순서대로 부름
    │
    └── tests/
        └── planner/
            ├── sample_inputs/demo_week_inputs.example.json  테스트용 입력 예시
            ├── test_notification_time_helpers.py  도우미 함수 테스트
            ├── test_rules.py        할 일 종류별 규칙 테스트
            └── test_demo_week.py    데모 주간 전체가 정답과 같은지 테스트
```

### 3-1. 모듈 폴더 안의 4개 파일

`modules/` 아래 6개 폴더는 모두 같은 구성입니다.

| 파일 | 역할 | 언제 고치나 |
|---|---|---|
| `__init__.py` | 빈 파일. 파이썬 패키지 표시 (필수) | 안 고침 |
| `router.py` | API 주소와 받는 값(`?from=` 등) 정의. **이름 고정**, 안에 `router` 변수 필수 | 주소나 받는 값을 바꿀 때 |
| `response_format.py` | 응답 모양 (Pydantic 클래스) | 화면이 새 필드를 요청할 때 |
| `data_provider.py` | 데이터를 어디서 가져와서 어떻게 거를지 | 예시 → 실제 데이터로 바꿀 때 |

`modules/` 안에 폴더를 만들고 `router.py`에 `router`를 두면 **서버가 켜질 때 자동으로 `/api/폴더이름` 주소가 생깁니다.** `main.py`는 고치지 않아도 됩니다. 이름이 `_`로 시작하는 폴더(`_template`)는 등록되지 않습니다.

---

## 4. API 사용법

### 4-1. 모든 API 공통 규칙

| 규칙 | 내용 |
|---|---|
| 주소 | `http://서버주소/api/모듈이름` (로컬: `http://127.0.0.1:8000/api/today`) |
| 시각 | 항상 서울 시각, ISO 형식에 `+09:00`. 예) `"2026-11-17T14:00:00+09:00"` |
| 날짜 | `"YYYY-MM-DD"`. 예) `"2026-11-17"` |
| 코드값 | 영어 대문자 (`LUNCH`, `APPROVAL_REQUEST` 등). 화면 문구는 프론트가 한국어로 바꿈. [부록 A](#부록-a-코드값-목록) 참고 |
| 예시 표시 | 모든 응답 맨 위에 `"is_example": true/false` |
| 기간 조건 | `?from=2026-11-16&to=2026-11-22` (양 끝 포함, 둘 다 생략 가능) |

### 4-2. 오류 응답

모든 오류는 같은 모양입니다. 프론트는 `error.code`로 종류를 구분하고 `error.message`를 보여주면 됩니다.

```json
{
  "error": {
    "code": "INVALID_DATE_RANGE",
    "message": "from 날짜가 to 날짜보다 늦습니다."
  }
}
```

| HTTP 상태 | code | 언제 |
|---|---|---|
| 400 | `INVALID_DATE_RANGE` | `from`이 `to`보다 늦음 |
| 400 | `SLOT_IN_BUSY_DAYPART` | 설정에서 알림 시각을 바쁜 시간대(점심, 저녁)에 넣음 |
| 400 | `SLOT_OUTSIDE_OPEN_HOURS` | 설정에서 알림 시각을 영업시간 밖에 넣음 |
| 404 | `NOT_FOUND` | 없는 주소 |
| 422 | `INVALID_INPUT` | 값 형식이 틀림. `details`에 어느 칸이 왜 틀렸는지 들어 있음 |
| 500 | `INTERNAL_ERROR` | 서버 내부 오류 (서버 터미널에 원인이 찍힘) |

### 4-3. 프론트에서 호출하는 예

```javascript
const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL; // 예) http://127.0.0.1:8000

const res = await fetch(`${BASE_URL}/api/plan?from=2026-11-16&to=2026-11-22`);
const data = await res.json();
if (!res.ok) {
  alert(data.error.message); // 오류도 항상 같은 모양
} else {
  console.log(data.plan_items);
}
```

서버 주소는 코드에 직접 쓰지 말고 환경 변수로 두세요. 배포하면 네이버클라우드 주소로 바뀝니다.

**CORS**: 브라우저는 다른 주소의 서버를 부를 때 허락된 주소인지 확인합니다. 화면 주소가 `http://localhost:3000`이 아니면 `server/.env`의 `CORS_ORIGINS`에 추가해야 합니다. 안 하면 브라우저 콘솔에 `CORS policy` 오류가 뜹니다.

---

### 4-4. `GET /api/today` 오늘의 카드

오늘 알림 시각별 **카드 묶음**을 돌려줍니다. 받는 값은 없습니다.

```json
{
  "is_example": true,
  "date": "2026-11-17",
  "batches": [
    {
      "slot_at": "2026-11-17T10:00:00+09:00",
      "slot": "OPENING",
      "entries": [
        {"plan_id": "POSTER:game_031:2026-11-19", "notice_id": null, "notify_kind": "EXECUTE_REMINDER", "priority": 4}
      ]
    },
    {
      "slot_at": "2026-11-17T14:00:00+09:00",
      "slot": "AFTERNOON",
      "entries": [
        {"plan_id": "REVISIT_REPLY:rv_118:2026-11-17", "notice_id": null, "notify_kind": "APPROVAL_REQUEST", "priority": 1},
        {"plan_id": "REVIEW_FIX:risk_004:2026-11-17", "notice_id": null, "notify_kind": "APPROVAL_REQUEST", "priority": 2},
        {"plan_id": "MENU_ORDER:2026-11-18:2026-11-18", "notice_id": null, "notify_kind": "APPROVAL_REQUEST", "priority": 3}
      ]
    }
  ]
}
```

| 필드 | 뜻 |
|---|---|
| `batches` | 알림 시각별 묶음. 시간순. 알림이 없는 시각은 아예 없음 |
| `slot` | `OPENING`(출근 후 10:00), `AFTERNOON`(오후 14:00), `CLOSING`(마감 전 21:30) |
| `entries` | 그 시각에 보여줄 카드. **이미 우선순위 순서로 정렬됨** |
| `plan_id` / `notice_id` | 둘 중 하나만 있음. 카드 내용은 `/api/plan`에서 같은 id를 찾아서 봄 |
| `notify_kind` | `APPROVAL_REQUEST` 승인 요청, `EXECUTE_REMINDER` 실행 알림, `PREVIEW` 월요일 예고, `NOTICE` 매출 이상 |
| `priority` | 1 불만 리뷰, 2 반복 불만 개선, 3 내일 실행할 일, 4 그 밖 |

**today와 plan의 관계**: today는 "오늘 몇 시에 무엇을 알릴지"를 **id로만** 알려줍니다. 카드에 보일 이유 한 줄, 실행 시각 같은 내용은 plan에 있습니다. 할 일 하나가 여러 알림에 나오기 때문에(예: 월요일에 승인 요청, 화요일에 실행 알림) 이렇게 나눴습니다.

```
today의 entry  plan_id: "POSTER:game_031:2026-11-19"
                        │ 같은 id
plan의 item    plan_id: "POSTER:game_031:2026-11-19"
               reason_line: "목요일 국가대표 축구 경기 홍보 포스터를 올려요."
               approval_request_at, execute_at …
```

> 지금 예시 파일은 데모 주간 화요일(11/17) 하루치를 늘 돌려줍니다. 계획 엔진을 연결하면 실제 오늘 날짜의 묶음이 나옵니다.

---

### 4-5. `GET /api/plan` 할 일 목록

| 받는 값 | 예 | 뜻 |
|---|---|---|
| `from` | `2026-11-16` | 시작 날짜 (포함, 생략 가능) |
| `to` | `2026-11-22` | 끝 날짜 (포함, 생략 가능) |

**고르는 기준**: 할 일은 승인 요청 시각이나 실행 시각이 기간 안에 있으면 포함하고, 알림은 알림 시각이 기간 안에 있으면 포함합니다.

```json
{
  "is_example": true,
  "plan_items": [
    {
      "plan_id": "POSTER:game_031:2026-11-19",
      "task_type": "POSTER",
      "revisit_class": null,
      "basis": {"kind": "GAME", "ref_id": "game_031"},
      "target_date": "2026-11-19",
      "approval_request_at": "2026-11-16T14:00:00+09:00",
      "execute_at": "2026-11-17T10:00:00+09:00",
      "deadline_at": "2026-11-19T20:00:00+09:00",
      "reason_line": "목요일 국가대표 축구 경기 홍보 포스터를 올려요.",
      "planned_at": "2026-11-15T22:30:00+09:00"
    }
  ],
  "notice_items": [
    {
      "notice_id": "SALES_ANOMALY:2026-11-17:LUNCH",
      "kind": "SALES_ANOMALY",
      "slot_at": "2026-11-18T10:00:00+09:00",
      "refs": ["2026-11-17"],
      "text": "어제 점심 매출이 평소보다 35% 많았어요. 달력에 없던 일이에요."
    }
  ]
}
```

**할 일(`plan_items`) 필드**

| 필드 | 뜻 |
|---|---|
| `plan_id` | `{할일종류}:{근거id}:{대상날짜}`. 다시 계산해도 같은 값 |
| `task_type` | `REVISIT_REPLY` 리뷰 답글, `MENU_ORDER` 메뉴판, `POSTER` 포스터, `REVIEW_FIX` 반복 불만 개선, `REORDER_NUDGE` 재주문 권유 |
| `revisit_class` | 리뷰 답글일 때만. `QUICK` 불만, `WEEKLY` 매주 단골, `MONTHLY` 매달 단골, `BASIC` 일반 |
| `basis` | 근거. `kind`(리뷰, 손님, 행사, 경기, 위험 신호, 달력 날짜)와 `ref_id` |
| `approval_request_at` | 사장님께 승인을 요청하는 시각 |
| `execute_at` | 실행 시각. 반복 불만 개선은 `null` |
| `deadline_at` | 실행 기한 |
| `reason_line` | 카드에 보일 이유 한 줄 |
| `planned_at` | 이 할 일의 근거가 생긴 시각 |

**알림(`notice_items`) 필드**: 승인이 필요 없는 알림입니다. `kind`는 `WEEKLY_PREVIEW`(월요일 주간 예고) 또는 `SALES_ANOMALY`(매출 이상)이고, `text`가 그대로 보여줄 문장입니다.

---

### 4-6. `GET /api/calendar` 이번 주 달력

받는 값: `from`, `to` (plan과 같음). 날짜 × 시간대(점심, 저녁, 야간) **칸 목록**을 돌려줍니다.

```json
{
  "is_example": true,
  "cells": [
    {
      "date": "2026-11-19",
      "daypart": "DINNER",
      "signal": "HIGH",
      "baseline_sales": 820000,
      "expected_sales": 1033200,
      "ratio": 1.26,
      "reasons": [
        {"tag": "SEASON", "ref_id": "season_winter", "effect": 0.05},
        {"tag": "GAME", "ref_id": "game_031", "effect": 0.21}
      ],
      "reason_text": "저녁에 국가대표 축구 경기가 있어 배달이 늘 것 같아요",
      "computed_at": "2026-11-15T22:30:00+09:00"
    }
  ]
}
```

| 필드 | 뜻 |
|---|---|
| `signal` | 수요 신호. `HIGH` 많음, `NORMAL` 보통, `LOW` 적음 (칸 색에 사용) |
| `baseline_sales` | 평소 매출 (최근 같은 요일·시간대 기준) |
| `expected_sales` | 예상 매출 |
| `ratio` | 예상 ÷ 평소. 1.15 이상이면 HIGH, 0.85 이하면 LOW |
| `reasons` | 이유 태그 목록. `tag`는 `EVENT` 행사, `GAME` 경기, `WEATHER` 날씨, `SEASON` 계절. `effect` 0.21은 +21% |
| `reason_text` | 칸을 눌렀을 때 보일 이유 한 줄 |

예시 데이터는 데모 주간 21칸입니다. 11/19 저녁·야간은 경기로 HIGH, 11/21~22 축제 시간대는 HIGH, 11/18부터 계절(SEASON) 태그가 붙습니다.

---

### 4-7. `GET /api/sales` 매출 패턴

| 받는 값 | 예 | 뜻 |
|---|---|---|
| `from`, `to` | `2026-11-02`, `2026-11-15` | 기간 |
| `grain` | `day`(기본), `week`, `month`, `weekday_daypart` | 묶는 단위 |

```json
{
  "is_example": true,
  "grain": "weekday_daypart",
  "rows": [
    {"period": "MON", "daypart": "LUNCH", "days_counted": 2,
     "sales_amount": 588000, "qty": 70, "food_cost": 199900, "labor_cost": 55000, "profit": 333100}
  ]
}
```

| grain | `period` 값 | 계산 |
|---|---|---|
| `day` | `"2026-11-02"` | 하루 × 시간대 그대로 |
| `week` | 그 주 월요일 `"2026-11-02"` | 한 주 합계 |
| `month` | `"2026-11"` | 한 달 합계 |
| `weekday_daypart` | `"MON"` ~ `"SUN"` | 요일 × 시간대 **평균** (요일 패턴용) |

모든 단위에서 시간대(`daypart`) 구분은 유지됩니다. 하루 전체 합이 필요하면 화면에서 세 시간대를 더하면 됩니다. `days_counted`는 그 줄에 합치거나 평균 낸 날 수, `profit`은 매출 − 메뉴 원가 − 인건비입니다.

예시 데이터는 2026-11-02 ~ 11-17이고, 11/17 점심만 평소보다 35% 많게 넣었습니다(매출 이상 알림의 근거).

---

### 4-8. `GET /api/reviews` 리뷰와 분류 결과

| 받는 값 | 예 | 뜻 |
|---|---|---|
| `from`, `to` | `2026-11-16`, `2026-11-22` | 리뷰 작성일 기준 기간 |
| `quick` | `true` / `false` | `true`면 불만 리뷰(빠른 응대)만, `false`면 나머지만. 생략하면 전부 |

```json
{
  "is_example": true,
  "reviews": [
    {
      "review_id": "rv_118",
      "platform": "BAEMIN",
      "written_at": "2026-11-17T12:30:00+09:00",
      "rating": 1,
      "text": "배달이 너무 늦어서 다 식어서 왔어요.",
      "customer_key": null,
      "order_id": null,
      "label": {
        "sentiment": "NEGATIVE",
        "complaint_types": ["DELIVERY_DELAY"],
        "complaint_groups": ["DELIVERY"],
        "is_quick": true,
        "labeler": "HCX",
        "labeled_at": "2026-11-17T13:50:00+09:00"
      }
    }
  ]
}
```

카드에서 **근거 리뷰를 펼쳐 볼 때** 씁니다. 할 일의 `basis.ref_id`(예: `rv_118`)와 같은 `review_id`를 찾으면 됩니다. `customer_key`는 손님 가명이고 이름이나 전화번호는 다루지 않습니다. `label`이 `null`이면 아직 분류 전입니다.

---

### 4-9. `GET /api/settings`, `PATCH /api/settings` 매장 설정

**보기**: `GET /api/settings`

```json
{
  "is_example": true,
  "settings": {
    "store_id": "store_001",
    "name": "춘천 대학가 국수집 (가상 매장)",
    "open_time": "10:00",
    "close_time": "22:00",
    "dayparts": {
      "LUNCH": {"start": "11:00", "end": "13:30"},
      "DINNER": {"start": "17:00", "end": "21:00"},
      "NIGHT": {"start": "21:00", "end": "22:00"}
    },
    "busy_dayparts": ["LUNCH", "DINNER"],
    "slots": {"OPENING": "10:00", "AFTERNOON": "14:00", "CLOSING": "21:30"},
    "closed_weekdays": []
  }
}
```
(`category`, `lat`, `lng` 생략)

**고치기**: `PATCH /api/settings`. 바꿀 항목만 보내면 됩니다. 고칠 수 있는 것은 `slots`(알림 시각 3개), `dayparts`(시간대), `busy_dayparts`(바쁜 시간대) 세 가지입니다.

```json
{"slots": {"OPENING": "10:00", "AFTERNOON": "15:00", "CLOSING": "21:30"}}
```

검사 규칙:
- 시각은 `"HH:MM"` 형식 (`"9:00"`은 오류, `"09:00"`은 가능)
- 알림 시각은 출근 후 < 오후 < 마감 전 순서
- 알림 시각은 영업시간 안, 바쁜 시간대 밖
- 시간대는 시작 < 끝

> ⚠️ 지금은 **서버 메모리에만 저장**됩니다. 서버를 다시 켜면 예시 값으로 돌아가고, 바꿔도 계획이 다시 계산되지 않습니다. DB와 계획 엔진을 연결할 때 함께 처리합니다.

---

## 5. 계획 엔진

`server/app/planner/`는 **"분석 결과를 받아서 언제 사장님께 무엇을 알릴지 계산하는"** 순수 파이썬 코드입니다. AI가 아니라 날짜·시간 규칙으로 계산합니다.

### 5-1. 쓰는 법

```python
import datetime as dt
from app.planner.data_shapes import PlanInputs
from app.planner.make_plan import make_plan

inputs = PlanInputs.model_validate(입력_dict)   # 매장 설정, 리뷰, 손님 주기, 달력 등
now = dt.datetime.fromisoformat("2026-11-17T14:00:00+09:00")
result = make_plan(inputs, now)

result.plan_items    # 할 일 목록 (/api/plan 의 plan_items 와 같은 모양)
result.notice_items  # 승인 없는 알림 (/api/plan 의 notice_items 와 같은 모양)
result.batches       # 알림 시각별 묶음 (/api/today 의 batches 와 같은 모양)
```

`now`에는 "지금"을 넣습니다. **`now` 이전에 생긴 데이터만** 씁니다(리뷰, 위험 신호, 매출 이상, 계산된 달력과 손님 주기). 행사·경기 일정은 앞날 것도 씁니다. API에서는 실제 현재 시각을, 테스트에서는 원하는 시각을 넣습니다.

### 5-2. 입력 (`PlanInputs`)

| 항목 | 내용 | 나중에 누가 만드나 |
|---|---|---|
| `store` | 매장 설정 (알림 시각, 시간대, 영업시간) | 지호 |
| `reviews` | 리뷰와 분류 결과 | 지호 + 태성 |
| `customer_cycles` | 손님 주문 주기 (`WEEKLY`, `MONTHLY`, `NONE`) | 태성 |
| `calendar` | 달력 칸 (수요 신호, 이유 태그) | 태성 |
| `risk_signals` | 같은 불만 7일 안에 3건 | 태성 |
| `sales_anomalies` | 달력으로 설명되지 않는 매출 이상 | 지호(분석 줄) |
| `events`, `games` | 행사, 경기 일정 | 지호 |

모든 필드 정의는 `planner/data_shapes.py`에 있습니다.

### 5-3. 규칙

알림 가능 시각은 **10:00 출근 후, 14:00 오후, 21:30 마감 전** 세 번입니다(매장 설정에서 바꿀 수 있음).

| 할 일 | 언제 만드나 | 승인 요청 | 실행 | 기한 | 파일 |
|---|---|---|---|---|---|
| ① 불만 리뷰 답글 | 불만 리뷰가 들어오면 | 리뷰 뒤 첫 알림 시각 | 승인과 동시 | 그날 마감 | `rule_review_reply.py` |
| ① 그 밖의 리뷰 답글 (매주 단골, 매달 단골, 일반) | 불만이 아닌 리뷰가 들어오면 | 리뷰가 달린 주의 **토요일 10:00** (답글과 함께) | 승인되면 **토요일 11:00** 자동 게시 | 토요일 11:00 | `rule_review_reply.py` |
| 매달 단골 재주문 권유 | 매달 단골이 불만이 아닌 리뷰를 남기면 | 답글 토요일 **4주 뒤 토요일 10:00** | 같은 날 11:00 발송 | 11:00 | `rule_reorder_nudge.py` |
| ② 메뉴판 바꾸기 | 날짜의 이유 태그 묶음이 전날과 다르면 (행사 끝나는 날 포함) | 전날 14:00 | 당일 10:00 | 당일 마감 | `rule_menu_order.py` |
| ③ 포스터 | 수요 신호 HIGH를 만든 행사·경기 / 행사 없는 주말 | 3일 전 14:00 | 2일 전 10:00 | 행사 시작 (주말 포스터는 토요일 개점) | `rule_poster.py` |
| ④ 반복 불만 개선 | 위험 신호가 열리면 | 발견 뒤 첫 14:00 (같은 시각 포함) | 없음 | 없음 (2차) | `rule_complaint_fix.py` |
| 월요일 주간 예고 | 매주 월요일 | 월요일 10:00 (승인 없음) | | | `info_alerts.py` |
| 매출 이상 알림 | 달력에 없는 매출 이상 | 다음 날 10:00 (승인 없음) | | | `info_alerts.py` |

**리뷰 답글 세부 규칙**
- 판단 순서: 불만 → 매주 단골 → 매달 단골 → 일반
- 토요일 10:00 승인 요청이 이미 지난 뒤(토요일 10시 이후, 일요일)에 달린 리뷰는 **다음 주 토요일**로 넘깁니다.
- 분류 결과(`label`)가 없는 리뷰는 건너뜁니다.

**그 밖의 공통 규칙**
- 계산한 승인 요청 시각이 근거를 알게 된 시각보다 이르면(이미 지났으면) 다음 알림 시각으로 미룹니다.
- 과거 매출 효과가 없어 달력 태그가 붙지 않은 행사·경기(예: 11/18 야구)는 아무 알림도 만들지 않습니다.

### 5-4. 우선순위와 묶기 (`priority_and_grouping.py`)

| 우선순위 | 대상 |
|---|---|
| 1 | 불만 리뷰 답글 |
| 2 | 반복 불만 개선 |
| 3 | 다음 날 실행할 일의 승인 요청 |
| 4 | 그 밖 (오늘 실행 알림, 주간 예고, 매출 이상, 토요일 답글·재주문 권유 승인 요청) |

- 같은 우선순위 안에서는 **기한이 빠른 것이 앞**입니다. 기한이 없으면 맨 뒤로 갑니다.
- **실행 알림**은 실행 시각이 따로 있고 그게 알림 가능 시각일 때만 보냅니다. 불만 리뷰 답글(승인과 동시 실행)과 토요일 11:00 자동 게시는 실행 알림이 없습니다.
- 항목이 없는 알림 시각에는 묶음을 만들지 않습니다.

### 5-5. 데모 주간 결과 (정답)

`tests/planner/test_demo_week.py`가 확인하는 결과입니다. 괄호 안은 우선순위입니다.

| 날짜 | 10:00 출근 후 | 14:00 오후 | 21:30 마감 전 |
|---|---|---|---|
| 월 11/16 | 주간 예고 (4) | 승인: 경기 포스터 (3) | |
| 화 11/17 | 실행: 경기 포스터 (4) | 승인: 배달 지연 리뷰 답글 (1), 배달 지연 개선 (2), 메뉴판 계절 전환 (3) | |
| 수 11/18 | 실행: 메뉴판 계절 전환 (4) / 알림: 어제 점심 매출 +35% (4) | 승인: 메뉴판 경기 (3), 축제 포스터 (3) | |
| 목 11/19 | 실행: 메뉴판 경기 (4), 축제 포스터 (4) | 승인: 메뉴판 경기 끝 (3) | |
| 금 11/20 | 실행: 메뉴판 경기 끝 (4) | 승인: 메뉴판 축제 (3) | 승인: 맛 불만 리뷰 답글 (1) |
| 토 11/21 | 승인: c_m01 재주문 권유 (4), 리뷰 답글 4건 (4) → 11:00 게시 / 실행: 메뉴판 축제 (4) | | |
| 일 11/22 | | 승인: 메뉴판 축제 끝 (3) | |

공통 문서의 원래 정답표와 다른 점:
- 매주 단골 c_w01(11/11 리뷰)의 답글은 11/14 토요일로 옮겨져 이번 주에 없습니다.
- 매달 단골 c_m01의 답글은 10/24 토요일에 이미 처리됐고, 대신 11/21에 재주문 권유가 생겼습니다.
- 일반 리뷰 4건은 금요일 승인이 아니라 토요일 10:00 승인, 11:00 게시입니다.
- 11/18 14:00은 기한 순서 규칙에 따라 메뉴판(기한 11/19)이 축제 포스터(기한 11/21)보다 앞입니다.

---

## 6. 예시 데이터

### 6-1. 두 종류의 예시 데이터

| | `contracts/sample_responses/` | `server/tests/planner/sample_inputs/` |
|---|---|---|
| 무엇 | API **응답** 예시 (계획 엔진의 출력 쪽) | 계획 엔진 **입력** 예시 |
| 누가 씀 | API가 돌려줌, 프론트가 화면 만들 때 참고 | 계획 엔진 테스트 |
| 비유 | 완성된 요리 사진 | 요리 재료 |

### 6-2. 예시 데이터 표시

JSON은 주석을 쓸 수 없어서 두 가지로 표시합니다.
- 파일 이름에 `.example`을 붙입니다.
- 파일 맨 위에 `"_설명"` 항목을 둡니다. `_`로 시작하는 항목은 서버가 응답에서 빼고 보냅니다.

리뷰 문구, id(`rv_118`, `game_031` 등), 매출 숫자, 위도·경도는 **지어낸 값**입니다. 데모 주간 사건(경기, 축제, 불만 리뷰 시각 등)은 공통 문서(지호 D4)를 따랐습니다.

### 6-3. 예시를 고칠 때

- 응답 예시 JSON은 **요청마다 새로 읽습니다.** 파일을 고치고 저장하면 서버를 다시 켜지 않아도 바로 반영됩니다.
- 모양이 틀리면(필드 누락, 코드값 오타 등) API가 500 오류를 냅니다. 서버 터미널에 어느 칸이 틀렸는지 찍힙니다.
- `today`와 `plan` 예시는 테스트 입력을 계획 엔진에 넣어 계산한 결과입니다. 계산에 쓴 일회용 스크립트는 저장소에 없습니다. 입력을 바꿨다면 응답 예시도 손으로 맞춰야 합니다.

---

## 7. 테스트

```bash
python -m pytest -v
```
> `server/` 폴더에서 실행합니다. `tests/` 아래 `test_`로 시작하는 파일을 모두 찾아 실행합니다.

| 파일 | 확인하는 것 | 예 |
|---|---|---|
| `test_notification_time_helpers.py` | 알림 시각 도우미 | 12:30 다음 알림은 14:00, 21:40 다음은 다음 날 10:00, 일요일은 그 주 토요일로 계산 |
| `test_rules.py` | 할 일 종류별 규칙 | 경기 3일 전 14:00 포스터 승인, 토요일 19시 리뷰는 다음 주 토요일, 야구는 포스터 없음 |
| `test_demo_week.py` | 데모 주간 전체 | [5-5 정답표](#5-5-데모-주간-결과-정답)와 알림 시각, 순서, 종류, 우선순위가 모두 같은지 |

테스트가 실패하면 어느 값이 기대와 달랐는지 출력됩니다. **규칙을 고치면 테스트도 같이 고쳐야 합니다.**

---

## 8. 자주 하는 작업

### 8-1. 화면이 응답에 새 필드를 원할 때
1. 그 모듈의 `response_format.py`에 필드를 추가합니다. 할 일, 달력, 리뷰처럼 계획 엔진과 같이 쓰는 모양은 `planner/data_shapes.py`에 추가합니다.
2. `contracts/sample_responses/`의 예시 JSON에 값을 넣습니다.
3. `/docs`에서 바뀐 모양을 확인하고 프론트 담당에게 알립니다.

### 8-2. 규칙을 바꿀 때 (예: 리뷰 답글 게시 시각을 11:00 → 10:30)
1. 해당 `rule_*.py` 파일 맨 위의 상수를 고칩니다. 예) `rule_review_reply.py`의 `SATURDAY_SEND_TIME = "11:00"`
2. 테스트의 기대값(`test_rules.py`, `test_demo_week.py`)을 같이 고칩니다.
3. `python -m pytest`로 확인합니다.

바꾸기 쉽게 상수로 빼 둔 값:

| 상수 | 파일 | 지금 값 |
|---|---|---|
| `SATURDAY_APPROVAL_SLOT` | `rule_review_reply.py` | `"OPENING"` (토요일 10:00 승인) |
| `SATURDAY_SEND_TIME` | `rule_review_reply.py` | `"11:00"` |
| `NUDGE_AFTER_WEEKS` | `rule_reorder_nudge.py` | `4` |
| `REASON_LINES`, `REASON_LINE` | `rule_review_reply.py`, `rule_reorder_nudge.py` | 카드 이유 문구 |

### 8-3. `today`, `plan` API를 계획 엔진에 연결할 때 (다음 단계)
`data_provider.py`만 바꾸면 됩니다. 응답 모양이 같아서 프론트는 고칠 것이 없습니다.

```python
# modules/today/data_provider.py (연결 후 모습 예시)
def get_today() -> TodayResponse:
    inputs = ...  # DB나 태성의 분석 결과에서 PlanInputs 만들기
    now = now_seoul()
    result = make_plan(inputs, now)
    batches = [b for b in result.batches if b.slot_at.date() == now.date()]
    return TodayResponse(is_example=False, date=now.date(), batches=batches)
```

### 8-4. 새 API를 만들 때
1. `server/app/modules/_template/` 폴더를 복사해서 이름을 바꿉니다. 예) `notifications`
2. `router.py`에 주소를 만들고, 필요하면 `response_format.py`와 `data_provider.py`를 추가합니다.
3. 서버를 다시 켜면 `/api/notifications`가 자동으로 생깁니다.

---

## 9. 임시로 정한 것과 아직 안 된 것

### 임시로 정한 것 (팀과 다시 정할 수 있음)
- 토요일 10:00~11:00 사이에 달린 리뷰는 다음 주 토요일로 넘깁니다. 10:00 승인 알림이 이미 나간 뒤이기 때문입니다.
- 토요일 답글·재주문 권유 승인 요청은 우선순위 4이고, 기한(11:00)이 빨라 10:00 묶음에서 앞에 옵니다.
- 재주문 권유는 매달 단골의 **불만이 아닌** 리뷰에만 만듭니다.
- 불만 리뷰가 정확히 알림 시각(예: 14:00:00)에 들어오면 다음 알림 시각으로 넘깁니다. 그 시각의 계산은 직전에 이미 끝났기 때문입니다.

### 아직 안 된 것
- `today`, `plan` API ↔ 계획 엔진 연결 ([8-3](#8-3-today-plan-api를-계획-엔진에-연결할-때-다음-단계))
- DB 연결, 설정 변경 저장과 재계산
- 시뮬레이터용 API (`/api/notifications` 등). 가상 시각을 쓰지 않기로 해서 방식을 다시 정해야 합니다.
- 프론트와 정할 것: 근거 리뷰 본문을 카드에 넣을지, today 응답에 할 일 내용을 같이 넣을지, 일반 리뷰 여러 건을 서버와 화면 중 어디서 한 장으로 묶을지
- README의 모듈 파일 이름 안내(`schemas.py`, `service.py`)가 지금 구조(`response_format.py`, `data_provider.py`)와 다릅니다.
- 배포할 때는 `contracts/` 폴더도 `server/` 옆에 함께 올려야 합니다(응답 예시를 읽기 때문).

---

## 부록 A. 코드값 목록

정의는 `server/app/planner/data_shapes.py`에 있습니다. 목록에 없는 값이 응답에 섞이면 서버가 오류를 냅니다.

| 이름 | 값 | 뜻 |
|---|---|---|
| `daypart` 시간대 | `LUNCH`, `DINNER`, `NIGHT` | 점심, 저녁, 야간 |
| `slot` 알림 시각 | `OPENING`, `AFTERNOON`, `CLOSING` | 출근 후, 오후, 마감 전 |
| `task_type` 할 일 | `REVISIT_REPLY`, `MENU_ORDER`, `POSTER`, `REVIEW_FIX`, `REORDER_NUDGE` | 리뷰 답글, 메뉴판, 포스터, 반복 불만 개선, 재주문 권유 |
| `revisit_class` 답글 분류 | `QUICK`, `WEEKLY`, `MONTHLY`, `BASIC` | 불만, 매주 단골, 매달 단골, 일반 |
| `notify_kind` 알림 종류 | `APPROVAL_REQUEST`, `EXECUTE_REMINDER`, `PREVIEW`, `NOTICE` | 승인 요청, 실행 알림, 주간 예고, 승인 없는 알림 |
| `notice kind` | `WEEKLY_PREVIEW`, `SALES_ANOMALY` | 월요일 주간 예고, 매출 이상 |
| `priority` | `1`, `2`, `3`, `4` | 불만 리뷰, 반복 불만 개선, 내일 실행, 그 밖 |
| `basis kind` 근거 | `REVIEW`, `CUSTOMER`, `EVENT`, `GAME`, `RISK_SIGNAL`, `CALENDAR_DAY` | 리뷰, 손님, 행사, 경기, 위험 신호, 달력 날짜 |
| `signal` 수요 신호 | `HIGH`, `NORMAL`, `LOW` | 많음, 보통, 적음 |
| `reason tag` 이유 | `EVENT`, `GAME`, `WEATHER`, `SEASON` | 행사, 경기, 날씨(비·폭염·한파), 계절 |
| `cycle` 주문 주기 | `WEEKLY`, `MONTHLY`, `NONE` | 매주, 매달, 주기 없음 |
| `platform` | `NAVER`, `BAEMIN`, `YOGIYO`, `COUPANG` | 리뷰 플랫폼 |
| `sentiment` | `POSITIVE`, `NEGATIVE`, `MIXED` | 긍정, 부정, 섞임 |
| `complaint_type` 불만 유형 | `TASTE`, `PORTION`, `HYGIENE`, `PHOTO_MISMATCH`, `DELIVERY_DELAY`, `SERVICE` | 맛, 양, 위생, 사진과 다름, 배달 지연, 응대 |
| `complaint_group` 불만 묶음 | `FOOD`, `DELIVERY`, `SERVICE` | 음식, 배달, 응대 |
| `labeler` 분류 주체 | `HCX`, `RULE` | HyperCLOVA X, 키워드 규칙 |
| `weekday` 요일 | `MON` ~ `SUN` | 월 ~ 일 |
