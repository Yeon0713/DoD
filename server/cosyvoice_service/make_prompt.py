"""CosyVoice 2 가 따라 할 도나 목소리 본보기를 만든다 (prompt/donna_prompt.wav, prompt/donna_prompt.txt).

지금까지 쓰던 Qwen3-TTS 의 Sohee 목소리 + 도나 목소리 설계(server/voice/tts.py INSTRUCT)로 한 문장을 읽게 해서 녹음으로 쓴다.
서버 가상환경에서 한 번만 (mlx-audio 가 거기 있다):
    cd server && .venv/bin/python cosyvoice_service/make_prompt.py
다른 사람 목소리를 쓰고 싶으면 3 ~ 10초짜리 wav 와 그 글을 같은 이름으로 넣으면 된다 (본인 동의를 받은 녹음만).
"""

import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

TEXT = "안녕하세요, 사장님. 오늘 일정이랑 밤사이 들어온 리뷰를 차례대로 알려 드릴게요."
QWEN_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit"


def main() -> None:
    from mlx_audio.tts.utils import load_model

    from voice import tts

    model = load_model(QWEN_MODEL)
    results = list(model.generate(text=TEXT, voice="sohee", instruct=tts.INSTRUCT, lang_code="korean"))
    audio = np.concatenate([np.array(r.audio, dtype=np.float32).reshape(-1) for r in results])
    out_dir = HERE / "prompt"
    out_dir.mkdir(exist_ok=True)
    with wave.open(str(out_dir / "donna_prompt.wav"), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(model.sample_rate)
        out.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    (out_dir / "donna_prompt.txt").write_text(TEXT, encoding="utf-8")
    print(f"본보기 목소리: {out_dir / 'donna_prompt.wav'} ({len(audio) / model.sample_rate:.1f}초)")


if __name__ == "__main__":
    main()
