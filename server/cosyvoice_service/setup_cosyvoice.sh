#!/bin/bash
# CosyVoice 2 (도나 목소리) 설치. 서버 가상환경(server/.venv)과 섞이지 않게 conda 환경 donna-cosyvoice 를 따로 만든다.
# 처음 한 번만: cd server/cosyvoice_service && bash setup_cosyvoice.sh   (10 ~ 30분, 모델과 라이브러리 수 GB)
#   1. 공식 코드 받기          vendor/CosyVoice (+ Matcha-TTS)
#   2. conda 환경 만들기       donna-cosyvoice (Python 3.10, 공식 권장)
#   3. 라이브러리 설치         공식 requirements.txt 에서 맥에 필요 없는 GPU·웹 데모 묶음은 뺐다
#   4. 모델 받기              pretrained_models/CosyVoice2-0.5B (Hugging Face FunAudioLLM/CosyVoice2-0.5B)
set -e
cd "$(dirname "$0")"
ENV=donna-cosyvoice
CONDA=${CONDA_EXE:-$(command -v conda || echo /opt/anaconda3/bin/conda)}

if [ ! -d vendor/CosyVoice ]; then
  git clone --recursive --depth 1 https://github.com/FunAudioLLM/CosyVoice.git vendor/CosyVoice
fi

if ! "$CONDA" env list | grep -q "^$ENV "; then
  "$CONDA" create -n "$ENV" -y python=3.10
fi
PY="$("$CONDA" run -n "$ENV" python -c 'import sys; print(sys.executable)')"
echo "[setup] python: $PY"

"$PY" -m pip install --upgrade pip
# openai-whisper==20231117 은 빌드할 때 pkg_resources 가 있어야 한다 (새 setuptools 에는 없다). 옛 setuptools 로 따로 먼저 설치한다
"$PY" -m pip install "setuptools<70" wheel
"$PY" -m pip install --no-build-isolation openai-whisper==20231117
# 공식 requirements.txt (2026-11 기준) 중 맥 추론에 필요한 것. 빠진 것: deepspeed·tensorrt·onnxruntime-gpu (리눅스 GPU),
# gradio·tensorboard·grpcio·fastapi-cli (웹 데모·학습). 버전은 공식과 같게 맞춘다.
"$PY" -m pip install \
  torch==2.3.1 torchaudio==2.3.1 numpy==1.26.4 \
  conformer==0.3.2 diffusers==0.29.0 hydra-core==1.3.2 HyperPyYAML==1.2.3 inflect==7.3.1 librosa==0.10.2 \
  lightning==2.2.4 matplotlib==3.7.5 modelscope==1.20.0 networkx==3.1 omegaconf==2.3.0 onnx==1.16.0 onnxruntime==1.18.0 \
  openai-whisper==20231117 protobuf==4.25 pyarrow==18.1.0 pydantic==2.7.0 pyworld==0.3.4 rich==13.7.1 soundfile==0.12.1 \
  transformers==4.51.3 x-transformers==2.11.24 wetext==0.0.4 gdown==5.1.0 wget==3.2 \
  fastapi==0.115.6 uvicorn==0.30.0 huggingface_hub

# 위 설치가 setuptools 를 새 버전으로 올리면 pkg_resources 가 사라진다 (CosyVoice 가 모델을 읽을 때 쓴다). 다시 옛 버전으로
"$PY" -m pip install "setuptools<70"

if [ ! -f pretrained_models/CosyVoice2-0.5B/cosyvoice2.yaml ]; then
  "$PY" -c "from huggingface_hub import snapshot_download; snapshot_download('FunAudioLLM/CosyVoice2-0.5B', local_dir='pretrained_models/CosyVoice2-0.5B')"
fi
echo "[setup] 끝. 켜기: $CONDA run -n $ENV --no-capture-output python cosyvoice_server.py"
