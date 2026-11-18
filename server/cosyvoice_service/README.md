# 도나 목소리 서비스 (CosyVoice 2)

음성 백엔드(`server/voice`, 8100)가 도나가 할 말을 이 서비스(8110)에 보내면, CosyVoice 2가 읽은 소리(wav)를 돌려줍니다.

- **왜 따로 도나요?** CosyVoice 2는 PyTorch, Python 3.10, 정해진 라이브러리 버전이 필요합니다. 서버 가상환경(`server/.venv`)에 섞으면 다른 기능이 깨질 수 있어서, conda 환경 `donna-cosyvoice`에서 따로 돕니다.
- **목소리**: CosyVoice 2에는 정해진 목소리가 없습니다. 짧은 본보기 녹음(`prompt/donna_prompt.wav`)을 듣고 그 목소리로 읽습니다. 본보기는 예전 도나 목소리(Qwen3-TTS Sohee + 도나 목소리 설계)로 만들었습니다(`make_prompt.py`).
- **속도 (M2 맥북 에어, CPU)**: 문장 길이의 약 3.5배입니다(6초 문장에 약 20초). 맥 GPU(MPS)로 옮겨 봤지만 빠르지 않았습니다. 그래서 음성 백엔드는 브리핑을 준비할 때 도나가 할 말을 **미리** 만들어 둡니다. 아직 못 만든 문장은 앱이 기기 목소리로 읽습니다.

## 처음 한 번: 설치 (10 ~ 30분, 약 7GB)

```bash
cd /Users/yeoheon/DoD/server/cosyvoice_service
bash setup_cosyvoice.sh
```
> 공식 코드(`vendor/CosyVoice`)를 받고, conda 환경 `donna-cosyvoice`(Python 3.10)를 만들고, 라이브러리와 모델(`pretrained_models/CosyVoice2-0.5B`, 4.5GB)을 받습니다. 받은 것은 GitHub에 올리지 않습니다(`.gitignore`).

```bash
cd /Users/yeoheon/DoD/server
.venv/bin/python cosyvoice_service/make_prompt.py
```
> 본보기 목소리(`prompt/donna_prompt.wav`, 약 6초)를 만듭니다. 서버 가상환경의 Qwen3-TTS로 한 문장을 읽습니다.

## 켤 때마다 (음성 백엔드보다 먼저)

```bash
cd /Users/yeoheon/DoD/server/cosyvoice_service
conda run -n donna-cosyvoice --no-capture-output python cosyvoice_server.py
```
> 도나 목소리 서비스를 http://127.0.0.1:8110 에서 켭니다. 터미널에 `CosyVoice 2 준비 끝`이 나오면 됩니다(10 ~ 20초).

확인: http://127.0.0.1:8110/health 에서 `"ready": true`

## 예전 목소리(Qwen3-TTS)로 되돌리기

음성 백엔드를 켤 때 `VOICE_TTS_ENGINE=qwen3`을 붙입니다.

```bash
cd /Users/yeoheon/DoD/server
VOICE_TTS_ENGINE=qwen3 .venv/bin/python -m voice.run_voice
```
> 이 서비스 없이 예전처럼 Qwen3-TTS(MLX, GPU)로 도나 목소리를 만듭니다. 만들어 둔 소리는 엔진마다 따로 저장돼서 섞이지 않습니다.
