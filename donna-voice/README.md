# 도나 v0.2.1 (음성 앱 + 알바생 앱)

사장님이 **말로 묻고 말로 듣는** 도나의 새 앱입니다. Figma `v0.2.1 : 디자인개선`의 하루 시나리오(D-01 ~ D-33)와 알바생 앱(F-01 ~ F-09)을 기준으로 만들었습니다. 가게는 초옹장(s005)입니다. 기존 앱(`mobile/`, `frontend/`, `server/`)과는 폴더도 주소도 따로 씁니다.

| | 폴더 | 주소 | 기술 |
|---|---|---|---|
| 앱 | `app/` | http://localhost:8090 | Expo SDK 58 (React Native Web) |
| 백엔드 (하네스 에이전트) | `../server/voice/` | http://localhost:8100 | FastAPI + Harness + CLOVA, 받아 적기 Faster-Whisper large-v3-turbo + Silero VAD |
| 도나 목소리 (CosyVoice 2) | `../server/cosyvoice_service/` | http://127.0.0.1:8110 | conda 환경 `donna-cosyvoice` (설치는 그 폴더 README) |
| 백엔드 목업 (알바생·인스타용, 지금은 끔) | `server/` | http://localhost:8100 | FastAPI |

기존 앱이 쓰는 3000, 8000, 8082와 겹치지 않습니다. 실제 백엔드와 목업은 같은 8100을 쓰므로 하나만 켭니다.

**사장님 앱은 실제 백엔드(`server/voice`)에 붙어 있습니다.** 답글은 하네스 에이전트가 CLOVA로 쓰고, 도나는 CosyVoice 2로 말합니다 (본보기 목소리는 예전 Qwen3-TTS Sohee + 도나 목소리 설계, `docs/donna-voice-design.md`). **알바생 기능도 실제 백엔드에 연결했습니다 (2026-11-18)**: 말로 초대(랜덤 6자리 코드)·시키기·다 했대?·취소·내보내기, 알바생 가입·로그인. 인스타 기능은 아직 실제 백엔드에 연결하지 않아 목업을 켜야 보입니다.

## 켜는 법

도나 목소리 서비스 → 백엔드 → 앱 순서로 켭니다. 백엔드는 켤 때 초옹장 데이터를 넣고 시계를 11월 17일 아침 9시 2분으로 맞춘 뒤 브리핑을 준비합니다. **밤사이 준비 결과 저장본**(`server/voice/fixtures/s005_choongjang.prepared.json`)을 그대로 넣으므로 켜자마자, 또 "처음부터"를 누르자마자 바로 브리핑할 수 있습니다. 시나리오 파일이나 답글 프롬프트를 고치면 `cd server && .venv/bin/python -m voice.prepared_snapshot s005_choongjang`로 저장본을 다시 만듭니다(CLOVA, 3 ~ 4분). 도나 목소리는 그다음부터 뒤에서 만들어 둡니다.

**듣기와 말하기 (2026-11-18)**
- 받아 적기(STT): 앱이 마이크 소리를 백엔드로 보내고, 백엔드가 Silero VAD로 말소리 구간을 잘라 Faster-Whisper large-v3-turbo로 받아 적습니다(맥 GPU, 말이 끝나고 약 3초). 백엔드 받아 적기를 못 쓰면 앱이 브라우저 음성 인식으로 듣습니다. 처음 켤 때 Whisper 모델(약 1.6GB)을 받습니다.
- 도나 목소리(TTS): CosyVoice 2가 본보기 목소리로 읽습니다. 서비스가 꺼져 있으면 앱이 기기 목소리로 읽습니다. 예전 Qwen3-TTS로 돌리려면 `VOICE_TTS_ENGINE=qwen3`.

처음 한 번 (라이브러리):

```bash
cd server && .venv/bin/pip install -r requirements.txt mlx-audio==0.6.5
```

도나 목소리 서비스 (처음 한 번 설치는 `server/cosyvoice_service/README.md`):

```bash
cd server/cosyvoice_service && conda run -n donna-cosyvoice --no-capture-output python cosyvoice_server.py
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

## 써 보는 법

화면에는 추천 답변(칩)이 없습니다 (v0.2.1 확정 포맷). 말로만 씁니다. 마이크가 없는 환경에서는 브라우저 콘솔에서 말을 대신 넣습니다.

```js
__donna.say('도나야, 오늘 일정 브리핑해 줘')
```

1. 시작 → 로그인(아무 버튼이나) → 마이크 켜기.
2. 홈(D-07)에서 "도나야, 오늘 일정 브리핑해 줘". 일정 → 리뷰 → 바로 답해도 될지 → 좋은 리뷰 → 답글 예약 → 끝. (인스타에 올릴까요는 목업에서만)
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
