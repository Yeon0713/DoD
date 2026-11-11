# DoD (Deliver Or Die)

NAVER Cloud Hyper-Local AI 챌린지 팀 DoD의 저장소입니다.
소상공인 가게 사장님을 위한 앱(주문, 매출 분석, 리뷰 응대, 마케팅, 일정 관리 등)을 만듭니다.

- 커밋 · 브랜치 · PR 규칙: [commit_guide.md](commit_guide.md)
- 화면용 API와 계획 엔진 자세한 사용법: [docs/server-api-and-planner-guide.md](docs/server-api-and-planner-guide.md)

---

## 1. 폴더 구조

```
DoD/
├── README.md                지금 보고 있는 문서
├── commit_guide.md          커밋 · 브랜치 · PR 규칙
├── .gitignore               GitHub에 올리면 안 되는 파일 목록 (.env, 가상환경 등)
├── contracts/
│   └── sample_responses/    화면용 API가 지금 돌려주는 응답 예시 JSON (5장)
├── docs/                    자세한 사용 안내 문서
└── server/                  백엔드 서버 (FastAPI)
    ├── requirements.txt     서버에 필요한 파이썬 패키지 목록
    ├── .env.example         설정 파일(.env)의 틀. 값은 비워서 공유
    ├── app/
    │   ├── main.py          서버 시작점. modules/ 안의 기능을 자동으로 연결, 오류 응답 형식 등록
    │   ├── core/            모든 모듈이 같이 쓰는 코드
    │   │   ├── config.py    .env에서 설정 값 읽기
    │   │   ├── ncloud.py    네이버 클라우드 API 호출 (서명 자동 처리)
    │   │   ├── clova.py     HyperCLOVA X 호출 (리뷰 답변, 마케팅 문구, 챗봇 대화 등)
    │   │   ├── maps.py      Maps 호출 (주소 ↔ 좌표, 길찾기)
    │   │   ├── api_hub.py   NAVER API HUB 호출 (지역·블로그 검색, 검색어 트렌드)
    │   │   ├── sens.py      SENS 문자 보내기 (예약 알림 등)
    │   │   ├── seoul_time.py              서울 시각 도구
    │   │   ├── error_response.py          오류 응답 형식 통일
    │   │   └── sample_response_loader.py  응답 예시 JSON 읽기
    │   ├── modules/         기능 모듈을 넣는 곳 ← 기능 개발은 여기서
    │   │   ├── __init__.py  modules/ 안의 폴더를 찾아서 서버에 등록하는 코드 (수정 X)
    │   │   ├── _template/   새 기능을 만들 때 복사할 틀 (서버에 등록되지 않음)
    │   │   └── today/ plan/ calendar/ sales/ reviews/ settings/   화면용 API (5장)
    │   └── planner/         계획 엔진: 언제 사장님께 무엇을 알릴지 계산 (5장)
    ├── db/                  DB 스키마, 마이그레이션, 목업 데이터 (4장)
    └── tests/               테스트 (server/ 에서 python -m pytest)
```

---

## 2. 서버 실행하기

모든 명령어는 **터미널**(Windows: Git Bash, Mac: 터미널 앱)에 입력합니다.
Python 3.10 이상이 필요합니다. (`python --version`으로 확인)

### 2-1. 처음 한 번만

**서버 폴더로 이동**

```bash
cd server
```

**가상환경 만들기**

이 프로젝트 전용 파이썬 환경을 만듭니다. 다른 프로젝트의 패키지와 섞이지 않게 해 줘요.

```bash
python -m venv .venv
```

> Mac에서는 `python` 대신 `python3`을 쓰세요.

**가상환경 켜기**

```bash
source .venv/Scripts/activate
```

> Mac에서는 `source .venv/bin/activate`

터미널 줄 앞에 `(.venv)`가 붙으면 켜진 거예요.

**패키지 설치**

```bash
pip install -r requirements.txt
```

**설정 파일 만들기**

```bash
cp .env.example .env
```

`.env`에는 나중에 API 키 같은 비밀 값을 넣습니다. `.gitignore`에 등록돼 있어서 GitHub에 올라가지 않아요.
새 설정 값이 생기면 `.env.example`에도 **이름만** 추가해서 팀원들과 공유하세요. (값은 비워 두기)

### 2-2. 서버 켤 때마다

터미널을 새로 열었다면 `server/` 폴더로 이동한 뒤 가상환경부터 켭니다.

```bash
source .venv/Scripts/activate
```

```bash
uvicorn app.main:app --reload
```

- `app.main:app`은 "`app/main.py` 안의 `app`을 실행하라"는 뜻이에요.
- `--reload`를 붙이면 코드를 저장할 때마다 서버가 자동으로 다시 켜집니다.
- 끌 때는 `Ctrl + C`

### 2-3. 잘 켜졌는지 확인

서버가 켜진 상태에서 브라우저로 들어가 보세요.

| 주소 | 결과 |
|---|---|
| http://localhost:8000/health | `{"status":"ok"}`가 나오면 정상 |
| http://localhost:8000/docs | API 목록 화면 (FastAPI가 자동으로 만들어 줌). 여기서 API를 직접 눌러 테스트할 수 있어요 |

---

## 3. 새 기능(모듈) 만들기: 어디서 작업하나요?

**기능은 전부 `server/app/modules/` 안에 폴더 하나씩 만들어서 작업합니다.**
폴더를 만들면 서버가 켜질 때 자동으로 `/api/<폴더이름>` 주소에 연결돼요. `main.py`는 고치지 않습니다.

각자 자기 기능 폴더 안에서만 작업하면 다른 팀원과 같은 파일을 고칠 일이 거의 없어서 충돌이 적어요.

### 예시: 리뷰 응대 기능 만들기

**① `_template` 폴더를 복사해서 이름을 바꾸기**

```bash
cp -r app/modules/_template app/modules/review
```

(`server/` 폴더에서 실행. VS Code에서 폴더를 복사 · 붙여넣기 한 뒤 이름을 바꿔도 됩니다.)

**② `app/modules/review/router.py`에 API 작성하기**

```python
from fastapi import APIRouter

router = APIRouter()


@router.post("/reply")
def make_reply():
    ...
```

**③ 서버를 다시 켜면 자동 연결**

위 코드는 `POST /api/review/reply` 주소가 됩니다. http://localhost:8000/docs 에서 바로 확인할 수 있어요.

### 모듈 이름 추천

`commit_guide.md`의 범위(scope)와 맞추면 커밋 기록과 폴더가 한눈에 연결됩니다.

| 기능 | 폴더 | API 주소 |
|---|---|---|
| 상권 · 매출 분석 | `modules/analysis/` | `/api/analysis/...` |
| 마케팅 콘텐츠 생성 | `modules/marketing/` | `/api/marketing/...` |
| 리뷰 응대 | `modules/review/` | `/api/review/...` |
| 전화 응대 | `modules/call/` | `/api/call/...` |

### 모듈 안에서 파일 나누기 (추천)

꼭 지켜야 하는 건 **`router.py` 안에 `router`가 있어야 한다**는 것 하나뿐입니다.
코드가 길어지면 아래처럼 나누는 걸 추천해요.

```
modules/review/
├── __init__.py      비워 둠 (필수)
├── router.py        API 주소 정의. 요청을 받아 service로 넘김 (필수)
├── service.py       실제 동작. HyperCLOVA X 호출(app/core/clova.py 사용), 데이터 처리 등
├── schemas.py       요청 · 응답 데이터 모양 (Pydantic 모델)
└── prompts/         HyperCLOVA X 프롬프트 파일
```

> 화면용 API 모듈(`today`, `plan` 등)은 같은 역할을 `response_format.py`(응답 모양)와 `data_provider.py`(데이터 가져오기)라는 이름으로 나눠 두었습니다. 파일 이름이 달라도 동작 방식은 같습니다.

- 프롬프트를 바꿀 때는 커밋 타입 `prompt`를 씁니다. 예) `prompt(review): 답글 말투를 더 공손하게 변경`
- 이름이 `_`로 시작하는 폴더는 서버에 등록되지 않습니다. 만들다 만 기능은 `_review`처럼 이름을 붙여 두면 서버에 안 붙어요.

### 주의

- **API 키는 코드에 직접 쓰지 말고 `.env`에 넣습니다.** 읽어 오려면 `app/core/config.py`의 `Settings`에 항목을 추가하세요.
- 새 패키지를 설치했다면 `requirements.txt`에도 추가하세요. 커밋 타입은 `chore`입니다.

---

## 4. DB (SQLite + 목업 데이터)

개발 DB는 **SQLite 파일**이고 git에 같이 올라갑니다. `git pull`만 하면 DB까지 받고, 서버가 DB에 처음 접속할 때 파일을 엽니다. 따로 설치하거나 켤 것은 없습니다.

```
server/db/data/common.db   공통 테이블 (events, games, weather_daily)
server/db/data/s001.db     s001 한림국수 전용 테이블
server/db/data/s002.db     s002 두리맥주 전용 테이블
server/db/data/s003.db     s003 석사돈가스 전용 테이블
```

매장 파일은 매장 이름으로 붙어서 `s001.orders`처럼 씁니다. `db/mock/out/` 아래 CSV는 같은 내용의 사본입니다 (`out/s001/orders.csv`, `out/common/weather_daily.csv` …).

### 목업 다시 만들기 (`server/` 폴더)

```bash
python -m db.mock.generate     # db/data/*.db 를 새로 만들고 CSV도 갱신 (같은 시드 = 같은 데이터)
```

DB 파일은 바이너리라 git이 합칠 수 없습니다. 두 사람이 동시에 고쳐 올리지 않도록, 목업을 다시 만들 사람을 정해 두세요.

### 테이블 (C1 원본)

| 테이블 | 한 줄 = | 주요 열 |
|---|---|---|
| store | 매장 | 영업시간, 휴무 요일·`slots`(JSON) |
| menu | 메뉴 | name, category(`main`/`side`/`drink`), price |
| orders | 주문 | `ordered_at`, channel(`hall`/`delivery`), `customer_key`, total_amount |
| order_items | 주문 속 메뉴 | order_id, menu_id, quantity, unit_price |
| reviews | 리뷰 | `written_at`, rating, content, order_id·`customer_key`(이어진 리뷰만), complaint_type(LLM이 채움) |
| staff / shifts | 알바 / 근무 | starts_at, ends_at |
| events | 행사 | kind, starts_at, ends_at, distance_km |
| games | 경기 | sport, level(`national`/`pro`), starts_at |
| weather_daily | 하루 날씨 | temp_max, temp_min, precip_mm |

- 매장 테이블(store ~ staff / shifts)은 매장 파일마다 하나씩 있고, id는 매장마다 1부터 매깁니다. 행사·경기·날씨는 `common.db`에 하나만 있습니다.
- 코드에서는 `db.session.store_engine("s001")`로 연결하면 `models.Order` 등이 그 매장 테이블을 가리킵니다.
- 시각은 서울 시간으로 저장되고, 읽으면 서울 시간대가 붙은 `datetime`이 나옵니다.
- 열 전체는 `db/models.py`에 있습니다.

**배포 때 PostgreSQL로 옮길 수 있게** 지금부터 지킬 것:
- 쿼리는 SQLAlchemy 문법으로 씁니다. `::date`, `AT TIME ZONE` 같은 DB 전용 SQL 문자열은 쓰지 않습니다.
- 열 타입은 `db/models.py`에 있는 공통 타입(`JSON`, 서울 시각 `TZ` 등)만 씁니다.
- 옮길 때는 `db/session.py`의 접속을 PostgreSQL로 바꾸고, 매장마다 스키마(`s001` …)를 만든 뒤 생성기로 다시 넣으면 됩니다.

---

## 5. 화면용 API와 계획 엔진

사장님 화면(오늘의 카드, 이번 주 달력, 설정)에 데이터를 주는 API 6개와, **언제 사장님께 무엇을 알릴지 계산하는 계획 엔진**입니다.
자세한 응답 필드, 규칙, 고치는 법은 [docs/server-api-and-planner-guide.md](docs/server-api-and-planner-guide.md)에 있습니다.

> ⚠️ 지금 API는 **예시 데이터**(`contracts/sample_responses/`)를 돌려줍니다. 모든 응답에 `"is_example": true`가 붙습니다.
> DB와 분석 결과가 준비되면 실제 데이터로 바꾸고, 그때 `false`가 됩니다. 응답 모양은 그대로라 화면 코드는 고칠 필요가 없습니다.
> 예시 데이터 단계에서는 DB와 `.env` 없이도 서버가 켜집니다.

### 5-1. API 목록

서버를 켜고 http://localhost:8000/docs 에 들어가면 아래 API를 직접 호출해 볼 수 있습니다.

| 주소 | 쓰는 화면 | 받는 값 | 돌려주는 것 |
|---|---|---|---|
| `GET /api/today` | 오늘의 카드 | 없음 | 오늘 알림 시각(10:00, 14:00, 21:30)별 카드 묶음. 우선순위 순서로 정렬됨 |
| `GET /api/plan` | 오늘의 카드 | `from`, `to` | 할 일 목록(이유 한 줄, 승인 요청·실행 시각)과 승인 없는 알림(주간 예고, 매출 이상) |
| `GET /api/calendar` | 이번 주 달력 | `from`, `to` | 날짜 × 시간대(점심, 저녁, 야간)별 수요 신호와 이유 |
| `GET /api/sales` | 이번 주 달력 | `from`, `to`, `grain` | 매출 패턴. `grain`: `day`, `week`, `month`, `weekday_daypart` |
| `GET /api/reviews` | 카드의 근거 리뷰 | `from`, `to`, `quick` | 리뷰와 분류 결과. `quick=true`면 불만 리뷰만 |
| `GET /api/settings` | 설정 | 없음 | 매장 설정 (알림 시각, 장사 시간대) |
| `PATCH /api/settings` | 설정 | 바꿀 항목 | 알림 시각, 시간대 고치기. 지금은 서버 메모리에만 저장 |

예) `http://localhost:8000/api/plan?from=2026-11-16&to=2026-11-22`

**today와 plan의 관계**: today의 카드 묶음에는 `plan_id`(또는 `notice_id`)만 있습니다. 카드에 보일 내용은 plan에서 같은 id를 찾아서 씁니다.

### 5-2. 공통 규칙

- 시각은 서울 기준, `"2026-11-17T14:00:00+09:00"` 형식입니다. 날짜는 `"2026-11-17"`입니다.
- 코드값은 영어 대문자(`LUNCH`, `APPROVAL_REQUEST` 등)로 주고받고, 화면 문구는 프론트가 한국어로 바꿉니다.
- 오류는 항상 같은 모양입니다.
  ```json
  {"error": {"code": "INVALID_DATE_RANGE", "message": "from 날짜가 to 날짜보다 늦습니다."}}
  ```
- 화면 주소가 `http://localhost:3000`이 아니면 `.env`의 `CORS_ORIGINS`에 추가해야 브라우저에서 호출됩니다.

### 5-3. 계획 엔진 (`server/app/planner/`)

분석 결과(리뷰 분류, 손님 주문 주기, 달력, 위험 신호)를 받아 **할 일마다 승인 요청 시각, 실행 시각, 우선순위**를 정하고 알림 시각별로 묶습니다. AI가 아니라 날짜·시간 규칙으로 계산합니다.

| 할 일 | 승인 요청 | 실행 |
|---|---|---|
| 불만 리뷰 답글 | 리뷰 뒤 첫 알림 시각 | 승인과 동시 |
| 그 밖의 리뷰 답글 (단골, 일반) | 리뷰가 달린 주의 토요일 10:00 | 승인되면 토요일 11:00 게시 |
| 매달 단골 재주문 권유 | 답글 토요일 4주 뒤 토요일 10:00 | 같은 날 11:00 |
| 메뉴판 바꾸기 | 바뀌는 날 전날 14:00 | 당일 10:00 |
| 행사·경기 포스터 | 3일 전 14:00 | 2일 전 10:00 |
| 반복 불만 개선 | 발견 뒤 첫 14:00 | 없음 |

우선순위는 1 불만 리뷰, 2 반복 불만 개선, 3 내일 실행할 일, 4 그 밖입니다.

```python
from app.planner.make_plan import make_plan

result = make_plan(inputs, now)   # inputs: PlanInputs, now: 기준 시각
result.batches                    # /api/today 의 batches 와 같은 모양
```

규칙마다 파일이 나뉘어 있습니다(`rule_review_reply.py`, `rule_poster.py` 등). 규칙을 바꾸면 테스트도 같이 고쳐야 합니다.

### 5-4. 테스트

```bash
python -m pytest -v
```

`server/` 폴더에서 실행합니다. 데모 주간(2026-11-16 ~ 11-22)을 계획 엔진에 넣었을 때 알림 타임라인이 정답과 같은지 확인합니다.
