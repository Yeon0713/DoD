"""음성 백엔드 설정. 문서 14장의 정해지지 않은 값도 여기 모아 둔다 (임시로 정한 값)."""

import datetime as dt
import os
from pathlib import Path

from dotenv import dotenv_values

from Harness import clova_tools

# server/.env 는 메인 설정(pydantic Settings)의 칸으로만 읽혀 os.environ 에 들어가지 않는다.
# 그래서 아래 VOICE_* 값은 셸 환경 변수를 먼저 보고, 없으면 server/.env 를 본다 (2026-11-21).
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
_DOTENV = {k: v for k, v in dotenv_values(ENV_FILE).items() if v is not None} if ENV_FILE.exists() else {}


def env(name: str, default: str) -> str:
    return os.environ.get(name, _DOTENV.get(name, default))


DB_PATH = Path(env("VOICE_DB_PATH", str(Path(__file__).resolve().parents[1] / "db" / "app_data" / "voice.db")))
PORT = int(env("VOICE_PORT", "8100"))

GROUP_MIN_PEOPLE = 8  # 몇 명부터 단체 예약인가 (14장 8번 제안)
PREPARE_BEFORE_OPEN = dt.timedelta(hours=1)  # 브리핑 준비 = 출근 한 시간 전
AUTO_REPLY_DELAY = dt.timedelta(minutes=10)  # 아쉬운 리뷰가 들어오고 이만큼 뒤에 바로 답하기를 돈다
AUTO_REPLY_WINDOW = dt.timedelta(minutes=30)  # 이보다 오래된 리뷰에는 바로 답하지 않는다
# 영업 중 아쉬운 리뷰 (2026-11-18 팀 개선안): 바로 알리고, 15분 뒤 한 번 더, 25분까지 대답이 없으면 사과만 먼저 (30분 골든타임 안)
ALERT_BEFORE_OPEN = dt.timedelta(hours=1)  # 문 열기 한 시간 전부터 문 닫을 때까지 온 리뷰는 알린다. 그 밖은 AUTO_REPLY_DELAY 뒤 바로 답하기
ALERT_REMIND_AFTER = dt.timedelta(minutes=15)
ALERT_FALLBACK_AFTER = dt.timedelta(minutes=25)
# 영업 중 알림의 사과 답글을 에이전트(CLOVA)로 쓸지. 기본은 원인별 템플릿(원인과 실제 조치를 적은 글)으로 바로 알린다:
# 에이전트는 30초쯤 걸리고(2026-11-18 브라우저 확인), 그 글이 보상 검사(safe_reply)에 걸리면 어차피 템플릿으로 돌아온다.
ALERT_AGENT_REPLY = env("VOICE_ALERT_AGENT_REPLY", "false").lower() == "true"
POSITIVE_WINDOW = dt.timedelta(days=7)  # 좋은 리뷰 일주일 분석
POSITIVE_MIN = 3  # 최근 7일 좋은 리뷰가 이보다 적으면 4단계를 건너뛴다
NEGATIVE_WINDOW = dt.timedelta(days=28)  # 고칠 점 찾기에 보는 기간
TICK_SECONDS = 30  # 작업 큐를 보는 간격
FIXTURES = Path(__file__).resolve().parent / "fixtures"
# 켤 때 넣는 시연 가게 (비어 있으면 넣지 않는다). 그 파일의 demo.now 로 시계를 맞춘다 (시계는 켤 때마다 다시 맞춘다)
DEMO_FIXTURE = env("VOICE_DEMO_FIXTURE", "s005_choongjang")
DEMO_STORE_ID = env("VOICE_DEMO_STORE_ID", "s005")  # 로그인하지 않고 열었을 때 보여 줄 가게
# 네이버 로그인을 마치고 돌아갈 수 있는 사장님 앱 주소 (voice/api/account.py). 메인 서버 CORS 목록과 따로 둔다
APP_ORIGINS = {o.strip() for o in env("VOICE_APP_ORIGINS", "http://localhost:8090,http://127.0.0.1:8090").split(",") if o.strip()}


def agent_on(name: str) -> bool:
    """에이전트를 쓸지. VOICE_AGENT_<NAME>=false (셸 또는 server/.env) 로 끄면 템플릿·규칙으로만 돈다. CLOVA 키가 없어도 꺼진다."""
    return env(f"VOICE_AGENT_{name.upper()}", "true").lower() != "false" and clova_tools.is_enabled()


# 인사과 (2026-11-21, donna-voice/docs/agent-structure.md 4장·9-0). 평가는 HR_EPOCH(월)부터 HR_PERIOD 마다
HR_EPOCH = dt.date(2026, 11, 30)
HR_PERIOD = dt.timedelta(days=14)
HR_PROMOTE_RATIO = 0.9  # 2주 안 결재 중 그대로 승인이 이 비율 이상이면 한 단계 오른다
HR_BATCH_WINDOW = dt.timedelta(minutes=30)  # 사원 업무의 영업 중 묶음: 첫 건 뒤 이만큼 모았다가 한 번에 묻는다 (9-0 a)


def hr_on() -> bool:
    """VOICE_HR=false (셸 또는 server/.env) 면 반응 기록·평가·강등·수첩 판정을 멈춘다. 직급은 저장된 그대로 읽는다 (9-0 r)."""
    return env("VOICE_HR", "true").lower() != "false"


# 감사팀 (2026-11-22, donna-voice/docs/audit-team-plan.md). 실행 중 스위치는 두지 않는다 (18장 3번)
AUDIT_RETURNS = 2  # 2차 감사 불합격 뒤 같은 대화로 되돌리는 최대 횟수 (결정 6). 1차 코드 거절과 따로 센다
AUDIT_ROUND_SECONDS = 60  # 2차 감사 한 회차의 상한. 넘으면 그 회차는 감사 못 함 (서버가 멈추지 않게 하는 안전장치)
