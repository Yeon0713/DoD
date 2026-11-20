"""밤사이 준비 결과 저장본 (2026-11-18).

시연 이야기는 "도나가 밤사이 리뷰를 읽고 답글을 쓰고 브리핑을 준비해 뒀다"이다. 그런데 실제로 준비하면 CLOVA 로 답글을
수십 개 쓰느라 3 ~ 4분 걸려서, "처음부터"를 누르거나 서버를 켠 뒤 바로 브리핑을 들을 수 없었다.
그래서 한 번 준비한 결과(그 가게의 문서 전부: 리뷰와 답글, 브리핑, 예약 답글, 할 일 기록, 번호표)를
fixtures/<시나리오>.prepared.json 에 저장해 두고, 다음부터는 계산하지 않고 그대로 넣는다 (몇 초 → 1초 안).

  저장본 만들기 (CLOVA 키 필요, 3 ~ 4분, 시나리오나 답글 프롬프트를 고친 뒤 다시):
      cd server && .venv/bin/python -m voice.prepared_snapshot s005_choongjang
  쓰는 곳: api/dev.seed (처음부터, 서버를 켤 때 가게가 없으면)

시나리오 파일(fixtures/<시나리오>.json)이 바뀌면 저장본의 fixture_sha 와 달라져 쓰지 않고 예전처럼 새로 준비한다.
알바생 표는 시나리오 파일에서 매번 새로 넣는다 (staff.seed). 대화 기록(turn, session)과 알림은 저장하지 않는다.
"""

import hashlib
import json
import sys
from pathlib import Path

from voice import clock, config, repo

SKIP_KINDS = {"turn", "session", "notice"}
VERSION = 1
ENABLED = config.env("VOICE_PREPARED_SNAPSHOT", "true").lower() != "false"  # 끄면 늘 새로 준비한다
FOLDER: Path | None = None  # 시험에서 바꾼다 (없으면 config.FIXTURES)


def path(name: str) -> Path:
    return (FOLDER or config.FIXTURES) / f"{name}.prepared.json"


def fixture_sha(name: str) -> str:
    return hashlib.sha256((config.FIXTURES / f"{name}.json").read_bytes()).hexdigest()[:16]


def save(name: str, store_id: str) -> Path:
    """지금 저장소에 있는 그 가게의 준비된 상태를 저장본으로."""
    docs = [d for d in repo.store_docs(store_id) if d["kind"] not in SKIP_KINDS]
    data = {"version": VERSION, "fixture": name, "fixture_sha": fixture_sha(name), "store_id": store_id,
            "demo_now": clock.iso(clock.now()), "counters": repo.counters_of(store_id), "docs": docs}
    out = path(name)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


def load(name: str) -> dict | None:
    """쓸 수 있는 저장본. 없거나 시나리오 파일이 바뀌었으면 None."""
    found = path(name)
    if not ENABLED or not found.exists():
        return None
    try:
        data = json.loads(found.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if data.get("version") != VERSION or data.get("fixture_sha") != fixture_sha(name):
        return None
    return data


def restore(name: str, payload: dict) -> bool:
    """저장본을 그대로 넣는다. 넣었으면 True (브리핑까지 준비된 상태가 된다)."""
    data = load(name)
    if data is None:
        return False
    from voice import staff, staff_orders

    store_id = data["store_id"]
    repo.delete_store(store_id)
    staff_orders.forget_recent()
    repo.put_many(store_id, data["docs"])
    repo.set_counters(data["counters"])
    staff.seed(store_id, payload)  # 알바생 표는 시나리오 파일에서 (하린은 아직 안 들어온 상태)
    return True


def main() -> None:
    """저장본 만들기: 빈 임시 저장소에서 처음부터 준비(CLOVA)한 뒤 저장한다. 지금 쓰는 voice.db 는 건드리지 않는다."""
    import tempfile

    name = sys.argv[1] if len(sys.argv) > 1 else config.DEMO_FIXTURE
    with tempfile.TemporaryDirectory() as tmp:
        config.DB_PATH = Path(tmp) / "voice.db"
        from voice import tts
        from voice.api import dev

        tts.ENABLED = False  # 목소리는 만들지 않는다 (저장본에는 글만)
        old = path(name)
        if old.exists():
            old.unlink()  # 예전 저장본을 쓰지 않고 새로 준비하게
        print(f"[{name}] 밤사이 준비를 실제로 합니다 (CLOVA, 3 ~ 4분)…", flush=True)
        result = dev.seed(name, fresh=True)
        out = save(name, result["store_id"])
        print(f"저장본: {out} (문서 {len(json.loads(out.read_text(encoding='utf-8'))['docs'])}개)")


if __name__ == "__main__":
    main()
