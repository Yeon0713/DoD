# 테스트 네이버 계정 (dona_demo)

임시 네이버 로그인 화면(진짜 네이버 키가 없을 때)에서 쓰는 테스트 계정입니다.

- 2026-11-13: 계정마다 시험할 장면을 정해 두고(dona_test1~3), 조건을 DB 표 하나로 관리하게 했습니다.
- **2026-11-15: 시나리오별 계정 셋을 지우고 데모 계정 하나(`dona_demo`)만 둡니다.**
  - 지운 것은 계정뿐입니다. 가게 데이터(`server/db/data`의 s004 피플스클럽·s005 초옹장·s101 등, 등록 기록, 불러온 리뷰)는 그대로입니다.
  - 장면 시각(`scene_at`), 정해 둔 가게(`store_id`) 같은 조건 칸은 남겨 두었습니다. 다시 시나리오 계정이 필요하면 DB에 줄을 더 넣으면 됩니다.

## 1. 데모 계정

| 계정 (비밀번호 `dona1234`) | 처음 로그인 | 그다음 로그인 | 로그아웃 | 탈퇴하기 |
|---|---|---|---|---|
| **dona_demo** | 등록한 가게가 없어서 **가게 찾기 · 등록 → 사장님 확인(심사) → 처음 설정** (가입) | 이 계정으로 등록한 가게로 바로. 처음 설정·끝낸 카드·고쳐 쓴 답글도 되살림 | 이 기기 기록을 계정 몫으로 보관 (`keep`) | **계정과 가게 연결만 끊음** → 같은 아이디로 다시 로그인하면 가입부터. 계정을 새로 만들 필요 없음 |

- 프로필(이름 김도나, 닉네임 도나데모 등)은 시험용으로 지은 값입니다.
- 사장님 확인은 "시험용 값 넣기"를 누르면 통과합니다. 초옹장은 `120-81-03450` · 김도나 · 2021.04.01, 피플스클럽은 `412-87-05567` · 김도나 · 2019.09.02 ([owner-check.md](owner-check.md)).
- 초옹장(네이버 플레이스 `2004174048`)을 고르면 목업 가게 **s005**로 이어집니다. 1년치 주문·리뷰를 그대로 씁니다.
- 탈퇴해도 가게 데이터(가게 파일, 리뷰)는 지우지 않습니다. 다시 가입해서 같은 가게를 고르면 같은 가게(s005)로 이어집니다. 리뷰 불러오기 기록은 비우므로 리뷰 불러오기를 처음부터 다시 합니다 (목업 가게로 이은 초옹장·피플스클럽만. 등록 가게 s101 …은 불러오기가 리뷰를 새로 넣으므로 기록을 남깁니다).

## 2. DB

- 파일: **`server/db/test_accounts.db`** (SQLite, git에 같이 올라갑니다. 팀 모두 같은 계정으로 시험합니다)
- 파일이 없으면 서버가 `server/app/modules/auth/test_accounts.py`의 `DEFAULT_ACCOUNTS` 값으로 만듭니다.
- 이 파일은 지워지지 않습니다.
  - 목업 생성기(`python -m db.mock.generate`)는 `db/data`만 다시 만듭니다.
  - 데모 초기화(`/dev/reset`)는 `db/app_data`만 지웁니다.
- 고친 값은 **서버를 다시 켜지 않아도 다음 로그인부터** 씁니다 (로그인할 때마다 DB를 읽습니다).

표 `test_accounts` (한 줄이 계정 하나)

| 칸 | 뜻 | dona_demo |
|---|---|---|
| `login_id`, `password` | 임시 네이버 로그인 아이디·비밀번호 (시험용 값) | `dona_demo` / `dona1234` |
| `naver_id`, `profile_json` | 네이버 회원 번호 자리와 프로필 (`/v1/nid/me`와 같은 모양). 등록 기록 `owners`의 `naver:<naver_id>`와 이어짐 | `TEST_NAVER_ID_DEMO` |
| `find_store` | `1`이면 로그인할 때마다 등록 기록을 보지 않고 가게 찾기부터 | `0` |
| `store_id` | 로그인하면 들어갈 가게 (예: `s001`). 비우면 이 계정으로 등록해 둔 가게 | 비움 |
| `scene_at` | 로그인하면 서버 시계를 이 시각으로 옮김. **서버를 `DEV_CLOCK_ENABLED=true`로 켰을 때만** | 비움 (실제 시각) |
| `on_logout` | `reset` 로그아웃하면 전부 처음으로 / `keep` 남김 | `keep` |
| `scenario` | 화면에 보일 설명 | |

보는 법 (`server` 폴더에서)

```bash
sqlite3 db/test_accounts.db "SELECT login_id, find_store, store_id, scene_at, on_logout FROM test_accounts"
```

## 3. 어떻게 동작하나

**서버** (`server/app/modules/auth/`)
- `test_accounts.py`: DB를 읽고(없으면 만들고) 계정마다 들어갈 가게(`login_store`)와 화면 설명(`where_it_goes`)을 정합니다.
- `router.py`
  - **로그인 결과**: DB 조건대로 가게를 정합니다(`find_store`면 없음, `store_id`, 아니면 등록 기록 `owners`). 가게가 없으면 앱이 가게 찾기(가입)로 보냅니다.
  - **`POST /api/auth/test/logout`** `{"login_id"}`: `reset`이면 그 가게의 고친 설정과 계산을 지우고 서버 시계를 실제 시각으로 돌립니다. `keep`이면 아무것도 지우지 않습니다.
  - **`POST /api/auth/test/withdraw`** `{"login_id"}`: 등록 기록 `owners`에서 이 계정 줄만 지우고(`registered_stores.remove_owner`), 사장님 확인 승인을 `withdrawn`으로 바꾸고, 그 가게의 고친 설정·계산(서버 메모리)을 지웁니다. 목업 가게로 이은 가게는 리뷰 불러오기 기록(`review_platforms`)도 비웁니다(`registered_stores.clear_review_platforms`). 테스트 계정, 가게 파일, 리뷰, 등록 기록 `stores`는 그대로입니다.

**앱** (`mobile/src/lib/testAccount.ts`)
- 이 기기 기록 = 처음 설정(`dona.prefs.v1`), 끝낸 카드(`dona.cardState.v1`), 고쳐 쓴 답글(`dona.drafts.v1`), 홈 저장본
- **로그인** (`onTestLogin`): `keep` 계정은 계정 몫으로 보관해 둔 기록(`dona.keep.testAccount.<아이디>`)을 되살립니다. `reset` 계정은 지웁니다.
- **로그아웃** (`onTestLogout`, 설정 › 계정 › 로그아웃): `keep`이면 기록을 계정 몫으로 보관합니다.
- **탈퇴하기** (`onTestWithdraw`, 설정 › 계정 › 탈퇴하기): 서버에 탈퇴를 알리고, 이 기기 기록과 그 계정 보관본을 지웁니다 → 시작 화면. 같은 아이디로 다시 로그인하면 가게 찾기부터 합니다.

## 4. 알아 둘 것

- 보관본은 **그 브라우저(기기)에만** 있습니다. 다른 브라우저에서 로그인하면 등록한 가게로 들어가되 처음 설정부터 합니다.
- 피플스클럽은 2026-11-13에 목업 가게 연결이 생기기 전에 **s101**로 등록된 기록이 남아 있습니다(각자 PC의 `db/app_data/registry.db`). 이 기록이 있는 PC에서 피플스클럽을 다시 등록하면 s004로 잇다가 막힙니다. 초옹장은 해당 없습니다.
- 시험: `server/tests/modules/test_naver_login.py` (테스트는 실제 DB 대신 임시 DB를 씁니다, `tests/conftest.py`)
