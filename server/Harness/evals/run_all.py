"""python -m Harness.evals all : label → guards → reply → batch → intent 를 차례로 돌린다.

- 스위트마다 그 스위트의 기본 --systems 를 쓴다 (--systems 는 무시한다). 나머지 옵션(--runs, --judge-mode, 정답지 등)은 같이 쓴다.
- 한 스위트가 실패해도(예외, SystemExit) 다음으로 간다. CLOVA 키가 필요한데 없으면 그 스위트는 "안 돌림".
- --baseline 이면 각 result.json 의 config.baseline 을 true 로 적는다 (대시보드 추세에서 기준점으로 그린다).
- 끝에 스위트마다 결과 폴더(또는 실패·안 돌림 까닭)를 출력하고 그 목록을 돌려준다. 보고는 `report` 스위트가 쓴다.
"""

import argparse
import copy
import sys
import traceback
from pathlib import Path

from app.core.config import settings
from Harness.evals import report

ORDER = ("label", "guards", "reply", "batch", "intent")


def run_all(args: argparse.Namespace, suites: dict) -> list[dict]:
    outcomes = []
    saved_baseline = report.BASELINE
    report.BASELINE = bool(getattr(args, "baseline", False))
    try:
        for name in ORDER:
            suite = suites[name]
            one = copy.copy(args)
            one.suite = name
            one.resume = None
            one.system_names = suite.parse_systems(suite.default_systems) if suite.uses_systems else []
            print(f"\n== {name} ({', '.join(one.system_names) or '-'}) ==", flush=True)
            if suite.needs_clova(one) and not settings.clova_studio_api_key:
                outcomes.append({"suite": name, "status": "안 돌림", "reason": "CLOVA 키 없음", "out": None})
                continue
            try:
                out = suite.run(one)
            except SystemExit as stop:
                outcomes.append({"suite": name, "status": "실패", "reason": str(stop), "out": None})
                continue
            except Exception as error:  # 한 스위트가 실패해도 나머지는 돈다
                traceback.print_exc(file=sys.stderr)
                outcomes.append({"suite": name, "status": "실패", "reason": f"{type(error).__name__}: {error}", "out": None})
                continue
            folder = Path(out).parent if out and Path(out).name == "result.json" else (Path(out) if out else None)
            outcomes.append({"suite": name, "status": "완료", "reason": "", "out": str(folder) if folder else None})
    finally:
        report.BASELINE = saved_baseline
    print("\n== 결과 폴더 ==")
    for row in outcomes:
        print(f"  {row['suite']:<7} {row['status']}  {row['out'] or row['reason']}")
    return outcomes
