# 도나 v0.2.1 (음성 앱 + 알바생 앱)

사장님이 **말로 묻고 말로 듣는** 도나의 새 앱입니다. Figma `v0.2.1 : 디자인개선`의 하루 시나리오(D-01 ~ D-33)와 알바생 앱(F-01 ~ F-09)을 기준으로 만들었습니다. 가게는 초옹장(s005)입니다. 기존 앱(`mobile/`, `frontend/`, `server/`)과는 폴더도 주소도 따로 씁니다.

| | 폴더 | 주소 | 기술 |
|---|---|---|---|
| 앱 | `app/` | http://localhost:8090 | Expo SDK 58 (React Native Web) |
| 백엔드 (하네스 에이전트) | `../server/voice/` | http://localhost:8100 | FastAPI + Harness + CLOVA, 도나 목소리 Qwen3-TTS |
| 백엔드 목업 (알바생·인스타용, 지금은 끔) | `server/` | http://localhost:8100 | FastAPI |

기존 앱이 쓰는 3000, 8000, 8082와 겹치지 않습니다. 실제 백엔드와 목업은 같은 8100을 쓰므로 하나만 켭니다.

**사장님 앱은 실제 백엔드(`server/voice`)에 붙어 있습니다.** 답글은 하네스 에이전트가 CLOVA로 쓰고, 도나는 Qwen3-TTS의 Sohee 목소리에 도나 목소리 설계(`docs/donna-voice-design.md`)를 얹어 말합니다. 인스타와 알바생 기능은 아직 실제 백엔드에 연결하지 않았습니다. 그 화면을 보려면 실제 백엔드 대신 목업을 켜야 합니다.

## 켜는 법

백엔드를 먼저 켭니다. 켤 때 초옹장 데이터를 넣고 시계를 11월 17일 아침 9시 2분으로 맞춘 뒤 브리핑을 준비합니다(답글을 CLOVA로 쓰느라 1 ~ 2분 걸립니다). 도나 목소리는 그다음부터 뒤에서 만들어 둡니다.

```bash
cd server && .venv/bin/pip install -r requirements.txt mlx-audio==0.6.5
```

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

## 써 보는 법

화면에는 추천 답변(칩)이 없습니다 (v0.2.1 확정 포맷). 말로만 씁니다. 마이크가 없는 환경에서는 브라우저 콘솔에서 말을 대신 넣습니다.

```js
__donna.say('도나야, 오늘 일정 브리핑해 줘')
```

1. 시작 → 로그인(아무 버튼이나) → 마이크 켜기.
2. 홈(D-07)에서 "도나야, 오늘 일정 브리핑해 줘". 일정 → 리뷰 → 바로 답해도 될지 → 좋은 리뷰 → 답글 예약 → 끝. (인스타에 올릴까요는 목업에서만)
3. "매출 어때", "이번 주 보여 줘", "내일 예약 있어?", "이번 주 비 와?"도 실제 백엔드에서 됩니다.
4. 목업에서만: 영업 중에는 "도나야, 감자전 반죽에 전분 한 숟갈 더 넣으라고 해 줘", "토요일 저녁 7시에 여덟 분 박 사장님 이름으로 예약 적어 줘", "시킨 거 다 했대?", "오늘 정리해 줘", "인스타 어때?", "내일 뭐 있어?", "방금 보낸 거 취소해 줘".
5. 목업에서만: 알바생 앱은 http://localhost:8090/staff 에서 엽니다. 초대 코드 `482017`(문하린) → 가입 → 할 일. 사장님이 말로 보낸 일이 5초 안에 올라옵니다.

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
