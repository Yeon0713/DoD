# 도나 v0.2.0 (음성 앱)

사장님이 **말로 묻고 말로 듣는** 도나의 새 앱입니다. Figma `v0.2.0 : 음성처리` 확정안을 기준으로 프론트와 백엔드를 새로 만들었습니다. 기존 앱(`mobile/`, `frontend/`, `server/`)과는 폴더도 주소도 따로 씁니다.

| | 폴더 | 주소 | 기술 |
|---|---|---|---|
| 앱 | `app/` | http://localhost:8090 | Expo SDK 58 (React Native Web) |
| 백엔드 목업 | `server/` | http://localhost:8100 | FastAPI |

기존 앱이 쓰는 3000, 8000, 8082와 겹치지 않습니다.

## 켜는 법

백엔드를 먼저 켭니다.

```bash
cd donna-voice/server && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

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

1. 시작 → 로그인(아무 버튼이나) → 마이크 켜기.
2. 홈에서 "오늘 일정 브리핑해 줘"라고 말하거나, 그 말이 적힌 칩을 누릅니다.
3. 도나가 5단계로 브리핑합니다. 가만히 있으면 다음 단계로 넘어가고, "다시 말해 줘", "화면에 보여 줘", "그만"을 말할 수 있습니다.

마이크가 없는 환경에서는 칩을 눌러 씁니다. 개발 중에는 브라우저 콘솔에서 말을 대신 넣을 수 있습니다.

```js
__donna.say('오늘 일정 브리핑해 줘')
```

## 목업 데이터 바꾸기

백엔드는 에이전트 대신 고정 데이터로 답합니다. 아래로 상황을 바꿉니다.

| 하고 싶은 것 | 명령 |
|---|---|
| 처음 쓰는 날로 (허락을 아직 안 물음) | `curl -X POST localhost:8100/v1/dev/fixtures -H 'Content-Type: application/json' -d '{"scenario":"first_day"}'` |
| 허락한 다음 날로 (도나가 밤사이 답글을 닮) | `curl -X POST localhost:8100/v1/dev/fixtures -H 'Content-Type: application/json' -d '{"scenario":"next_day"}'` |
| 리뷰 한 건 넣기 | `curl -X POST localhost:8100/v1/dev/reviews -H 'Content-Type: application/json' -d '{"rating":1,"text":"너무 짜요"}'` |
| 시각 옮기기 | `curl -X POST localhost:8100/v1/dev/clock -H 'Content-Type: application/json' -d '{"now":"2026-11-17T14:00:00+09:00"}'` |
| 지금 저장된 것 보기 | `curl localhost:8100/v1/dev/state` |

API 문서는 http://localhost:8100/docs 에서 볼 수 있습니다.

## 폴더

```
app/src/
  app/               화면 (start, login, mic, (tabs)/index·calendar·sales·settings)
  components/        부품 (talk: 말풍선·도나 말·칩 / cards: 카드 여섯 가지 / dock: 도나·듣기 알약·메뉴바)
  lib/               api(서버), voice(듣기·읽기), conversation(대화 상태), layout(반응형), session(이 기기에 기억하는 것)
  theme/tokens.ts    색, 글자, 간격
server/app/
  main.py            API와 말 알아듣기(규칙)
  briefing.py        브리핑 5단계 만들기
  data.py            목업 데이터
docs/
  implementation-plan.md   구현 계획과 검토 기록
  open-features.md         아직 못 만든 것과 필요한 기능
```

계약(API 모양)은 [docs/v0.2.0-voice-agent-handoff.md](../docs/v0.2.0-voice-agent-handoff.md)에 있습니다.
