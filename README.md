# DoD (Deliver Or Die)

NAVER Cloud Hyper-Local AI 챌린지 팀 DoD의 저장소입니다.
소상공인 가게 사장님을 위한 앱(주문, 매출 분석, 리뷰 응대, 마케팅, 일정 관리 등)을 만듭니다.

- 커밋 · 브랜치 · PR 규칙: [commit_guide.md](commit_guide.md)

---

## 1. 폴더 구조

```
DoD/
├── README.md                지금 보고 있는 문서
├── commit_guide.md          커밋 · 브랜치 · PR 규칙
├── .gitignore               GitHub에 올리면 안 되는 파일 목록 (.env, 가상환경 등)
└── server/                  백엔드 서버 (FastAPI)
    ├── requirements.txt     서버에 필요한 파이썬 패키지 목록
    ├── .env.example         설정 파일(.env)의 틀. 값은 비워서 공유
    └── app/
        ├── main.py          서버 시작점. modules/ 안의 기능을 자동으로 연결
        ├── core/            모든 모듈이 같이 쓰는 코드
        │   ├── config.py    .env에서 설정 값 읽기
        │   ├── ncloud.py    네이버 클라우드 API 호출 (서명 자동 처리)
        │   ├── clova.py     HyperCLOVA X 호출 (리뷰 답변, 마케팅 문구, 챗봇 대화 등)
        │   ├── maps.py      Maps 호출 (주소 ↔ 좌표, 길찾기)
        │   ├── api_hub.py   NAVER API HUB 호출 (지역·블로그 검색, 검색어 트렌드)
        │   └── sens.py      SENS 문자 보내기 (예약 알림 등)
        └── modules/         기능 모듈을 넣는 곳 ← 기능 개발은 여기서
            ├── __init__.py  modules/ 안의 폴더를 찾아서 서버에 등록하는 코드 (수정 X)
            └── _template/   새 기능을 만들 때 복사할 틀 (서버에 등록되지 않음)
                └── router.py
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

- 프롬프트를 바꿀 때는 커밋 타입 `prompt`를 씁니다. 예) `prompt(review): 답글 말투를 더 공손하게 변경`
- 이름이 `_`로 시작하는 폴더는 서버에 등록되지 않습니다. 만들다 만 기능은 `_review`처럼 이름을 붙여 두면 서버에 안 붙어요.

### 주의

- **API 키는 코드에 직접 쓰지 말고 `.env`에 넣습니다.** 읽어 오려면 `app/core/config.py`의 `Settings`에 항목을 추가하세요.
- 새 패키지를 설치했다면 `requirements.txt`에도 추가하세요. 커밋 타입은 `chore`입니다.

---

## 4. DB (PostgreSQL + 목업 데이터)

DB는 PostgreSQL(Docker)이고, 목업 데이터는 `db/mock/generate.py`가 만들어 DB에 넣습니다. `db/mock/out/*.csv`는 DB 없이 볼 수 있게 남겨 둔 같은 내용의 사본입니다.

### 실행 (`server/` 폴더, Docker Desktop 켠 상태)

```bash
docker compose up -d           # PostgreSQL 켜기
alembic upgrade head           # 테이블 만들기
python -m db.mock.generate     # 목업 생성 → DB에 넣고 CSV도 갱신 (같은 시드 = 같은 데이터)
```

`.env`의 `DATABASE_URL`은 `.env.example` 값 그대로 쓰면 됩니다.

### 테이블 (C1 원본)

| 테이블 | 한 줄 = | 주요 열 |
|---|---|---|
| store | 매장 | 영업시간, `dayparts`·`busy_dayparts`·`slots`(JSON) |
| menu | 메뉴 | name, category(`main`/`side`/`drink`), price |
| orders | 주문 | `ordered_at`, channel(`hall`/`delivery`), `customer_key`, total_amount |
| order_items | 주문 속 메뉴 | order_id, menu_id, quantity, unit_price |
| reviews | 리뷰 | `written_at`, rating, content, order_id·`customer_key`(이어진 리뷰만), complaint_type(LLM이 채움) |
| staff / shifts | 알바 / 근무 | starts_at, ends_at |
| events | 행사 | kind, starts_at, ends_at, distance_km |
| games | 경기 | sport, level(`national`/`pro`), starts_at |
| weather_daily | 하루 날씨 | temp_max, temp_min, precip_mm |

- 시각은 모두 `timestamptz`입니다. 서울 기준 날짜로 묶으려면 `(ordered_at AT TIME ZONE 'Asia/Seoul')::date`
- 열 전체는 `db/models.py`에 있습니다.
