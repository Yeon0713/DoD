# 도나 프론트엔드

사장님용 모바일 웹(375px 기준). 화면은 Figma `DONNA-UX-UI` 파일의 `04 · DONNA 쉬운 시안 v4`를 따르고, 만드는 순서는 [`docs/frontend_plan_v4.md`](../docs/frontend_plan_v4.md)를 따른다.

## 켜기

```bash
npm install
npm run dev
```

`http://localhost:3000`을 열면 **오늘 화면**이 나온다. 기본은 **고정 샘플 모드**라 서버 없이도 화면이 나온다. 샘플은 `contracts/sample_responses/`의 예시 파일을 그대로 읽는다.

**Figma 04 화면을 하나씩 보려면 `http://localhost:3000/dev`** 를 연다. "Figma 04 화면 바로 가기"에서 화면 번호(04-1 ~ 04-66)를 누르면 그 화면에 맞는 시각과 상태로 열린다.

## 바꿀 수 있는 값

| 값 | 기본 | 뜻 |
|---|---|---|
| `NEXT_PUBLIC_USE_MOCK` | `true` | `false`면 실제 서버(`NEXT_PUBLIC_API_BASE_URL`)를 부른다 |
| `NEXT_PUBLIC_API_BASE_URL` | `http://127.0.0.1:8000` | 서버 주소 |
| `NEXT_PUBLIC_MOCK_DELAY_MS` | `600` | 고정 샘플을 일부러 늦추는 시간 |

고정 샘플 모드에서는 주소 뒤에 값을 붙여 화면을 바꿔 볼 수 있다.

- `?now=2026-11-17T14:05` : 지금 시각 (기본은 데모 주간 화요일 오후 2시 5분)
- `?delay=4000` : 불러오기를 4초 늦춰서 3초 안내(04-8c)를 본다. `12000`이면 10초 넘음(04-8d)
- `?fail=1` : 답글 올리기 같은 동작을 일부러 실패시켜 못 올렸을 때(04-5f)를 본다
- `?offline=1` : 인터넷이 끊긴 화면(04-9, 04-7E), `?fresh=1` : 저장해 둔 카드 없이 처음처럼 불러오기
- `?card=카드id` : 오늘 화면에서 그 카드를 맨 앞으로, `?sheet=later` : "나중에" 시트(04-22)를 연 채로
- `/week?day=2026-11-19`, `/start/store?q=가게이름`, `/reply/...?view=failed`, `/menu-order/...?view=applying|done|reverted`, `/naver/connect?view=done`, `/poster/...?step=making|preview|edit|share|sent`

**개발용 시뮬레이터 `/dev`** 에서 가상 시각(11/16 ~ 11/25, 하루 3번), 답글 시각 규칙(시안 규칙, 지금 서버 규칙), 네이버 연결 상태, 알림 꺼 둠, 불러오기 늦추기를 바꾸고, 카드 기록을 지우고, 브라우저 알림을 띄워 볼 수 있다. 데모 주간 알림 타임라인도 여기서 본다.

## 화면 주소 (Figma 04 시안)

| 주소 | Figma |
|---|---|
| `/start`, `/start/store`, `/start/notify-time`, `/start/notify-on` | 04-1, 04-2(04-2b), 04-3, 04-3b |
| `/` | 오늘: 카드 전부, 04-4n, 04-4f, 04-6, 04-8 계열, 04-9, 04-22, 04-43, 04-44 |
| `/reply/[planId]`, `/reply/[planId]/edit` | 04-5, 04-5f, 04-11r, 04-35r, 04-39r, 04-21 |
| `/reply/batch/[planId]` (`?one=0`) | 04-25, 04-25b |
| `/check/[planId]` | 04-24 |
| `/week`, `/week/[refId]` | 04-7 계열, 04-18, 04-18b |
| `/settings`, `/settings/notify-time`, `/settings/busy`, `/settings/naver` | 04-19, 04-19b, 04-20, 04-58 |
| `/naver/connect`, `/menu-order/[planId]` | 04-51, 04-52, 04-53 ~ 04-57 |
| `/poster/[planId]` (`?step=share`) | 04-61 ~ 04-66 |
| `/start/hours`, `/start/hours/confirm`, `/settings/hours` | 05-2h, 05-2i, 05-19h 장사 시간 (알림 시간이 장사 시간을 따라감) |
| `/sales`, `/sales/week`, `/sales/menu`, `/sales/time`, `/sales/channel`, `/sales/month` | 05-70 ~ 05-75 매출 |
| `/lock` | 04-23 잠금 화면에서 시작 |
| `/dev` | 개발용 시뮬레이터 |

서버에 아직 없는 기능(답글 초안과 올리기, 네이버 메뉴 순서, 포스터, 결과 알림)은 `src/mocks/extras.ts`와 `src/lib/actions.ts`의 목업으로 동작한다. 서버 API가 생기면 `actions.ts` 안만 바꾼다. 매출 대시보드(`/sales`)는 `server/db/mock/out`의 주문 목업을 계산해서 보여 준다. 무엇이 목업이고 서버에 무엇이 필요한지는 [`docs/frontend_mock_and_api_needs.md`](../docs/frontend_mock_and_api_needs.md)에 정리했다.

## 폴더

```text
src/
├── app/                  주소별 화면. mock-api/는 고정 샘플을 돌려주는 길
├── components/
│   ├── icons/Icon.tsx    Figma icon/* 36개
│   ├── ui/               버튼, 상태 알약, 진행 막대, 아래 탭, 시트, 뼈대, 띠 알림
│   ├── today/            오늘 화면과 할 일 카드
│   ├── reply/            답글 보기, 고쳐 쓰기, 좋은 리뷰 묶음, 점검 목록
│   ├── week/             이번 주, 바쁜 날 자세히
│   ├── start/            처음 쓰는 날
│   ├── settings/         설정
│   ├── naver/            네이버 연결, 메뉴 순서
│   ├── poster/           인스타 포스터
│   └── dev/              개발용 시뮬레이터
├── lib/
│   ├── api.ts            데이터 조회는 이곳에서만
│   ├── queue.ts          오늘 카드 줄 세우기 (우선순위, 기본 답글 묶기)
│   ├── cards.ts          서버 값 → 카드 문구 (Figma 문구 그대로)
│   ├── cardState.ts      다 했어요, 나중에 기록 (서버 API 전까지 이 기기에만)
│   ├── localStore.ts     처음 쓰는 날, 네이버 연결, 고쳐 쓴 답글, 띠 알림
│   ├── actions.ts        서버에 없는 동작의 목업 (답글 올리기, 메뉴 순서, 포스터)
│   └── time.ts, labels.ts
├── mocks/extras.ts       서버에 없는 값의 목업 (답글 초안, 점검 목록, 메뉴, 결과 알림)
└── types/contract.ts     서버 응답 모양
public/donna/             Figma에서 내보낸 도나 그림
```
