"""음성 백엔드 켜기. server/ 폴더에서 가상환경을 켠 뒤:

    python -m voice.run_voice

주소는 http://127.0.0.1:8100 (VOICE_PORT 로 바꿀 수 있다). 기존 서버(run_dev.py, :8000)와 따로 돈다.
켜기 전에 포트를 이미 쓰는 프로그램이 있는지 본다 (run_dev.py 와 같은 확인).
"""

import sys

import uvicorn

from run_dev import HOST, port_in_use
from voice import config


def main() -> None:
    if port_in_use(config.PORT):
        sys.exit(f"{config.PORT}번 포트를 이미 쓰고 있어요. 예전에 켠 음성 백엔드를 끄거나 VOICE_PORT 로 다른 포트를 정하세요.")
    print(f"음성 백엔드: http://{HOST}:{config.PORT}  (API 문서 http://{HOST}:{config.PORT}/docs)")
    uvicorn.run("voice.main:app", host=HOST, port=config.PORT)


if __name__ == "__main__":
    main()
