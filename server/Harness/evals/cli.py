"""python -m Harness.evals <suite> … 의 입구. 스위트 이름 → 실행 함수.

스위트를 더하려면 SUITES 에 Suite 하나를 더한다. run(args) 는 argparse 결과를 받아 결과 폴더(report.start)를 만들고
result.json 을 쓴다. 공통 옵션의 뜻은 build_parser 에 적었다.

실제 CLOVA 를 부른다. server/.env 의 CLOVA_STUDIO_API_KEY 가 없으면 시작하지 않는다.
(label 스위트는 hcx 분류기를 고를 때만 키가 필요하다. rule, voice 는 CLOVA 를 부르지 않는다)

--systems 의 뜻은 스위트마다 다르다. A/B 를 비교하는 스위트는 A, B, label 은 분류기 이름(rule, hcx, voice)이다.

critic, live 는 기존 스크립트(Harness/critic_eval.py, live_eval.py)를 그대로 부른다. 두 스크립트는 아직 예전 결과 모양
(result.json 에 schema 없음)으로 쓴다. 음성 점검(voice/live_check.py)은 run() 입구가 생기면 스위트로 더한다.
"""

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import settings
from Harness import limiter
from Harness.evals import gold, judge, systems


@dataclass(frozen=True)
class Suite:
    name: str
    description: str
    run: Callable[[argparse.Namespace], object]
    uses_systems: bool = False  # --systems 로 고를 수 있는지 (아니면 --systems 를 쓰지 않는다)
    uses_judge: bool = False  # 심판을 부르는지 (아니면 --judge-mode 를 쓰지 않는다)
    parse_systems: Callable[[str], list[str]] = systems.parse_names  # --systems 글 → 이름 목록 (잘못되면 ValueError·SystemUnavailable)
    default_systems: str = "A,B"
    needs_clova: Callable[[list[str]], bool] = lambda names: True  # 고른 시스템으로 CLOVA 키가 필요한지


def _ids(args: argparse.Namespace) -> list[str] | None:
    return [part for part in args.ids.split(",") if part] or None


def _run_critic(args: argparse.Namespace) -> object:
    from Harness import critic_eval

    return critic_eval.run(args.runs, _ids(args), args.workers)


def _run_live(args: argparse.Namespace) -> object:
    from Harness import live_eval

    return live_eval.run(args.runs, _ids(args), args.workers)


def _run_label(args: argparse.Namespace) -> object:
    from Harness.evals import label_eval

    return label_eval.run(args)


def _label_systems(text: str) -> list[str]:
    from Harness.evals import label_eval

    return label_eval.parse_classifiers(text)


SUITES: dict[str, Suite] = {suite.name: suite for suite in (
    Suite("critic", "LLM 검토기(reply_critic) 정확도: 판정 세트 놓침·오탐 (--ids 로 사례 고르기, 예전 결과 모양)", _run_critic),
    Suite("live", "에이전트 실제 호출: 가상 가게 t001 사례 7개의 과제 완료·호출 수·시간 (--ids 로 사례 이름, 예전 결과 모양)", _run_live),
    Suite("label", "리뷰 분류(질문 1): 분류기 rule, hcx, voice 의 아쉬운 리뷰 재현율·정밀도, 감정·불만 유형 F1. 정답지 필요 "
                   "(--systems 기본 rule,voice. hcx 는 실제 CLOVA. --scope balanced 면 64건만)",
          _run_label, uses_systems=True, parse_systems=_label_systems, default_systems="rule,voice",
          needs_clova=lambda names: "hcx" in names),
)}


def suite_list() -> str:
    width = max(len(name) for name in SUITES)
    return "\n".join(f"  {name:<{width}}  {suite.description}" for name, suite in SUITES.items())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m Harness.evals",
        description="도나 에이전트 평가 (실제 CLOVA). 결과는 db/app_data/harness_eval/<suite>-<시각>/ 에 남는다.",
        epilog="스위트:\n" + suite_list(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("suite", choices=list(SUITES), metavar="suite", help="돌릴 스위트 (아래 목록)")
    parser.add_argument("--runs", type=int, default=1, help="같은 사례를 돌리는 횟수. 3회 모두 통과율을 보려면 3")
    parser.add_argument("--systems", default=None,
                        help="비교할 시스템. 보통 A 단일 에이전트, B 멀티 에이전트 하네스(기본 A,B). label 은 rule,hcx,voice")
    parser.add_argument("--ids", default="", help="쉼표로 구분한 사례 id (비우면 전체)")
    parser.add_argument("--workers", type=int, default=4, help="동시에 돌리는 사례 수 (1 이면 하나씩)")
    parser.add_argument("--concurrency", type=int, default=limiter.MAX_CONCURRENT,
                        help="CLOVA 동시 호출 한도. 4 는 429 가 많이 났다 (2026-11-15)")
    parser.add_argument("--judge-mode", choices=judge.MODES, default="tools",
                        help="심판 방식. tools: 추론 끄고 도구로 제출, thinking: 추론 켜고 JSON 글로 답")
    parser.add_argument("--scope", choices=("full", "balanced"), default="full",
                        help="label: full 이면 전체와 balanced 둘 다, balanced 면 balanced 64건만 분류")
    gold.add_arguments(parser)  # 정답지를 쓰는 스위트가 gold.from_args(args) 로 읽는다
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    suite = SUITES[args.suite]
    if args.runs < 1:
        raise SystemExit("--runs 는 1 이상이어야 해요")
    args.system_names = []
    if suite.uses_systems:
        try:
            args.system_names = suite.parse_systems(args.systems or suite.default_systems)
        except (ValueError, systems.SystemUnavailable) as error:
            raise SystemExit(str(error)) from None
    elif args.systems is not None:
        print(f"[알림] {suite.name} 스위트는 시스템을 나누지 않아 --systems 를 쓰지 않아요 (지금 하네스만 잽니다)", file=sys.stderr)
    if suite.needs_clova(args.system_names) and not settings.clova_studio_api_key:
        raise SystemExit("server/.env 에 CLOVA_STUDIO_API_KEY 가 없어요")
    limiter.set_max_concurrent(args.concurrency)
    try:
        suite.run(args)
    except (judge.JudgeModelError, gold.GoldError) as error:
        raise SystemExit(f"멈춤: {error}") from None
