# 목업에서 실제 서버, DB, 클라우드로: 연결에 필요한 것

앱(`mobile/`)은 지금 **서버 없이 목업으로만** 동작합니다. 이 문서는 실제 데이터, 서버, DB, 클라우드에 연결하려면 **무엇이 이미 있고, 무엇이 없고, 어떤 순서로 하면 되는지**를 정리합니다.

- 화면별로 필요한 필드와 API를 자세히 적은 목록: [frontend_mock_and_api_needs.md](./frontend_mock_and_api_needs.md) 3장 (A ~ Z3)
- 지금 서버 API와 계획 엔진: [server-api-and-planner-guide.md](./server-api-and-planner-guide.md) (`main` 브랜치)
- 앱을 켜는 법: [guide_for_collaborators.md](./guide_for_collaborators.md)

> 기준: 앱은 브랜치 `jheroorehj/feat-frontend` (2026-11-11), 서버는 `main`.
> 2026-11-11에 `main`(리뷰 분류, 분석 결과 계약까지)을 이 브랜치로 병합했습니다. 아직 `main`에 들어가지 않은 팀원 브랜치(`taeseong/feat-review`의 주문 주기와 위험 신호, `jiho/data-shifts`의 알바 근무 목업)는 이 브랜치에 없습니다. 연결 작업 전에 앱 코드를 `main`으로 PR할지 정해야 합니다.

---

## 1. 지금 구조

```
화면 (src/components)
  │  데이터 읽기                     사장님 동작                   이 기기에만 저장
  ▼                                  ▼                             ▼
src/lib/api.ts                     src/lib/actions.ts            src/lib/cardState.ts   (카드 처리 상태)
  │ EXPO_PUBLIC_USE_MOCK             (답글 올리기, 다시 쓰기,       src/lib/localStore.ts  (처음 설정, 네이버 연결, 고쳐 쓴 답글)
  ├─ true(기본) → src/mocks/server   메뉴 순서, 포스터,             src/lib/account.ts     (로그인)
  │               (예시 JSON 계산)   네이버 로그인, 문자 인증)       src/lib/dev.ts         (개발 화면 스위치)
  └─ false → 실제 서버                지금은 기다렸다가 성공만 함
             EXPO_PUBLIC_API_BASE_URL/api/...
```

- **읽기**는 `src/lib/api.ts` 한 곳에서만 합니다. 스위치 하나(`EXPO_PUBLIC_USE_MOCK=false`)로 실제 서버로 바뀝니다.
- **사장님 동작**은 `src/lib/actions.ts` 함수 안만 실제 API 호출로 바꾸면 됩니다. 화면은 이미 "보내는 중", "실패", "다시 하기"를 처리합니다.
- **이 기기 저장소**(`dona.*` 키)는 서버에 계정이 생기면 서버로 옮겨야 합니다. 그대로 두면 휴대폰을 바꾸거나 앱을 지우면 사라집니다.
- 목업 데이터는 `npm run sync-mocks`가 `contracts/sample_responses/`와 `server/db/mock/out/*.csv`에서 복사해 옵니다 (`mobile/scripts/sync-mocks.mjs`).

---

## 2. 앱 쪽 설정 값

`mobile/.env` 파일을 만들어 넣습니다 (Git에 올리지 않음). 이름이 `EXPO_PUBLIC_`으로 시작하는 값은 **앱 안에 그대로 들어가므로 비밀 값을 넣으면 안 됩니다.**

| 이름 | 지금 | 서버 연결 후 |
|---|---|---|
| `EXPO_PUBLIC_USE_MOCK` | 비어 있음 (= 목업) | `false` |
| `EXPO_PUBLIC_API_BASE_URL` | 기본 `http://127.0.0.1:8000` | 서버 주소. 예: `https://api.도메인` |
| `EXPO_PUBLIC_MOCK_DELAY_MS` | 목업 응답 지연 (기본 600) | 쓰지 않음 |
| `EXPO_PUBLIC_SHOW_DEV` | 배포 빌드에서도 개발 화면 보이기 | 실서비스에서는 빼기 |

- 휴대폰(Expo Go)에서는 `127.0.0.1`이 휴대폰 자기 자신입니다. 같은 와이파이의 PC 서버를 쓰려면 PC의 내부 IP(예: `http://192.168.0.10:8000`)를, 아니면 클라우드 주소를 넣습니다.
- 서버 `.env`의 `CORS_ORIGINS`에 웹 주소를 넣어야 웹에서 부를 수 있습니다. 지금 값은 `["http://localhost:3000"]`뿐이라 **`http://localhost:8082`와 배포할 웹 주소를 더해야 합니다.**

---

## 3. API: 있는 것, 모양이 다른 것, 없는 것

> **2026-11-11 확인**: `main`의 서버를 켜고 불러 봤습니다. `today`, `plan`, `calendar`, `reviews`, `settings`, `sales?grain=day`는 200, 앱이 부르는 `sales/live`와 `naver/place`는 404, `Origin: http://localhost:8082`에 대한 CORS 허용은 없었습니다.

### 3-1. 서버에 있고 그대로 쓸 수 있는 것 (예시 데이터를 돌려줌)

| API | 앱에서 쓰는 곳 | 남은 일 |
|---|---|---|
| `GET /api/today` | 홈, 지금 할 일 | 예시 데이터 → 실제 계산 (계획 엔진 + DB) |
| `GET /api/plan?from&to` | 카드 내용 | 앱이 `from`, `to`를 아직 안 보냄 (오늘 기준 기간 넣기) |
| `GET /api/calendar?from&to` | 이번 주 | 날씨 필드 추가 (API 문서 3장 Q) |
| `GET /api/reviews?from&to` | 답글, 점검 | 리뷰 사진, 주문 시각(`photos`, `ordered_at`) 추가 (3장 U, V) |
| `GET /api/settings`, `PATCH /api/settings` | 설정, 처음 쓰는 날 | 요일별 장사 시간, 브레이크 타임 필드와 검사 추가 (3장 P, W). 지금은 서버 메모리에만 저장 → DB 저장 |

> 서버 응답의 `"is_example": true`가 실제 데이터로 바뀌면 `false`가 됩니다. 응답 모양은 같아서 화면 코드는 고치지 않아도 됩니다.

### 3-2. 서버에 있지만 앱이 기대하는 모양과 다른 것

| 앱이 부르는 것 | 서버에 있는 것 | 정할 일 |
|---|---|---|
| `GET /api/sales/live`, `/weeks`, `/menus`, `/times`, `/channels`, `/months` (매출 탭 6장) | `GET /api/sales?grain=day\|week\|month\|weekday_daypart` | 서버에 6개를 만들지, 앱이 `grain` 응답을 받아 계산할지. 앱 목업 계산(`src/mocks/server/sales.ts`)을 서버로 옮기는 것을 권합니다 (3장 R) |

### 3-3. 서버에 아직 없는 것 (새로 만들어야 함)

| 무엇 | 제안 API | 앱에서 바꿀 곳 | API 문서 |
|---|---|---|---|
| 답글 초안 | `plan` 항목에 `draft_text` 필드 | `mocks/extras.ts` `mockDraft` 삭제 | 3장 A |
| 답글 다시 쓰기 | `POST /api/replies/{plan_id}/rewrite` | `actions.ts` `rewriteReply` | 3장 B |
| 답글 올리기 (배달앱, 네이버) | `POST /api/replies/{plan_id}/publish` | `actions.ts` `publishReply` | 3장 C, S |
| 카드 처리 상태 (다 했어요, 나중에, 끝낸 시각) | `PATCH /api/plan/{plan_id}` 또는 `GET/POST /api/card-state` | `lib/cardState.ts` | 3장 D, Z2 |
| 승인만 하고 나중에 실행 | `POST /api/plan/{plan_id}/approve` | `TaskScreen` 답글 맡기기 | 3장 E |
| 가게 찾기 | `GET /api/stores/search?q=` | `start/StartScreens.tsx` | 3장 F |
| 네이버 플레이스 불러오기 | `GET /api/naver/place` | `api.naverPlace` (지금 목업만) | 3장 X |
| 네이버 연결, 메뉴 순서 바꾸기 | `POST /api/naver/connect`, `POST /api/menu-order/{plan_id}` | `actions.ts` | 3장 H, T |
| 포스터 만들기, 저장 | `POST /api/posters` (그림 주소 돌려줌) | `actions.ts` `makePoster`, 포스터 화면 | 3장 I |
| 결과 알림 (재주문, 불만 줄었어요) | `plan.notice_items`에 `REPLY_RESULT`, `FIX_RESULT` | `mocks/extras.ts` `RESULT_NOTICES` 삭제 | 3장 J |
| 행사, 경기 이름 | `calendar`에 이름 필드 | `lib/cards.ts` `eventName` | 3장 M |
| **가입, 로그인** (네이버, 휴대폰 문자) | `POST /api/auth/naver`, `POST /api/auth/phone/code`, `POST /api/auth/phone/verify` | `actions.ts`, `lib/account.ts` | 3장 Z3 |
| **계정, 네이버 계정 연결** | `GET /api/account`, `POST/DELETE /api/account/naver`, `DELETE /api/account` | `settings/AccountSettingsScreen.tsx` | 3장 Z3 |
| 사장님 설정 (처음 쓰는 날 마침, 알림 꺼 둠 등) | 계정에 저장 | `lib/localStore.ts` `prefs` | 3장 N |
| 휴대폰 알림 (푸시) | `POST /api/devices` (푸시 토큰 저장) + 서버가 알림 시각에 보냄 | `start/notify.native.ts` | 3장 O, Y |

---

## 4. 로그인과 계정에 필요한 것

지금 서버에는 **사용자 개념이 없습니다** (매장 하나 `store_001` 고정). 실제로 쓰려면 이것부터 있어야 다른 API가 "누구의 가게"인지 압니다.

1. **사장님 계정과 가게 연결**: 사장님(owner) 한 명이 가게(store) 하나 이상을 가집니다. 모든 API가 로그인한 사장님의 가게 데이터만 돌려줘야 합니다.
2. **로그인 토큰**: 로그인하면 서버가 토큰(예: JWT)을 줍니다. 앱은
   - 토큰을 휴대폰 안전 저장소에 둡니다: `npx expo install expo-secure-store` (웹은 다른 방법 필요)
   - `src/lib/api.ts`의 `request()`에서 모든 요청에 `Authorization: Bearer 토큰` 머리글을 붙입니다 (지금은 없음).
   - 토큰이 만료되면(401) 로그인 화면으로 보냅니다. 지금 아래 탭의 로그인 확인(`app/(tabs)/_layout.tsx`)이 `account.method`를 보므로, 이 값을 토큰 유무로 바꾸면 됩니다.
3. **네이버 로그인**
   - 네이버 개발자 센터(https://developers.naver.com)에 애플리케이션을 등록하고 Client ID, Secret을 받습니다. Secret은 **서버 `.env`에만** 둡니다.
   - 앱은 네이버 로그인 화면을 열고 돌아온 `code`를 서버에 보냅니다 (`POST /api/auth/naver { code }`). 앱에서는 `expo-auth-session`과 앱 주소 체계(scheme, `app.json`)를 쓰고, 돌아올 주소(redirect URI)를 네이버에 등록합니다. 웹은 `http://localhost:8082/...`와 배포 주소를 등록합니다.
   - 네이버 플레이스(가게 정보, 메뉴 순서)를 바꾸는 권한은 일반 네이버 로그인과 다릅니다. **스마트플레이스 연동이 가능한 공식 API나 제휴가 있는지 먼저 확인해야 합니다.** 화면(06-50 ~ 06-58)은 이것이 된다고 보고 그렸습니다.
4. **휴대폰 문자 인증**: 서버에 이미 `app/core/sens.py`(네이버 클라우드 SENS 문자)가 있습니다. 숫자 6개를 만들어 3분 동안 저장(DB나 캐시)하고, 같은 번호에 너무 자주 보내지 않게 막습니다. 발신 번호는 SENS 콘솔에 등록한 번호만 됩니다.

---

## 5. DB에 필요한 것

`server/db/`(PostgreSQL, Alembic)에 지금 있는 테이블(`main` 기준): `store`, `menu`, `orders`, `order_items`, `reviews`, `staff`, `shifts`, `events`, `games`, `weather_daily`.

앱 화면을 실제로 돌리려면 더 필요한 테이블 (이름은 제안):

| 테이블 | 한 줄 = | 주요 열 | 쓰는 화면 |
|---|---|---|---|
| `owner` | 사장님 | 이름, 만든 날 | 계정 |
| `auth_identity` | 로그인 방법 하나 | owner_id, kind(`naver`/`phone`), 네이버 id 또는 휴대폰 번호 | 가입, 로그인 |
| `owner_store` | 사장님과 가게 연결 | owner_id, store_id, 역할 | 모든 API |
| `phone_code` | 보낸 인증 숫자 | 번호, 숫자(해시), 만료 시각, 시도 횟수 | 08-1o |
| `plan_item` | 계획 엔진이 만든 할 일 | plan_id, store_id, 종류, 승인 요청 시각, 실행 시각, 이유, `draft_text` | 홈, 지금 할 일 |
| `card_state` | 카드 처리 기록 | store_id, card_id, 상태(`done`/`snoozed`), 끝낸 시각, 다시 알릴 시각, 한 일(`note`) | 홈, 끝낸 일, 오늘 함께 한 일 |
| `reply` | 올리거나 맡긴 답글 | review_id, plan_id, 글, 상태(`scheduled`/`published`/`failed`), 올린 시각, 배달앱 | 답글, 끝낸 일 |
| `poster` | 만든 포스터 | plan_id, 메뉴, 큰 글자, 가게 줄, 색, 그림 주소 | 포스터 |
| `menu_order_change` | 메뉴 순서 바꾼 기록 | plan_id, 바꾼 순서, 바꾼 시각, 되돌린 시각 | 메뉴판 |
| `naver_link` | 네이버 연결 | owner_id, place_id, 토큰(암호화), 알아서 바꾸기 켬 | 설정 › 계정, 네이버 플레이스 |
| `device` | 알림 받을 휴대폰 | owner_id, 푸시 토큰, 플랫폼 | 휴대폰 알림 |
| `owner_prefs` | 사장님 설정 | 처음 설정 마침, 알림 꺼 둠, 첫날 카드 봄 | 처음 쓰는 날, 홈 |

- `store`의 `slots`, `dayparts`, `busy_dayparts`(JSON)에 요일별 장사 시간(`weekly_hours`)과 브레이크 타임(`break_time`)을 더합니다 (API 문서 3장 W).
- 리뷰를 배달앱별로 가져오는 방법(배민, 쿠팡이츠, 요기요, 네이버)이 정해져야 `reviews`가 실제 데이터가 됩니다. 공식 API가 없는 곳이 많아 **가장 먼저 확인할 위험 요소**입니다.

---

## 6. 클라우드 (네이버 클라우드 기준 예시)

서버에 이미 네이버 클라우드 키(`NCLOUD_*`), HyperCLOVA X(`CLOVA_STUDIO_*`), SENS, Maps, API HUB 설정 자리가 있습니다(`server/.env.example`).

| 필요한 것 | 예 | 메모 |
|---|---|---|
| 서버 실행 | NCP Server 또는 Kubernetes Service에 Docker로 FastAPI | HTTPS 도메인 필요 (앱 스토어 정책, 네이버 로그인 돌아올 주소) |
| DB | Cloud DB for PostgreSQL | `DATABASE_URL`만 바꾸면 Alembic 그대로 |
| 파일 저장 | Object Storage | 포스터 그림, 리뷰 사진. 앱에는 주소만 줌 |
| 문자 | SENS | 휴대폰 인증 (이미 코드 있음) |
| 답글 초안, 다시 쓰기 | HyperCLOVA X (`app/core/clova.py`) | 3장 A, B |
| 정해진 시각 작업 | 서버 안 스케줄러나 Cloud Functions | 계획 엔진 계산, 맡긴 답글 올리기, 알림 시각 푸시 |
| 비밀 값 | 서버 `.env` 또는 클라우드 비밀 저장소 | Git과 앱(`EXPO_PUBLIC_*`)에 넣지 않기 |
| 웹 배포 | `npx expo export --platform web` 결과(`dist/`)를 Object Storage + CDN | 웹 주소를 서버 `CORS_ORIGINS`와 네이버 돌아올 주소에 등록 |
| 앱 배포 | EAS Build (`npx eas-cli build`) | 빌드마다 `EXPO_PUBLIC_API_BASE_URL`을 실서버로. 푸시 알림은 개발 빌드가 필요 (Expo Go에서는 안 됨) |

---

## 7. 연결 순서 (추천)

각 단계는 "다 됐다"를 확인할 방법과 함께 적었습니다.

**0단계. 브랜치 맞추기**
- `main`은 이 브랜치에 병합해 두었습니다 (2026-11-11). 앱을 `main`으로 PR하고, 팀원 브랜치가 `main`에 들어오면 다시 받아옵니다. 서버는 `main`의 것을 기준으로.
- 확인: 한 브랜치에서 `server/`와 `mobile/`이 함께 켜짐.

**1단계. 읽기 API를 실제 서버로 (예시 데이터 그대로)**
- 서버 `CORS_ORIGINS`에 `http://localhost:8082` 추가, 서버 켜기.
- `mobile/.env`에 `EXPO_PUBLIC_USE_MOCK=false`, `EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`.
- 확인: 웹에서 이번 주, 설정이 서버 예시 데이터로 뜸. 매출 탭은 3-2를 정하기 전까지 실패 화면이 나옵니다.
- 알아 둘 것: 서버 예시 데이터는 **2026-11-17 화요일** 기준이고, 실제 서버 모드에서 앱은 **진짜 오늘 날짜**를 씁니다. 날짜가 다르면 홈에 할 일이 하나도 안 보입니다(다 끝낸 화면). 예시 날짜에 맞춰 보려면 서버가 오늘 날짜로 계산하게 될 때(2단계)까지 기다리거나, 확인용으로 `src/lib/time.ts`의 `nowFrom`이 실제 서버 모드에서도 가상 시각을 쓰게 잠시 바꿉니다.
- 알아 둘 것: 목업 모드에서만 하는 일(데모 한 주 묶음 만들기, 매장 시나리오, 가상 시각)은 꺼집니다. 개발 화면의 매장 시나리오는 목업 전용입니다.

**2단계. DB에 실제 데이터, 서버 응답을 DB에서**
- 목업 생성(`python -m db.mock.generate`)으로 DB를 채우고, 화면용 API의 `data_provider.py`를 DB 조회로 바꿈.
- 확인: 응답의 `is_example`이 `false`.

**3단계. 계정과 로그인**
- 4장의 owner, auth_identity, 토큰. 앱 `request()`에 `Authorization` 머리글, `actions.ts`의 `naverLogin`, `sendPhoneCode`, `verifyPhoneCode`를 실제 호출로.
- 확인: 다른 휴대폰으로 같은 계정에 들어가면 같은 가게가 보임.

**4단계. 사장님 동작과 기록을 서버로**
- 카드 처리 상태, 답글 올리기와 맡기기, 고쳐 쓴 답글, 메뉴 순서, 포스터 (3-3 표).
- `lib/cardState.ts`, `lib/localStore.ts`의 이 기기 저장을 API로 바꿈.
- 확인: 앱을 지웠다 다시 깔아도 "오늘 끝낸 일"이 그대로.

**5단계. 외부 연결**
- 배달앱 리뷰 가져오기와 답글 올리기, 네이버 플레이스, HyperCLOVA X 초안, 푸시 알림.
- 확인: 실제 리뷰에 단 답글이 배달앱에 보임.

**6단계. 클라우드 배포**
- 6장 표대로 서버, DB, 파일 저장, 웹과 앱 배포.

---

## 8. 목업에만 있는 것 (실서비스 전에 지우거나 숨길 것)

| 파일 | 내용 | 실서비스에서 |
|---|---|---|
| `src/mocks/server/` | 앱 안 목업 서버 | `USE_MOCK=false`면 안 씀. 지워도 됨 |
| `src/mocks/data/` | 예시 JSON, 주문 8,368건 | 위와 같음 |
| `src/mocks/extras.ts` | 답글 초안, 결과 알림, 업종별 메뉴 예시, 가게 주소 | 3-3이 생기는 대로 하나씩 삭제 |
| `src/mocks/personas.ts` | 매장 시나리오 6곳 | 개발 화면 전용 |
| `src/components/dev/`, `app/dev.tsx` | 개발 화면 | 배포 빌드에서는 링크가 숨겨짐. 주소로는 열리므로 실서비스 전에 막기 |
| `src/lib/dev.ts` | 가상 시각, 실패 스위치 | 목업 모드에서만 효과 |
| `src/lib/actions.ts` | 기다렸다 성공하는 흉내 | 함수 안을 실제 호출로 |
| `NaverLoginScreen`의 대기 | 1.5초 뒤 돌아온 것으로 봄 | 실제 네이버 로그인 화면 열기 |
