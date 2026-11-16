# 도나 목소리 설계

도나가 소리 내어 말할 때 쓰는 목소리입니다. 사장님 앱(`donna-voice/app`)은 이 목소리로 읽고, 만들어 두지 못한 문장만 기기 목소리로 읽습니다.

## 1. 어떤 사람의 목소리인가

| 무엇 | 정한 것 | 왜 |
|---|---|---|
| 누구 | 사장님 곁에서 몇 년째 가게를 같이 본 30대 초반 실장 | 사장님은 AI를 믿지 않습니다. 기계가 아니라 믿고 맡겨 온 사람처럼 들려야 합니다 |
| 말투 | 해요체. 차분하고 다정합니다. 들뜨거나 광고처럼 말하지 않습니다 | 아침 바쁜 시간에 짧게 알려 주는 말입니다. 꾸미는 말은 듣는 시간만 늘립니다 |
| 빠르기 | 보통보다 조금 느리게 | 디지털에 익숙하지 않은 사장님이 한 번에 알아듣게 합니다. 다시 묻게 하면 안 됩니다 |
| 숫자와 시각 | 또박또박 | "낮 열두 시", "열두 분"처럼 틀리면 안 되는 말이 가장 많습니다 |
| 높이 | 중간에서 조금 낮게. 날카롭지 않게 | 주방 소음 속에서도 편하게 들리고, 오래 들어도 피곤하지 않습니다 |
| 쉼 | 쉼표에서 짧게 쉽니다 | "저녁 예약은 두 팀이고, 오후 두 시부터 비 소식이 있어요"처럼 이어지는 말을 나눠 듣게 합니다 |
| 아쉬운 소식 | 담담하게. 겁주지 않습니다 | 아쉬운 리뷰는 도나가 이미 처리한 일입니다. 걱정을 키우지 않습니다 |

## 2. 만드는 방법

- 모델: Qwen3-TTS 1.7B CustomVoice (`mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit`). 이 컴퓨터(Apple Silicon)에서 MLX로 돌립니다. 키와 요금이 없고 문장이 밖으로 나가지 않습니다.
- 목소리: 미리 들어 있는 한국어 여성 목소리 **Sohee**
- 위 표를 모델에 주는 말투 지시(`instruct`)로 바꿔 함께 줍니다. 지시문은 `server/voice/tts.py`의 `INSTRUCT`에 있습니다. 영어로 썼습니다(이 모델은 영어·중국어 지시를 가장 잘 따릅니다).

```
A calm, warm Korean woman in her early thirties who has run this small restaurant with the owner for years,
giving him his morning briefing. Slightly slower than normal, unhurried pace with clear, crisp pronunciation,
especially for numbers and times. Gentle, polite and reassuring; friendly but never bubbly or salesy.
Steady mid-to-low pitch, short natural pauses at commas. A trusted colleague, not an announcer or a robot.
```

같은 문장을 지시 없이 읽으면 5.8초, 지시를 주면 7.1초가 걸렸습니다. 지시대로 조금 느리고 또박또박해졌습니다.

## 3. 숫자는 읽는 말로 바꿔서 줍니다

화면 글에는 아라비아 숫자를 씁니다(문서 12장). 모델에 그대로 주면 "12시"를 "십이 시"로 읽을 수 있어서, 소리를 만들기 전에 읽는 말로 바꿉니다 (`tts.spoken`).

| 화면 글 | 읽는 말 |
|---|---|
| 낮 12시에 단체 12명 | 낮 열두 시에 단체 열두 명 |
| 오전 10시 반 | 오전 열 시 반 |
| 30분 안에 | 삼십분 안에 |
| 128만 원 | 백이십팔만 원 |
| 11월 17일 | 십일월 십칠일 |

시각(시)과 사람·물건을 세는 말(명, 개, 팀, 번, 그릇)은 고유어로, 분·원·월·일은 한자어로 읽습니다.

## 4. 미리 만들어 둡니다

이 모델은 M1(메모리 8GB)에서 문장 길이의 약 3배 시간이 걸립니다. 말할 때마다 만들면 사장님이 기다려야 합니다. 그래서:

1. 브리핑을 준비할 때(문 열기 한 시간 전) 그날 도나가 할 말을 모두 만들어 `server/db/app_data/voice_tts/`에 둡니다. 한 번 만든 문장은 다시 만들지 않습니다.
2. 앱은 말하기 전에 `GET /v1/tts?text=`로 소리를 받습니다. 받는 데 1.5초를 넘기거나, 아직 만들지 않은 문장이면(서버가 204를 줌) 그 문장만 기기 목소리로 읽습니다. 서버는 그 문장을 맨 앞 차례로 만들어 둡니다.
3. 소리를 끈 사장님에게는 아무것도 받지 않습니다.

`GET /v1/tts/status`로 모델을 올렸는지, 만들 차례를 기다리는 문장이 몇 개인지 볼 수 있습니다.

## 5. 바꾸는 법

| 바꿀 것 | 환경 변수 |
|---|---|
| 끄기 (기기 목소리만) | `VOICE_TTS=false` |
| 목소리 | `VOICE_TTS_SPEAKER` (기본 `sohee`) |
| 말투 지시 | `VOICE_TTS_INSTRUCT` |
| 모델 | `VOICE_TTS_MODEL`. 0.6B 모델은 두 배쯤 빠르지만 말투 지시를 따르지 않습니다 |

설치: `server/.venv/bin/pip install mlx-audio==0.6.5`. 모델(약 3.1GB)은 처음 만들 때 Hugging Face에서 내려받습니다.

## 6. 아직 정하지 않은 것

- 휴대폰·태블릿 앱(설치형)에서는 같은 소리 파일을 받아 재생하면 됩니다. 재생 코드는 아직 웹만 있습니다 (`donna-voice/app/src/lib/voice.ts`).
- 서버를 클라우드에 올리면 MLX를 쓸 수 없습니다. 그때는 GPU 서버의 Qwen3-TTS나 Alibaba Cloud API로 바꿔야 합니다.
