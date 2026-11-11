# 도나 모바일 앱 (Expo)

iOS · Android · 웹을 한 코드로 만드는 앱이다. Expo SDK 58, Expo Router, NativeWind 4, TanStack Query, Noto Sans KR.

## 실행

```bash
cd mobile
npm install
npx expo start
```

터미널에서 키를 누른다.

- `i` iOS 시뮬레이터 (Xcode 필요)
- `a` 안드로이드 에뮬레이터 (Android Studio 필요)
- `w` 웹 브라우저
- 실제 휴대폰은 Expo Go 앱으로 QR 코드를 찍는다.

확인용 명령:

```bash
npx tsc --noEmit                    # 타입 검사
npm run lint                        # ESLint (eslint-config-expo, React 훅 규칙 포함)
npx expo-doctor                     # 의존성 · 설정 점검
npx expo export --platform web      # 웹 번들이 만들어지는지
npx expo run:ios                    # 네이티브 빌드로 시뮬레이터에 설치
```

패키지는 `npm install` 대신 `npx expo install <이름>`으로 넣는다. SDK에 맞는 버전을 골라 준다.

## 폴더

```
mobile/
├─ app.json              앱 이름 · 아이콘 · 스플래시
├─ tailwind.config.js    토큰을 Tailwind 클래스로 바꾸는 곳
├─ babel.config.js       NativeWind 설정
├─ metro.config.js       NativeWind 설정 (src/global.css 읽음)
├─ assets/               아이콘 · 스플래시 이미지
└─ src/
   ├─ app/               화면 (파일 = 주소)
   │  ├─ _layout.tsx     폰트 로딩, QueryClient, 전체 Stack
   │  ├─ (tabs)/         하단 탭: index(홈, 07) · week(이번 주) · sales(매출) · settings(설정)
   │  ├─ task.tsx        지금 할 일 (07-3): 홈에서 카드 하나를 열어 처리한다
   │  └─ done/[id].tsx   끝낸 일 다시 보기 (07-4)
   ├─ components/        화면 조각 (home: 홈과 끝낸 일, task: 지금 할 일과 카드, ui/nav.ts: 화면 이동 도우미)
   ├─ lib/               화면 밖 로직 (useHome.ts의 useTodayCards: 오늘 카드 목록, cardState.ts: 카드 처리 상태)
   ├─ theme/tokens.json  디자인 토큰 원본
   └─ global.css         Tailwind 진입점
```

`@/` 는 `src/` 를 가리킨다. `@/lib/hours` 는 `src/lib/hours.ts` 이다.

## 토큰

토큰 원본은 `src/theme/tokens.json` 하나다. `frontend/src/app/globals.css` 의 `@theme` 값을 그대로 옮겼다.

- 색: `bg-paper`(기본 바탕), `bg-home`(홈 바탕, 07), `text-ink`, `border-line`, `bg-brand`, `text-urgent` …
- 글자: `text-display`(28/38 굵게) `text-title`(22/31 굵게) `text-body`(18/28) `text-label`(15/22 중간) `text-button`(18/24 굵게) `text-small`(14/20 중간)
- 모서리: `rounded-card`(20) `rounded-button`(14)

네이티브는 굵기마다 폰트 파일이 다르다. 그래서 `text-title` 같은 글자 클래스가 굵기에 맞는 폰트(NotoSansKR_400Regular / 500Medium / 700Bold)를 함께 고른다. 굵기만 바꿀 때 쓰는 `font-regular` · `font-medium` · `font-bold` 도 font-weight 대신 폰트를 바꾼다 (`tailwind.config.js` 플러그인). `font-*` 플러그인은 `text-*` 뒤에 둔다. 그래야 `text-body font-bold`처럼 같이 쓸 때 굵기가 이긴다. `<Text>` 에는 늘 글자 클래스 하나를 준다. 안 주면 시스템 폰트가 나온다.

탭 바처럼 클래스를 못 쓰는 곳은 `import tokens from '@/theme/tokens.json'` 으로 값을 직접 읽는다.

## 구조

Next.js 판(`frontend/`)의 계산 규칙과 화면 흐름을 그대로 옮기고 Figma 06 시안을 반영했다.

| 자리 | 내용 |
|---|---|
| `src/lib/` | 카드 만들기, 알림 묶음, 알림 시각, 요일별 장사 시간, 점검 사실 등 순수 계산 (Next.js 판과 같은 파일 이름). 데이터는 `api.ts` 한 곳에서만 부른다 |
| `src/lib/storage.ts` | 이 기기 저장소. AsyncStorage를 앱 시작 때 한 번 읽어 메모리에 두고 동기로 읽는다 (`_layout.tsx`가 다 읽은 뒤 화면을 그린다) |
| `src/lib/dev.ts` | 검토 스위치(가상 시각, 동작 실패, 인터넷 끊김, 늦추기, 카드 앞으로). 주소창이 없어서 `/dev` 화면에서 고른다 |
| `src/mocks/server/` | **앱 안 목업 서버**. 서버 예시 응답, 설정 저장과 검사, 네이버 불러오기, 매출 대시보드 계산 |
| `src/mocks/data/` | `npm run sync-mocks`가 `contracts/sample_responses`와 `server/db/mock/out/*.csv`에서 복사한 데이터 |
| `src/components/ui/` | 같이 쓰는 부품: 버튼, 말풍선, 시트, 띠, 탭 틀, 화면 이동(`nav.ts`) |
| `src/app/` | 화면. 주소는 Next.js 판과 같다 (`/reply/{planId}`, `/check/{planId}`, `/poster/{planId}?step=share`, `/start/...`, `/settings/...`, `/sales/...`, `/week/{refId}`, `/dev`, `/lock`) |

`EXPO_PUBLIC_USE_MOCK=false` 와 `EXPO_PUBLIC_API_BASE_URL` 을 주면 목업 서버 대신 실제 서버를 부른다. 서버에 새로 필요한 API와 데이터는 `docs/frontend_mock_and_api_needs.md` 3장(06은 U ~ Y), 앱에서 바뀐 자리는 9장에 있다.

## 검토하기

- 웹: `npx expo start --web` 후 `http://localhost:8081/dev` (이 저장소의 미리 보기 설정은 8082).
- 목업은 **매장 시나리오**로 연다. 개발 화면 맨 위에서 매장(6곳)과 장면을 고르면 그 가게 할 일 3~6개로 홈이 열린다. 처음 설치하면 발표 시나리오(춘천 대학가 국수집, 화요일 오후)다. 매장과 카드 28장 배치, 발표 순서는 `docs/demo_scenario.md`, 데이터는 `src/mocks/personas.ts`. "데모 한 주 할 일 28개 모두 홈에 모아 보기"를 켜면 28장을 한꺼번에 본다. Figma 바로 가기는 그 화면의 때를 그대로 만들려고 매장 시나리오를 끈다.
- `/dev` 에서 데모 주간 시각을 고르면 그 시각 기준으로 홈과 지금 할 일 화면이 바뀐다. 동작 실패, 인터넷 끊김, 느린 응답도 여기서 켠다. "처음부터 다시"는 이 기기 저장 값을 모두 지운다.
- 주 버튼에는 `testID="primary"`가 있어 웹 자동 검증에서 찾을 수 있다.
