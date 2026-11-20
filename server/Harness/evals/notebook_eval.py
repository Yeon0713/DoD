"""업무 수첩 규칙 판정 평가 (인사과 9장 7단계, voice/agents/notebook_rule.py). 실제 CLOVA 를 부른다.

세트 Harness/evals/data/notebook_cases.json: 사장님 말, 업무, 정답(계속 지킬 규칙인가, 칸).
잰 것: 규칙 판정 정확도·정밀도(적은 것 중 맞은 것)·재현율, 칸(agent|common) 정확도, 물러난 비율, 시간.
세트의 정답은 초안이다 (verified_by). 팀이 검토해 고친다.
"""

import argparse
import time

from Harness.evals import metrics, report
from Harness.evals.staff_eval import DATA, _isolate, _load, _view

NOTEBOOK_DATA = DATA / "notebook_cases.json"


def run_notebook(args: argparse.Namespace):
    """python -m Harness.evals notebook [--ids …]"""
    from voice import config as voice_config
    from voice.agents import notebook_rule

    body, cases = _load(NOTEBOOK_DATA, args.ids)
    print(f"수첩 규칙 {len(cases)}건", flush=True)
    if getattr(args, "dry_run", False):
        print(f"--dry-run: 예상 CLOVA 호출 약 {len(cases)}회")
        return None
    eval_run = report.start("notebook", config={"data": {"file": NOTEBOOK_DATA.name, "sha256": report.file_sha256(NOTEBOOK_DATA),
                                                          "verified_by": body.get("verified_by")}}, systems=["notebook"])
    _isolate(eval_run.out)
    voice_config.agent_on = lambda name: name == "notebook"  # 이 프로세스 안에서만
    gold, predicted, scope_ok, scope_n, fell_back, seconds = [], [], 0, 0, 0, []
    for case in cases:
        started = time.monotonic()
        got = notebook_rule.judge(_view(), case["said"], case["job"], [])
        seconds.append(time.monotonic() - started)
        fell_back += got is None
        guess = None if got is None else got["is_rule"]
        gold.append(case["is_rule"])
        predicted.append(guess)
        if case["is_rule"] and guess:
            scope_n += 1
            scope_ok += got["scope"] == case["scope"]
        eval_run.add_case({"id": case["id"], "said": case["said"], "gold": case["is_rule"], "predicted": guess,
                           "text": got["text"] if got else None, "scope": got["scope"] if got else None, "seconds": round(seconds[-1], 2)})
        print(f"  {case['id']} {case['said']}: 정답 {case['is_rule']} / 판정 {guess} {got['text'] if got else ''}", flush=True)
    prf = metrics.precision_recall_f1(gold, predicted, True)
    done = [p for p in predicted if p is not None]
    eval_run.metrics = [
        metrics.metric("notebook.accuracy", "계속 지킬 규칙인가 판정 정확도", question=2, system="notebook",
                       numerator=sum(1 for g, p in zip(gold, predicted) if p is not None and g == p), denominator=len(done)),
        metrics.value_metric("notebook.precision", "규칙 정밀도 (적은 것 중 맞은 것)", question=2, system="notebook",
                             value=prf.get("precision"), unit="ratio", higher_is_better=True),
        metrics.value_metric("notebook.recall", "규칙 재현율", question=2, system="notebook", value=prf.get("recall"), unit="ratio",
                             higher_is_better=True),
        metrics.metric("notebook.scope", "칸(담당·공통) 정확도", question=2, system="notebook", numerator=scope_ok, denominator=scope_n),
        metrics.metric("notebook.fallback", "판정하지 못한 비율", question=2, system="notebook",
                       numerator=fell_back, denominator=len(cases), higher_is_better=False),
        metrics.value_metric("notebook.seconds_median", "판정 시간 중앙값", question=5, system="notebook",
                             value=metrics.latency(seconds)["median"], unit="seconds"),
    ]
    out = eval_run.finish()
    print(f"result.json: {out}")
    return out
