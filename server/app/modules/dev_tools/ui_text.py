"""개발자 대시보드 "화면 글" 탭: 앱 화면의 글을 화면별로 보고, 고친 글을 앱 코드에 넣는다.

글을 뽑고 넣는 일은 앱 쪽 Node 스크립트(mobile/scripts/ui-text/cli.mjs, TypeScript 파서를 씀)가 하고,
서버는 그 스크립트를 불러 결과(JSON)를 그대로 넘겨준다. 그래서 서버 컴퓨터에 node 와 mobile/node_modules 가 있어야 한다.

- data  : 화면별 글, edits.json 에 저장해 둔 수정, 원본을 못 찾은 수정
- save  : 수정을 mobile/scripts/ui-text/edits.json 에 저장
- apply : 저장하고 앱 코드(mobile/src)의 글을 바꾼 뒤 타입 검사(tsc)
- export: 밖에서 고치는 JSON (화면별 모든 원본 + 빈 "수정" 칸)
- import: 밖에서 고친 JSON 의 "수정"을 원본 글로 자리를 찾아 edits.json 에 더하기
"""

import json
import shutil
import subprocess
from pathlib import Path

from app.core.error_response import ApiError

REPO = Path(__file__).resolve().parents[4]
MOBILE = REPO / "mobile"
CLI = MOBILE / "scripts" / "ui-text" / "cli.mjs"

# apply 는 코드를 바꾼 뒤 tsc 까지 돌려서 오래 걸릴 수 있다
TIMEOUT_SECONDS = {"data": 60, "save": 30, "apply": 180, "export": 60, "import": 60}


def run(command: str, body: dict | None = None) -> dict:
    """cli.mjs <command> 를 부르고 stdout 의 JSON 을 돌려준다."""
    node = shutil.which("node")
    if node is None:
        raise ApiError(503, "NODE_NOT_FOUND", "node 를 찾지 못했어요. 화면 글 탭은 Node.js 가 있는 컴퓨터에서 서버를 켜야 써요.")
    if not (MOBILE / "node_modules" / "typescript").is_dir():
        raise ApiError(503, "MOBILE_NOT_INSTALLED", "mobile/node_modules 가 없어요. mobile 폴더에서 npm install 을 먼저 해 주세요.")
    try:
        done = subprocess.run(
            [node, str(CLI), command],
            cwd=MOBILE,
            input=json.dumps(body or {}, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=TIMEOUT_SECONDS[command],
        )
    except subprocess.TimeoutExpired as e:
        raise ApiError(504, "UI_TEXT_TIMEOUT", "화면 글 스크립트가 너무 오래 걸려요. 잠시 뒤 다시 해 주세요.") from e
    if done.returncode != 0:
        # node 가 섞어 내는 인증서 경고 줄은 빼고 마지막 몇 줄만 보여 준다
        lines = [line for line in done.stderr.splitlines() if line.strip() and "trust settings" not in line]
        raise ApiError(500, "UI_TEXT_FAILED", "화면 글 스크립트가 실패했어요: " + " / ".join(lines[-3:]))
    return json.loads(done.stdout)
