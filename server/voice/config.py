"""음성 백엔드 설정. 문서 14장의 정해지지 않은 값도 여기 모아 둔다 (임시로 정한 값)."""

import datetime as dt
import os
from pathlib import Path

from Harness import clova_tools

DB_PATH = Path(os.environ.get("VOICE_DB_PATH", Path(__file__).resolve().parents[1] / "db" / "app_data" / "voice.db"))
PORT = int(os.environ.get("VOICE_PORT", "8100"))

GROUP_MIN_PEOPLE = 8  # 몇 명부터 단체 예약인가 (14장 8번 제안)
PREPARE_BEFORE_OPEN = dt.timedelta(hours=1)  # 브리핑 준비 = 출근 한 시간 전
AUTO_REPLY_DELAY = dt.timedelta(minutes=10)  # 아쉬운 리뷰가 들어오고 이만큼 뒤에 바로 답하기를 돈다
AUTO_REPLY_WINDOW = dt.timedelta(minutes=30)  # 이보다 오래된 리뷰에는 바로 답하지 않는다
POSITIVE_WINDOW = dt.timedelta(days=7)  # 좋은 리뷰 일주일 분석
POSITIVE_MIN = 3  # 최근 7일 좋은 리뷰가 이보다 적으면 4단계를 건너뛴다
NEGATIVE_WINDOW = dt.timedelta(days=28)  # 고칠 점 찾기에 보는 기간
TICK_SECONDS = 30  # 작업 큐를 보는 간격
FIXTURES = Path(__file__).resolve().parent / "fixtures"
# 켤 때 넣는 시연 가게 (비어 있으면 넣지 않는다). 그 파일의 demo.now 로 시계를 맞춘다 (시계는 켤 때마다 다시 맞춘다)
DEMO_FIXTURE = os.environ.get("VOICE_DEMO_FIXTURE", "s005_choongjang")


def agent_on(name: str) -> bool:
    """에이전트를 쓸지. VOICE_AGENT_<NAME>=false 로 끄면 템플릿·규칙으로만 돈다. CLOVA 키가 없어도 꺼진다."""
    return os.environ.get(f"VOICE_AGENT_{name.upper()}", "true").lower() != "false" and clova_tools.is_enabled()
