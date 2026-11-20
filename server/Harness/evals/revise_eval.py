"""사장님 고침 지시 평가 (인사과 9장 6단계, voice/agents/voice_reply.py revise). 실제 CLOVA 를 부른다.

세트 Harness/evals/data/revise_cases.json: 리뷰, 지난 답글, 지시, 코드로 볼 수 있는 조건(check).
잰 것: 지시를 지킨 비율(check 조건 모두), 검사를 통과해 고친 글이 나온 비율(물러나지 않음), 시간.
말투(부드럽게 등)는 코드로 재지 않는다. 세트의 정답은 초안이다 (verified_by). 팀이 검토해 고친다.
"""

import argparse
import re
import time

from Harness.evals import metrics, report
from Harness.evals.staff_eval import DATA, _isolate, _load, _view

REVISE_DATA = DATA / "revise_cases.json"
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def followed(case: dict, text: str) -> list[str]:
    """지키지 못한 조건 목록 (빈 목록이면 지켰다)."""
    rule, broken = case["check"], []
    if rule.get("shorter") and len(text) >= len(case["previous"]):
        broken.append("shorter")
    if rule.get("no_emoji") and EMOJI_RE.search(text):
        broken.append("no_emoji")
    if rule.get("no_exclaim") and "!" in text:
        broken.append("no_exclaim")
    broken += [f"must_not:{w}" for w in rule.get("must_not", []) if w in text]
    broken += [f"must:{w}" for w in rule.get("must", []) if w not in text]
    return broken


def run_revise(args: argparse.Namespace):
    """python -m Harness.evals revise [--ids …]"""
    from voice import config as voice_config
    from voice.agents import voice_reply

    body, cases = _load(REVISE_DATA, args.ids)
    print(f"고침 지시 {len(cases)}건", flush=True)
    if getattr(args, "dry_run", False):
        print(f"--dry-run: 예상 CLOVA 호출 약 {len(cases) * 7}회 (답글 + 검토 질문)")
        return None
    eval_run = report.start("revise", config={"data": {"file": REVISE_DATA.name, "sha256": report.file_sha256(REVISE_DATA),
                                                        "verified_by": body.get("verified_by")}}, systems=["revise"])
    _isolate(eval_run.out)
    voice_config.agent_on = lambda name: name == "reply"  # 이 프로세스 안에서만
    kept, produced, seconds = 0, 0, []
    for case in cases:
        review = {"id": case["id"], "store_id": "eval", "text": case["text"], "rating": 2 if case["sentiment"] == "negative" else 5,
                  "sentiment": case["sentiment"], "topic": "other", "written_at": "2026-01-01T00:00:00+09:00"}
        occasion = {"kind": "weekday_to_weekend", "label": "주말 점심 전", "explanation": "주말에 리뷰를 많이 봐요",
                    "post_at": "2026-01-03T11:00:00+09:00"} if case["kind"] == "SCHEDULED" else None
        started = time.monotonic()
        got = voice_reply.revise(_view(review), review, case["kind"], case["previous"], case["instruction"], occasion=occasion)
        seconds.append(time.monotonic() - started)
        broken = followed(case, got["text"]) if got else ["fallback"]
        produced += got is not None
        kept += not broken
        eval_run.add_case({"id": case["id"], "instruction": case["instruction"], "text": got["text"] if got else None,
                           "broken": broken, "seconds": round(seconds[-1], 2)})
        print(f"  {case['id']} {case['instruction']}: {'지킴' if not broken else broken} {got['text'] if got else ''}", flush=True)
    eval_run.metrics = [
        metrics.metric("revise.followed", "지시를 지킨 비율 (코드로 보는 조건)", question=2, system="revise",
                       numerator=kept, denominator=len(cases)),
        metrics.metric("revise.produced", "검사를 통과해 고친 글이 나온 비율", question=2, system="revise",
                       numerator=produced, denominator=len(cases)),
        metrics.value_metric("revise.seconds_median", "고쳐 쓰는 시간 중앙값", question=5, system="revise",
                             value=metrics.latency(seconds)["median"], unit="seconds"),
    ]
    out = eval_run.finish()
    print(f"result.json: {out}")
    return out
