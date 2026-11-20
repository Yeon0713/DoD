"""인사과가 새로 보내는 줄 종류·알림 종류가 앱 타입(donna-voice/app/src/lib/api.ts)에 있는지.

앱은 줄 종류로 아이콘을 찾는다 (cards.tsx ROW_LOOK[r.kind]). 모르는 종류를 보내면 화면이 깨진다 (2026-11-21 인사과 8단계에서 찾음).
"""

import re
from pathlib import Path

from voice import notebook
from voice.tests.test_scenario_b import night_then_morning

API = Path(__file__).resolve().parents[3] / "donna-voice" / "app" / "src" / "lib" / "api.ts"


def _union_after(marker: str) -> set[str]:
    text = API.read_text(encoding="utf-8")
    start = text.index(marker) + len(marker)
    return set(re.findall(r"'([a-z_]+)'", text[start:text.index(";", start)]))


def test_new_row_kinds_are_known_to_the_app():
    known = _union_after("export type RowKind =")
    donna, _ = night_then_morning()
    donna.turn("오늘 일정 브리핑해 줘")
    report = donna.turn("다음")  # 사후 보고 (done_report)
    notebook.add("s001", "common", "이모티콘 쓰지 않기", "x")
    read = donna.turn("수첩에 뭐 적혀 있어?")
    kinds = {r["kind"] for response in (report, read) for c in response["cards"] if c["type"] == "rows" for r in c["rows"]}
    assert kinds and kinds <= known, sorted(kinds - known)


def test_new_notice_kinds_are_known_to_the_app():
    known = _union_after("kind: 'staff_joined'") | {"staff_joined"}  # 알림(Notice) 종류
    assert {"hr_batch", "notebook"} <= known
