"""화면에 보낼 응답 예시(DoD/contracts/sample_responses/*.example.json)를 읽는다.

요청마다 파일을 새로 읽으므로 예시 파일을 고치면 서버를 다시 켜지 않아도 바로 반영된다.
파일 맨 위의 "_설명"처럼 _ 로 시작하는 항목은 사람이 읽는 설명이라 빼고 돌려준다.
배포할 때는 contracts/ 폴더도 server/ 옆에 함께 올려야 한다.
"""

import json
from pathlib import Path

# server/app/core/ 에서 세 단계 위가 저장소 맨 위(DoD/)
SAMPLE_RESPONSES_DIR = Path(__file__).resolve().parents[3] / "contracts" / "sample_responses"


def load_sample_response(name: str) -> dict:
    """name 예) "today" → today_response.example.json 내용"""
    path = SAMPLE_RESPONSES_DIR / f"{name}_response.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: value for key, value in data.items() if not key.startswith("_")}
