# 도나(DONNA) 확인 가이드: 디자인과 앱을 보는 법

처음 합류한 분이 **디자인을 보고**, **앱을 내 컴퓨터에서 켜서 웹으로 확인**하는 방법입니다.
서버, DB, 클라우드 연결은 [backend_integration.md](./backend_integration.md)를 보세요.

> 기준: 브랜치 `jheroorehj/feat-frontend`, 2026-11-11.
> 앱은 지금 **서버 없이 목업으로만** 동작합니다. 로그인, 리뷰, 매출, 답글 올리기는 모두 흉내이고, 바깥으로 아무것도 보내지 않습니다.

---

## 1. 무엇이 어디에 있나요

| 자리 | 내용 |
|---|---|
| `mobile/` | **지금 만드는 앱** (React Native + Expo). 웹, iOS, 안드로이드를 한 코드로 |
| `frontend/` | 예전 Next.js 판. 참고용이고 더 고치지 않습니다 |
| `server/` | FastAPI 서버. 최신 서버 코드는 `main` 브랜치에 있습니다 |
| `contracts/sample_responses/` | 서버 응답 예시 JSON. 앱 목업이 이 파일을 복사해서 씁니다 |
| `docs/demo_scenario.md` | 발표 시나리오와 매장별 확인 시나리오 |
| `docs/frontend_mock_and_api_needs.md` | 화면별로 서버에 필요한 API와 데이터 (자세한 목록) |
| `docs/backend_integration.md` | 목업을 실제 서버, DB, 클라우드로 바꾸는 순서 |
| `docs/audit_3principles.md` | "사람들이 쓰지 않는 앱의 3가지" 기준 점검 |

---

## 2. 디자인 보기 (Figma)

- 파일: https://www.figma.com/design/wXGnsDy7RlcIWL3cJCcV3Z
- 열리지 않으면 파일 주인에게 보기 권한을 요청하세요.

페이지 하나가 시안 하나입니다. **번호가 클수록 최신**이고, 지금 앱은 **06 화면에 07, 08을 더한 모습**입니다.

| 페이지 | 내용 |
|---|---|
| 목차 · 시작은 여기 | 페이지별 한 줄 설명 |
| 00 · 에셋 | 도나 캐릭터 시트, 배너, 아이콘 세트, 네이버 로고 |
| 01 ~ 05 | 지난 시안 (참고용) |
| **06 · 시안 v6** | 오늘 할 일 카드, 답글, 점검, 이번 주, 매출, 설정, 처음 쓰는 날. 지금 앱 화면 대부분의 기준 |
| **07 · 시안 v7 (홈)** | 홈(오늘 할 일과 끝낸 일), 지금 할 일, 끝낸 일 다시 보기 |
| **08 · 시안 v8** | 다 끝낸 홈의 "오늘 함께 한 일", 첫 화면과 가입, 로그인, 네이버 계정 연결 |

- 각 시안 섹션 오른쪽 위나 아래에 **규칙 보드**(예: `07-0`, `08-0`, `08-1-0`)가 있습니다. 화면이 어떻게 움직이는지는 여기에 적혀 있어요.
- 화면 이름의 번호(예: `06-4`, `08-1c`)는 코드 주석과 문서에서 같은 번호로 부릅니다. 코드에서 `08-1c`를 검색하면 그 화면 코드가 나옵니다.
- 색과 글자 스타일은 Figma 변수 `DoNA 03 · 토큰`, 글자 스타일 `DoNA 03/*`이고, 앱의 `mobile/src/theme/tokens.json`과 같은 값입니다.

---

## 3. 내 컴퓨터에서 앱 켜기 (웹)

### 3-1. 준비물 (처음 한 번)

| 필요한 것 | 확인 방법 | 메모 |
|---|---|---|
| Git | `git --version` | |
| Node.js **20 이상** | `node -v` | 확인한 버전은 24.8. https://nodejs.org 에서 LTS 설치 |
| 크롬 같은 브라우저 | | 휴대폰 크기로 보려고 개발자 도구를 씁니다 |

### 3-2. 코드 받기와 설치 (처음 한 번)

```bash
git clone https://github.com/Yeon0713/DoD.git
```

```bash
cd DoD
```

```bash
git checkout jheroorehj/feat-frontend
```

```bash
cd mobile
```

```bash
npm install
```

> 패키지를 새로 넣을 때는 `npm install 이름` 대신 `npx expo install 이름`을 씁니다. Expo 버전에 맞는 것을 골라 줍니다.

### 3-3. 켜기 (할 때마다)

`mobile/` 폴더에서:

```bash
npx expo start --web --port 8082
```

- 처음에는 화면을 묶는 데 30초쯤 걸립니다. 터미널에 `Web Bundled`가 나오면 준비된 거예요.
- 브라우저에서 http://localhost:8082 를 엽니다. 하얀 화면이면 몇 초 기다렸다가 새로 고침하세요.
- 끌 때는 터미널에서 `Ctrl + C`.

### 3-4. 휴대폰 크기로 보기

앱은 휴대폰 화면(가로 375) 기준으로 만들었습니다. 넓은 화면으로 보면 어색해요.

1. 크롬에서 `F12`(Mac은 `Cmd + Option + I`)로 개발자 도구를 엽니다.
2. 왼쪽 위 휴대폰 모양 아이콘(Toggle device toolbar)을 누릅니다.
3. 크기를 `iPhone 12 Pro`나 직접 `375 × 812`로 맞춥니다.

### 3-5. 처음 화면에서 들어가기 (목업 로그인)

처음 열면 **첫 화면(08-1)**이 나옵니다. 진짜 계정은 필요 없어요.

| 방법 | 하는 일 |
|---|---|
| **네이버로 시작하기** | 1.5초 뒤 네이버에서 돌아온 것으로 보고 가게 확인(08-1c)으로 갑니다. 진짜 네이버로 가지 않아요 |
| **휴대폰 번호로 시작하기** | 아무 번호(010으로 시작하는 11자리)나 적고, 숫자 6개는 아무거나 적으면 됩니다. `000000`만 틀린 숫자로 봅니다 |

그다음 "이대로 좋아요"를 몇 번 누르면 홈이 나옵니다.

### 3-6. 개발 화면으로 원하는 장면 바로 열기

로그인 없이 원하는 장면을 바로 보려면 **개발 화면**을 쓰세요.

- 여는 법: http://localhost:8082/dev , 또는 앱의 **설정 탭 맨 아래 "개발 화면"**
- 할 수 있는 것
  - **매장 시나리오**: 매장 6곳(국수집, 치킨호프, 닭갈비, 백반, 순대국밥, 곱창집) 중 하나와 장면을 누르면, 그 가게 할 일 3~6개로 홈이 열립니다. 맨 위 **춘천 대학가 국수집 화요일 오후**가 발표 시나리오예요. 누르는 순서는 [demo_scenario.md](./demo_scenario.md)에 있습니다.
  - **Figma 화면 바로 가기**: 화면 번호(예: `04-10`, `06-24`)를 누르면 그 화면을 그 시각 상태로 엽니다.
  - **문제 상황**: 인터넷 끊김, 올리기 실패, 느린 응답을 켜고 끌 수 있습니다.
  - **처음부터 다시 (모두 지우기)**: 이 브라우저에 저장된 상태(로그인, 처리한 카드, 설정)를 모두 지웁니다. 화면이 이상하게 남아 있으면 이걸 누르세요.

> 개발 화면은 개발 중일 때만 보입니다. 배포 빌드에서 보려면 `EXPO_PUBLIC_SHOW_DEV=true`로 빌드합니다.

### 3-7. 화면을 다 둘러보는 순서 (추천)

1. 개발 화면 → 춘천 대학가 국수집 → **화요일 오후**
2. 홈에서 "지금 하기"로 할 일 5개를 차례로 처리 (답글 달기, 리뷰 점검, 단골 답글, 메뉴판 바꾸기, 포스터 올리기)
3. 다 끝내면 홈에 "오늘 함께 한 일"이 나옵니다. 끝낸 일을 누르면 다시 볼 수 있어요.
4. 아래 탭 **이번 주**(요일을 눌러 보기), **매출**("자세히"), **설정**(계정, 장사 시간, 네이버 플레이스)
5. 설정 › 계정 › 로그아웃 → 로그인 화면 → 휴대폰 번호로 로그인

---

## 4. 휴대폰에서 보기 (선택)

같은 와이파이에 있는 휴대폰에서 볼 수 있습니다.

1. 휴대폰에 **Expo Go** 앱을 설치합니다 (App Store, Play 스토어).
2. `mobile/` 폴더에서:

```bash
npx expo start
```

3. 터미널에 나온 QR 코드를 휴대폰 카메라(iOS)나 Expo Go(안드로이드)로 찍습니다.

- 웹에서 안 되는 것(공유 창, 사진 고르기, 알림, 문자 숫자 자동 채우기)은 휴대폰에서만 확인할 수 있습니다.
- iOS 시뮬레이터(`npx expo run:ios`)도 되지만 느립니다. 화면 확인은 웹이 가장 빠릅니다.

---

## 5. 고친 뒤 확인하기

`mobile/` 폴더에서 아래 세 가지가 통과하면 올려도 됩니다.

```bash
npm run typecheck
```

```bash
npm run lint
```

```bash
npx expo export --platform web
```

- 마지막 명령은 배포용 웹 파일이 만들어지는지 봅니다 (`dist/` 폴더, Git에 올라가지 않음).
- 커밋 메시지 규칙은 저장소 맨 위의 [commit_guide.md](../commit_guide.md)를 따릅니다.
- 디자인을 바꾸는 일은 **Figma를 먼저 고치고** 코드를 고칩니다. 화면 번호를 코드 주석에 같이 적어 주세요.

---

## 6. 코드에서 화면 찾기

| 화면 | 주소 | 코드 |
|---|---|---|
| 첫 화면, 가입, 로그인 (08-1) | `/start`, `/login`, `/start/phone`, `/start/code`, `/start/naver-login` | `src/components/start/AccountScreens.tsx`, `StartScreens.tsx` |
| 처음 쓰는 날 (06-2 ~ 06-3b) | `/start/store`, `/start/naver-confirm`, `/start/notify-time` | `src/components/start/StartScreens.tsx` |
| 홈 (07-1, 07-2, 08-2) | `/` | `src/components/home/HomeScreen.tsx` |
| 지금 할 일 (07-3) | `/task` | `src/components/task/TaskScreen.tsx`, `TaskCard.tsx` |
| 끝낸 일 다시 보기 (07-4) | `/done/카드id` | `src/components/home/DoneScreen.tsx` |
| 답글, 점검 | `/reply/...`, `/check/...` | `src/components/reply/` |
| 메뉴판, 네이버 | `/menu-order/...`, `/naver/connect` | `src/components/naver/` |
| 포스터 | `/poster/...` | `src/components/poster/` |
| 이번 주, 매출, 설정 | `/week`, `/sales`, `/settings` | `src/components/week/`, `sales/`, `settings/` |
| 개발 화면 | `/dev` | `src/components/dev/` |
| 카드 문구 만들기 | | `src/lib/cards.ts` |
| 목업 데이터 | | `src/mocks/` (매장 시나리오 `personas.ts`, 목업 서버 `server/`) |

주소와 화면 파일의 관계: `src/app/` 아래 파일 하나가 주소 하나입니다 (Expo Router). 실제 화면 코드는 `src/components/`에 있습니다.

---

## 7. 자주 막히는 곳

| 증상 | 해결 |
|---|---|
| 하얀 화면만 나와요 | 처음 묶는 중입니다. 터미널에 `Web Bundled`가 나온 뒤 새로 고침하세요 |
| `Port 8082 is being used` | 이미 켜져 있습니다. 그 터미널을 쓰거나 `--port 8083`처럼 다른 번호로 켜세요 |
| 화면 상태가 꼬였어요 (계속 같은 카드, 로그인 안 됨) | 개발 화면 → **처음부터 다시**. 그래도 이상하면 브라우저 개발자 도구 › Application › Local Storage에서 `dona.`로 시작하는 값을 지웁니다 |
| 고쳤는데 화면이 안 바뀌어요 | `Ctrl + C`로 끄고 `npx expo start --web --port 8082 --clear`로 켜세요 (묶음 캐시 지우기) |
| 글자가 기본 글꼴로 나와요 | 글꼴(Noto Sans KR)을 받는 중입니다. 새로 고침하세요 |
| `npm install`이 실패해요 | Node 버전(`node -v`)이 20 이상인지 보세요. `mobile/node_modules`를 지우고 다시 설치합니다 |
