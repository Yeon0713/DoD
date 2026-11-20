"""실제 CLOVA 로 음성 백엔드 에이전트를 점검한다. server/.env 의 CLOVA 키가 필요하고 호출 비용이 든다.

사용 (server/ 에서):
  python -m voice.live_check            # 13장 기준 데이터로 시나리오 A·B 를 한 번 돈다
  python -m voice.live_check --runs 3   # 여러 번 돌려 흔들림까지 본다

보는 것
  - 답글(voice_reply): 에이전트 통과(AGENT) / 물러남(FALLBACK·TEMPLATE) 수, 검토 안 됨 수
  - 고칠 점(improve_tip): 근거 대조 통과 여부, 고른 문장
  - 브리핑 단계 /v1/turn 응답 시간 (LLM 을 부르지 않으므로 1초 안이어야 한다), 글자 폭 위반 수
- 저장소와 기록은 db/app_data/voice_check/<시각>/ 에 따로 둔다 (실제 voice.db, 개발자 대시보드 기록과 섞지 않는다).
"""

import argparse
import datetime as dt
import json
import time
from collections import Counter
from pathlib import Path

from app.core import clova_usage_log
from app.core.config import settings
from Harness import cache, trace
from voice import clock, config, width
from voice.tests.conftest import Donna, baseline
from voice.tests.test_scenario_b import NIGHT_REVIEW

OUT_ROOT = Path(__file__).resolve().parents[1] / "db" / "app_data" / "voice_check"


def one_run(number: int) -> dict:
    cache.CACHE_PATH = None  # 매번 실제로 불러 재므로 파일 캐시를 쓰지 않는다
    cache.clear()
    clock.set_now(None)
    donna = Donna()
    donna.client.post("/v1/dev/reset")
    payload = baseline()
    payload["reviews"] = [r for r in payload["reviews"] if r["id"] != "rv_0412"]
    payload["hr"] = {**payload.get("hr", {}), "negative_reply": "assistant"}  # 밤사이 묻지 않고 답한다 (인사과 대리)
    donna.clock("2026-11-16T21:40:00+09:00")
    donna.fixtures(payload)
    donna.review(**NIGHT_REVIEW)
    started = time.perf_counter()
    donna.clock("2026-11-17T09:00:00+09:00")  # 바로 답하기 + 브리핑 준비 (에이전트가 여기서 돈다)
    prepare_seconds = time.perf_counter() - started

    state = donna.state()
    replies = [r for r in state["review"] if r.get("reply_by") == "donna"]
    timings, violations = [], 0
    for text in ("오늘 일정 브리핑해 줘", "다음", "다음", "화면에 보여 줘", "돌아가기", "다음", "다음", "다음"):
        t0 = time.perf_counter()
        response = donna.turn(text)
        timings.append(time.perf_counter() - t0)
        violations += len(width.violations(response))
    briefing_doc = (state.get("briefing") or [{}])[-1]
    return {
        "run": number,
        "prepare_seconds": round(prepare_seconds, 1),
        "reply_sources": dict(Counter(r.get("reply_source") for r in replies)),
        "not_reviewed": sum(1 for r in replies if "검토 안 됨" in (r.get("reply_notes") or [])),
        "replies": [{"id": r["id"], "status": r["reply_status"], "source": r.get("reply_source"), "text": r["reply_text"]} for r in replies],
        "improve_tip": {"source": (briefing_doc.get("sources") or {}).get("improve_tip"),
                        "text": next((c["text"] for c in ((briefing_doc.get("steps") or {}).get("negative") or {}).get("cards", [])
                                      if c["type"] == "tip"), None)},
        "turn_seconds_max": round(max(timings), 3),
        "width_violations": violations,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()
    if not settings.clova_studio_api_key:
        raise SystemExit("server/.env 에 CLOVA_STUDIO_API_KEY 가 없어요")
    out = OUT_ROOT / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    config.DB_PATH = out / "voice.db"
    clova_usage_log.LOG_PATH = out / "clova_usage.db"
    trace.TRACE_PATH = out / "harness_trace.db"

    results = [one_run(n) for n in range(1, args.runs + 1)]
    for result in results:
        print(f"\n[{result['run']}회] 준비 {result['prepare_seconds']}초, 답글 {result['reply_sources']}, 검토 안 됨 {result['not_reviewed']}, "
              f"고칠 점 {result['improve_tip']}, 브리핑 응답 최대 {result['turn_seconds_max']}초, 폭 위반 {result['width_violations']}")
        for reply in result["replies"]:
            print(f"  - {reply['id']} {reply['status']} {reply['source']}: {reply['text']}")
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n기록: {out}")


if __name__ == "__main__":
    main()
