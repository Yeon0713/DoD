# 브랜치 `jheroorehj/fix-integration` 바뀐 점 (2026-11-12)

PR #12(앱을 실제 DB·분석·CLOVA X 와 연결) 뒤 통합 점검을 하면서 고치고 더한 것을 팀원이 한 번에 볼 수 있게 정리했습니다.
가입·매장 등록·데모 테스트 모드의 자세한 설명은 [store-registration-and-demo-test-mode.md](store-registration-and-demo-test-mode.md) 에 있습니다.

> 정리: 영웅 · 기준 커밋 `d5c96bf` (main 의 그 뒤 문서 커밋 2개는 합치지 않았습니다)

---

## 1. 먼저 알아 둘 것 (팀원 코드에 손댄 곳)

남의 파트 코드를 고친 곳입니다. **동작이 바뀌는 곳만** 적었고, 모두 테스트를 더했습니다.

| 파트 | 파일 | 바뀐 것 | 왜 |
|---|---|---|---|
| DB (지호) | `server/db/data/*.db`, `db/models.py`, `db/mock/generate.py` | **바꾸지 않음** | 등록한 가게는 따로 만든 파일(s101 …)에만 씀 |
| DB 읽기 | `app/data_pipeline/read_store_db.py` | `read_reviews` 가 **등록한 가게일 때만** 리뷰마다 `platform` 을 붙임 | 가게 파일 reviews 표에 플랫폼 칸이 없어서, 불러온 리뷰의 플랫폼은 등록 기록에 적어 둠 |
| 분석 (태성) | `app/analysis/pattern/sales_daily.py` | 인건비 계산: 근무표를 시작 시각 순으로 정렬해 겹칠 수 있는 근무만 봄 | 장사 시간 저장 뒤 다시 계산이 14초 걸렸음 (날마다 근무 1,300건 × 시간대). **세 가게 결과가 한 칸도 다르지 않은 것 확인**, 2.4초로 줄음 |
| 분석 → 계획 | `app/data_pipeline/analysis_to_plan_inputs.py` | ① 요일별 장사 시간에서 대표 시간·쉬는 날을 뽑음 ② 판 적이 없는 요일·시간대의 예상 매출·비율이 비면 0·1.0 으로 채움 | ① 요일마다 다른 장사 시간 저장 ② 주말엔 점심만 여는 가게에서 달력이 500 오류 |
| 계획 엔진 (여헌) | `app/planner/data_shapes.py` | `StoreSettings` 에 `weekly_hours`, `break_time`, `work_hours`, `extra_slots` (모두 없어도 되는 칸) | 요일별 장사 시간, 브레이크, 출퇴근, 더 넣은 알림 |
| 계획 엔진 | `make_plan.py`, `notification_time_helpers.py`, `rule_menu_order.py`, `info_alerts.py` | 쉬는 날에 잡힌 승인·실행을 다음 여는 날로 옮김, 쉬는 날은 메뉴판을 바꾸지 않고 그 다음 날은 앞의 여는 날과 견줌, 월요일 휴무 가게는 그 주 첫 여는 날에 주간 예고 | 쉬는 날이 있는 가게에서 500 이 나고 알림이 쉬는 날로 잡혔음 |
| 서버 계산 보관 | `app/data_pipeline/store_snapshot_cache.py` | 계획 엔진에 넘기는 달력 칸의 `computed_at` 을 "그 날짜를 처음 안 때"로, 어제 칸을 붙여 넘김(오늘 실행할 메뉴판이 아침에 사라지지 않게) | 10분마다 다시 계산할 때 승인 요청 시각이 계속 밀렸음 |
| 설정 | `app/modules/settings/*` | `weekly_hours`, `break_time`, `work_hours`, `extra_slots` 저장, 알림 시각 검사 범위에 출퇴근 시간 반영, 바쁜 시간대 중복 제거 | |
| 답글 (CLOVA) | `app/review_reply_writer/*` | 약속·지어낸 사정 거르기 정규식 손질, 숫자(날짜·전화번호)가 바뀐 답은 버리고 다시, 세 번째 시도 | "정확한 서비스를 제공할 수 있도록" 같은 평범한 문장을 잘못 걸러 502 |
| 공통 | `app/core/seoul_time.py`, `app/main.py`, `app/core/config.py` | 개발용 시계 앞당기기(`/dev/clock`), 초기화(`/dev/reset`) — `DEV_CLOCK_ENABLED=true` 일 때만. 새 설정 `NAVER_LOGIN_*`, `DEMO_STORE_DATA` | 다음 날 시험, 시연 초기화 |

## 2. 새로 생긴 것

### 서버
| 파일 | 하는 일 |
|---|---|
| `app/modules/auth/` | 네이버 로그인 (OAuth 순서 그대로). `NAVER_LOGIN_CLIENT_ID/SECRET` 이 없으면 **임시 네이버 로그인 화면**(테스트 계정 `dona_test1~3`, 비밀번호는 `test_accounts.py`) |
| `app/modules/stores/` | 매장 등록(네이버 지도에서 읽어 DB 저장), 지도 그림(Static Map, 번호 핀), 리뷰 불러오기(배민·네이버·쿠팡이츠, 지금은 목업), **우리 전용 목업 주문·매출·알바**(`demo_data.py`) |
| `app/core/naver_place.py` | 네이버 지도 가게 화면 읽기(크롤링): 영업시간, 브레이크, 메뉴(이름·가격·사진), 리뷰 수 |
| `app/data_pipeline/registered_stores.py` | 등록한 가게 파일(`db/data/s101.db` …)과 등록 기록(`db/app_data/registry.db`). **둘 다 git 에 올리지 않음** |
| `app/modules/naver/` | `GET /api/naver/search` (네이버 지역 검색, NAVER API HUB 키) 추가, `place` 응답에 주소·업종 |
| `tests/modules/` | 로그인, 매장 등록, 가게 검색, 출퇴근·알림 테스트 (서버 전체 340 통과) |

### 앱 (`mobile/`)
| 화면 / 파일 | 하는 일 |
|---|---|
| 시작·로그인 화면 ☰ 메뉴 (`components/start/DemoMenu.tsx`) | **데모 테스트 모드** 켜기, **초기화** |
| 가게 찾기 → 이 가게가 맞나요? (`components/start/StoreRegister.tsx`, `/start/store`, `/start/store-confirm`) | 지도 번호 핀과 목록, 영업시간 표·메뉴 사진으로 확인 후 등록 |
| 리뷰 불러오기 (`/start/reviews`) | 배민·네이버·쿠팡이츠 각각, 3초 로딩, 안 불러오고 넘어가면 한 번 묻기 |
| 출근·퇴근 (`/start/work-hours`) → 알림 시간 | 출근 10분 뒤 / 브레이크 시작 30분 뒤 / 퇴근 30분 전, **알림 추가하기** |
| 네이버 로그인 화면 | 중간 안내 화면 없이 바로 네이버(임시) 로그인으로. 실패하면 까닭과 다시 하기 |
| 메뉴·사진 고치기 | 네이버 스마트플레이스 열기 (`lib/smartplace.ts`) |
| 물음표 도나 6장 (`assets/donna/q-*.png`) | 상황별 그림 (Figma 00 에셋 `DONNA(5) 1`) |
| 시연용 마우스 (`components/dev/DemoCursor.tsx`) | 웹 주소 끝 `?cursor=1` |

### 앱에서 바뀐 동작
- 로그인한 계정의 가게를 모든 요청에 `?store_id=` 로 붙임. 홈 데이터 캐시는 그 가게 것일 때만 씀.
- "네이버 플레이스 연결" 단계(06-2n)는 없애고, 가게 확인 다음 바로 가게 정보 확인으로.
- 자정을 넘겨 여는 가게는 저장 전에 "아직 준비 중이에요"로 막음.
- 데모 테스트 모드에서는 "알림이 꺼져 있어요" 띠를 띄우지 않음.
- 통합 점검 수정: 이번 주 탭 7일 고정, 다시 쓰기 실패 문구(인터넷/서버 구분)·되돌리기, 매출 문구, 서버가 못 준 화면의 "불러오지 못했어요" 안내 등.

## 3. 켜는 법

```bash
cd server && DEV_CLOCK_ENABLED=true .venv/bin/uvicorn app.main:app --port 8000
cd mobile && npx expo start --web --port 8082
```
앱 시작 화면 ☰ › 데모 테스트 모드 켜기 → 네이버로 시작하기 → 임시 로그인(테스트 계정 넣기) → 가게 찾기.

## 4. 아직 안 된 것 (팀과 정할 것)

- 진짜 네이버 로그인: 도메인을 받아 developers.naver.com 에 앱 등록 후 키 넣기.
- 리뷰 크롤링(배민·네이버·쿠팡이츠): 지금은 목업.
- 손으로 움직이는 지도: NCP 콘솔 Maps 앱에 웹 주소 등록 필요 (지금은 그림 지도).
- 끝낸 일·미룬 일을 서버에 저장하기: 지금은 휴대폰에만 있어 미룬 일이 다음 날 사라짐.
- 고친 설정(요일별 시간, 출퇴근, 추가 알림)은 서버 메모리에만 있어 서버를 다시 켜면 사라짐.
- 자정을 넘겨 여는 가게의 알림 계획 (계획 엔진).
- 포스터를 "전날 만들어 올리기"로 바꾸는 것, 매출 이상 알림 연결 (계획 엔진, 데모 시나리오 계획에 있음).
- 설정 › 알림 받는 시간 화면에도 출퇴근·알림 추가 넣기.

## 5. 확인한 것

- 서버 `pytest` 340 통과, 18 건너뜀. 앱 `tsc --noEmit`, `eslint` 통과.
- 브라우저(웹 375×812)로: 데모 모드 → 임시 로그인 → 피플스클럽 검색·등록 → 리뷰 불러오기 → 출퇴근 → 알림 시간·추가 → 홈(배달 지연 사과 답글, 주말 포스터) → 매출 탭, 로그아웃 뒤 다른 계정 로그인, 이미 등록된 가게 다시 등록, 초기화.
