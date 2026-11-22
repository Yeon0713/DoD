# 도나 v0.2.1 (음성 앱 + 알바생 앱)

사장님이 **말로 묻고 말로 듣는** 도나의 새 앱입니다. Figma `v0.2.1 : 디자인개선`의 하루 시나리오(D-01 ~ D-33)와 알바생 앱(F-01 ~ F-09)을 기준으로 만들었습니다. 가게는 초옹장(s005)입니다. 기존 앱(`mobile/`, `frontend/`, `server/`)과는 폴더도 주소도 따로 씁니다.

| | 폴더 | 주소 | 기술 |
|---|---|---|---|
| 앱 | `app/` | http://localhost:8090 | Expo SDK 58 (React Native Web) |
| 백엔드 (하네스 에이전트) | `../server/voice/` | http://localhost:8100 | FastAPI + Harness + CLOVA X, 받아 적기 CLOVA Speech("도나야" 부스팅), 목소리 CLOVA Voice |
| 백엔드 목업 (알바생·인스타용, 지금은 끔) | `server/` | http://localhost:8100 | FastAPI |

기존 앱이 쓰는 3000, 8000, 8082와 겹치지 않습니다. 실제 백엔드와 목업은 같은 8100을 쓰므로 하나만 켭니다.

**사장님 앱은 실제 백엔드(`server/voice`)에 붙어 있습니다.** 답글은 하네스 에이전트가 CLOVA로 쓰고, 도나는 CLOVA Voice(아라 Pro, `vara`)로 말합니다. **알바생 기능도 실제 백엔드에 연결했습니다 (2026-11-18)**: 말로 초대(랜덤 6자리 코드)·시키기·다 했대?·취소·내보내기, 알바생 가입·로그인. 인스타 기능은 아직 실제 백엔드에 연결하지 않아 목업을 켜야 보입니다.

## 켜는 법

백엔드 → 앱 순서로 켭니다. 백엔드는 켤 때 초옹장 데이터를 넣고 시계를 11월 17일 아침 9시 2분으로 맞춘 뒤 브리핑을 준비합니다. **밤사이 준비 결과 저장본**(`server/voice/fixtures/s005_choongjang.prepared.json`)을 그대로 넣으므로 켜자마자, 또 "처음부터"를 누르자마자 바로 브리핑할 수 있습니다. 시나리오 파일이나 답글 프롬프트를 고치면 `cd server && .venv/bin/python -m voice.prepared_snapshot s005_choongjang`로 저장본을 다시 만듭니다(CLOVA, 3 ~ 4분).

**듣기와 말하기 (네이버 클라우드, 2026-11-19)**
- 받아 적기(STT): 앱이 마이크 소리를 백엔드로 보내고, 백엔드가 webrtcvad로 말소리 구간을 잘라 네이버로 받아 적습니다. `server/.env`의 `VOICE_STT=true`일 때만 쓰고, 아니면 앱이 브라우저 음성 인식으로 듣습니다.
  - `CLOVA_SPEECH_SECRET_KEY`가 있으면 **CLOVA Speech 단문 인식 + 키워드 부스팅**(`VOICE_STT_BOOSTINGS`, 기본 `도나야`)으로 받아 적습니다. 키는 콘솔 > CLOVA Speech > 도메인(단문 인식) > 빌더 실행 > 설정 > 연동 정보의 Secret Key입니다.
  - 없으면 CSR(CLOVA Speech Recognition)로 받아 적습니다. CSR은 호출어 "도나야"를 "누나야", "도나헤어"로 적어서 앱이 부르지 않은 말로 버리는 일이 많습니다.
- 도나 목소리(TTS): CLOVA Voice Premium(`vara`)으로 그때그때 만듭니다. 소리를 못 받으면 화면에 다시 듣기 버튼이 나옵니다.
- 둘 다 `server/.env`의 `CLOVA_VOICE_CLIENT_ID` / `CLOVA_VOICE_CLIENT_SECRET`이 필요합니다(AI·NAVER API Application에서 CSR과 CLOVA Voice에 체크).

처음 한 번 (라이브러리):

```bash
cd server && .venv/bin/pip install -r requirements.txt
```

백엔드:

```bash
cd server && .venv/bin/python -m voice.run_voice
```

처음부터 다시 하려면(허락을 아직 안 물은 아침으로):

```bash
curl -X POST localhost:8100/v1/dev/fixtures -H 'Content-Type: application/json' -d '{"fixture":"s005_choongjang"}'
```

목업을 켜려면(알바생·인스타 화면) 실제 백엔드를 끄고:

```bash
cd donna-voice/server && .venv/bin/python run_dev.py
```

그다음 앱을 켭니다.

```bash
cd donna-voice/app && npm install
```

```bash
cd donna-voice/app && npm run web
```

브라우저에서 http://localhost:8090 을 엽니다. 휴대폰 비율(375 × 812)과 태블릿 비율(768 × 1024, 1024 × 768)에서 모두 쓸 수 있습니다.

## 인스타 연결

실제 OAuth 전이라 `server/.env` 의 토큰으로 시연 가게 하나만 잇습니다 (Instagram API with Facebook Login).

1. Meta 쪽 준비: IG **비즈니스** 계정을 Facebook 페이지에 연결하고, Meta 앱(Business 유형)에 Facebook Login 과 Instagram 을 더한 뒤, Graph API Explorer 에서 `instagram_basic`, `instagram_content_publish`, `pages_read_engagement` 권한으로 페이지 토큰을 받아 장기 토큰으로 바꿉니다. IG 계정 id 는 `GET /me/accounts?fields=instagram_business_account` 로 봅니다.
2. `server/.env` 에 `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_USER_ID` 를 넣습니다.
3. 인스타 서버가 사진(JPEG)을 공개 주소에서 직접 가져가므로 둘 중 하나를 고릅니다.
   - `MEDIA_HOST=base_url` (기본): `ngrok http 8100` 으로 연 주소를 `PUBLIC_MEDIA_BASE_URL` 에 넣습니다. 사진은 `/media/...` 로 나갑니다. **이 방법은 백엔드 전체(`/v1/dev/*` 포함)가 인터넷에 열리므로 시험할 때만 씁니다.**
   - `MEDIA_HOST=object_storage`: `NCP_OBJECT_STORAGE_BUCKET` 에 버킷 이름을 넣습니다 (키는 `NCLOUD_ACCESS_KEY` / `NCLOUD_SECRET_KEY`, `pip install boto3`).
4. 백엔드를 켜고 앱의 인스타 허용 화면에서 "허용"을 누르거나 `curl -X POST localhost:8100/v1/instagram/connect -H 'Content-Type: application/json' -d '{}'` 를 부릅니다.

API: `GET /v1/instagram?store_id=s005` (연결, 남은 게시 한도, 최근 게시물), `POST /v1/instagram/posts` (`{"store_id":"s005","kind":"feed"|"story","post_at":null}`), `GET /v1/instagram/posts/{id}`. 올리는 건 작업 큐가 뒤에서 하고, 끝나면 도나 알림(`/v1/notices`)이 옵니다. 사진은 지금 메뉴 사진을 비율(피드 4:5, 스토리 9:16)에 맞춰 여백을 채운 것뿐입니다 (디자인은 `server/voice/instagram/media.py` 의 `prepare`).

## 시연 영상 (Figma H · 오늘 일정 브리핑)

Figma `v0.2.1 : 디자인개선` 섹션 **H "새 오늘 일정 브리핑 (요약 → 허락 → 상세)"** 와 같은 화면이 나오는 시연 데이터가 따로 있습니다 (`server/voice/fixtures/s005_choongjang_h.json`, 저장본 `s005_choongjang_h.prepared.json`). 기본 초옹장 데이터(`s005_choongjang`, 인사과·결재 시연)는 그대로입니다.

```bash
curl -X POST localhost:8100/v1/dev/fixtures -H 'Content-Type: application/json' -d '{"fixture":"s005_choongjang_h"}'
```

| 사장님이 하는 말 | 화면 (Figma) |
|---|---|
| (부르기 전) | H-01 홈 · 오늘 비, 예약 3팀 / 밤사이 리뷰 5건 / 비 오는 날 이벤트 / 3시 손님 요청사항 |
| "도나야, 오늘 일정 브리핑해 줘" | H-02 ~ H-04 요약 세 줄 (가만히 있으면 넘어감) → H-05 "상세 브리핑을 시작할까요?" |
| "응, 그렇게 해" | H-06 "비 오는 날 이벤트를 올릴까요?" (사장님이 준 그림 `server/voice/static/events/s005-rain-event.jpg`) |
| "응, 올려 줘" | H-07 스토리에 올렸어요 → H-08 리뷰 5건 → H-09 토요일 오전 11시 예약 → H-10 12분 만에 답했어요 → H-11 "알바생 할 일에 넣을까요?" |
| "응, 넣어 줘" | H-12 알바생 할 일에 넣었어요 → H-12b 오늘 브리핑은 여기까지예요 |
| (끝 화면 4초 뒤, 자동) | 시계가 밤 9시로 넘어가고 인사과 보고 K-01 "스토리는 먼저 올리고 저녁에 보고할까요?" (인스타 관리 · 사원 → 대리, 최근 20건 중 19건 그대로 승인, 사후 취소 0번) |
| "그래, 그렇게 해" | K-02 대리가 됐어요 |

**J 시연 (Figma J '영상 v15')**: 아쉬운 리뷰를 여쭤보고 올리는 판입니다. H와 같고 H-10 대신 J-10a, J-10b가 나옵니다.

```bash
curl -X POST localhost:8100/v1/dev/fixtures -H 'Content-Type: application/json' -d '{"fixture":"s005_choongjang_j"}'
```

| 사장님이 하는 말 | 화면 (Figma) |
|---|---|
| (H-09 뒤) | J-10a "사과 답변을 올릴까요?" (부정 리뷰는 꼭 여쭤보고 올려요, 초안에 서비스 문장) |
| "서비스 준다는 말은 빼고 올려" | J-10b "빼고 올렸어요" (뺀 문장은 줄을 그어 보임) + 인사과에 기록함 · 위기 대처 "사과할 때 서비스 준다는 말은 하지 않기" |
| "응, 넣어 줘" → (자동) → "그래, 그렇게 해" | H-11, H-12 → J-12b ("9:06에 고쳐서 올렸어요") → 밤 9시 K-01 → K-02 |

- "응, 올려 줘"는 **실제 인스타 스토리에 올립니다** (`server/.env`의 인스타 토큰, 위 "인스타 연결"의 사진 공개 주소 필요). 시험만 할 때는 토큰을 비우고 켭니다: `INSTAGRAM_ACCESS_TOKEN= INSTAGRAM_USER_ID= .venv/bin/python -m voice.run_voice`
- 시연 시계는 9시 2분에 멈춰 있어서 끝 화면의 시각("9:02에 …")은 모두 같습니다. 밤 9시 장면은 시계를 멈춘 시연 가게에서만 끝 화면 뒤에 저절로 넘어갑니다. 실제 가게는 밤 9시에 알림으로 옵니다 (`server/voice/jobs/hr_night.py`).
- 시나리오 파일을 고치면 저장본을 다시 만듭니다: `cd server && .venv/bin/python -m voice.prepared_snapshot s005_choongjang_h` (J는 `s005_choongjang_j`). 브리핑 순서·문구만 고친 경우는 다시 만들 필요가 없습니다 (불러올 때 지금 코드로 단계를 다시 짭니다, `jobs/briefing.assemble`).

## 써 보는 법

화면에는 추천 답변(칩)이 없습니다 (v0.2.1 확정 포맷). 말로만 씁니다. 마이크가 없는 환경에서는 브라우저 콘솔에서 말을 대신 넣습니다.

```js
__donna.say('도나야, 오늘 일정 브리핑해 줘')
```

1. 시작 → 로그인(아무 버튼이나) → 마이크 켜기.
2. 홈(H-01)에서 "도나야, 오늘 일정 브리핑해 줘". 요약 세 줄(비 → 도착한 리뷰 → 예약) → "상세 브리핑을 시작할까요?" → 인스타(비 오는 날 이벤트 스토리, 없으면 인기 메뉴 피드. 인스타를 연결했을 때만. "화면에 보여 줘", "다음 사진", "올려", "나중에") → 리뷰(도착한 수, 예약한 좋은 리뷰 답글, 바로 단 사과 답글. 직급이 묻는 업무면 여기서 묻는다) → 알바생 할 일 → 끝(오늘 아침에 한 것). 브리핑 밖에서는 "도나야, 인스타 스토리 올려 줘".
3. "매출 어때", "이번 주 보여 줘", "내일 예약 있어?", "이번 주 비 와?"도 실제 백엔드에서 됩니다.
4. 알바생 (실제 백엔드, `server/voice/staff_orders.py`): "도나야, 하린이 초대해 줘" → "카카오톡으로 보내 줘" → 알바생이 링크·코드로 가입하면 "하린 씨가 들어왔어요". 그 뒤 "도나야, 하린이한테 감자전 반죽에 전분 한 숟갈 더 넣으라고 해" → "응" (5초 안에 알바생 화면에), "오늘은 장칼국수 주문 받지 말라고 해", "시킨 거 다 했대?", "그거 취소해", "알바생 누구 있어?", "오늘 누구 나왔어?", "알바생 매뉴얼 보여 줘", "정우 내보내 줘".
5. 알바생 앱은 http://localhost:8090/staff 에서 엽니다. 사장님이 만든 초대 코드 → 이름·아이디·비밀번호로 가입 → 할 일. 다른 기기에서는 "이미 가입했어요"로 아이디·비밀번호를 넣고 들어옵니다. 시연 화면(`/demo`)의 알바생 휴대폰은 예시 메신저(`/demo-messenger`, Figma F-01)에서 시작하고, 개발자 모드(`/dev`)의 "알바생" 묶음에 위 말들이 버튼으로 있습니다. 연습할 때는 "하린 바로 가입"으로 초대를 건너뜁니다.
6. 목업에서만: "토요일 저녁 7시에 여덟 분 박 사장님 이름으로 예약 적어 줘", "오늘 정리해 줘", "인스타 어때?", "내일 뭐 있어?".

## 목업 데이터 바꾸기

백엔드는 에이전트 대신 고정 데이터로 답합니다. 아래로 상황을 바꿉니다.

| 하고 싶은 것 | 명령 |
|---|---|
| 처음 한 번 하는 날로 (인스타 연결 전, D-01 ~ D-06) | `curl -X POST localhost:8100/v1/dev/fixtures -H 'Content-Type: application/json' -d '{"scenario":"setup"}'` |
| 설정을 마친 다음 날 아침으로 (허락을 아직 안 물음) | `curl -X POST localhost:8100/v1/dev/fixtures -H 'Content-Type: application/json' -d '{"scenario":"first_day"}'` |
| 허락한 다음 날로 (도나가 밤사이 답글을 닮) | `curl -X POST localhost:8100/v1/dev/fixtures -H 'Content-Type: application/json' -d '{"scenario":"next_day"}'` |
| 리뷰 한 건 넣기 | `curl -X POST localhost:8100/v1/dev/reviews -H 'Content-Type: application/json' -d '{"rating":1,"text":"너무 짜요"}'` |
| 손님이 스토리에 태그함 (D-21, 알바생에게 서비스 할 일) | `curl -X POST localhost:8100/v1/dev/story -H 'Content-Type: application/json' -d '{}'` |
| 확인 필요를 안 누른 사람 알림 (D-23) | `curl -X POST localhost:8100/v1/dev/unconfirmed -H 'Content-Type: application/json' -d '{}'` |
| 시각 옮기기 | `curl -X POST localhost:8100/v1/dev/clock -H 'Content-Type: application/json' -d '{"now":"2026-11-17T14:00:00+09:00"}'` |
| 지금 저장된 것 보기 | `curl localhost:8100/v1/dev/state` |

API 문서는 http://localhost:8100/docs 에서 볼 수 있습니다.

## 폴더

```
app/src/
  app/               화면 (start, login, mic, instagram, (tabs)/index·calendar·sales·settings, staff/ 알바생 앱)
  components/        부품 (talk: 말풍선·도나 말 / cards: 카드 / dock: 머리·가게 상태 줄·도나·듣기 알약·메뉴바 / staff: 알바생 앱)
  lib/               api(서버), voice(듣기·읽기), conversation(대화 상태), layout(반응형), session(이 기기에 기억하는 것)
  theme/tokens.ts    색, 글자, 간격
server/app/
  main.py            API와 말 알아듣기(규칙)
  briefing.py        브리핑 단계 만들기 (일정, 리뷰, 좋은 리뷰, 인스타)
  requests.py        브리핑 밖의 말 (알바생에게 시키기, 예약, 매뉴얼, 인스타, 처음 설정)
  staff.py           알바생 앱 API (/v1/staff/*)
  data.py            목업 데이터 (초옹장)
server/static/       가게 로고와 메뉴 사진
docs/
  implementation-plan.md   구현 계획과 검토 기록
  open-features.md         아직 못 만든 것과 필요한 기능
```

계약(API 모양)은 [docs/v0.2.0-voice-agent-handoff.md](../docs/v0.2.0-voice-agent-handoff.md)에 있습니다.
