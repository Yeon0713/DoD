"""python -m Harness.evals <suite> … 의 입구. 스위트 이름 → 실행 함수.

스위트를 더하려면 SUITES 에 Suite 하나를 더한다. run(args) 는 argparse 결과를 받아 결과 폴더(report.start)를 만들고
result.json 을 쓴다. 공통 옵션의 뜻은 build_parser 에 적었다.

실제 CLOVA 를 부른다. server/.env 의 CLOVA_STUDIO_API_KEY 가 없으면 시작하지 않는다.
CLOVA 를 부르는 평가는 한 번에 한 프로세스만 돌린다. 동시 호출 한도(limiter, --concurrency)는 프로세스 안에서만 지켜져서,
두 평가를 함께 돌리면 CLOVA 동시 호출이 두 배가 되어 429 가 나고 에이전트가 물러나기로 끝나 결과가 흔들린다.
(label 은 hcx, guards 는 critic·judge_* 를 고를 때만 키가 필요하다. --dry-run 이면 키 없이 예상 호출 수만 본다)

--systems 의 뜻은 스위트마다 다르다. A/B 를 비교하는 스위트는 A, B, label 은 분류기 이름(rule, hcx, voice),
guards 는 판정기 이름(regex, critic, judge_tools, judge_thinking)이다.

critic, live 는 기존 스크립트(Harness/critic_eval.py, live_eval.py)를 그대로 부른다. 두 스크립트는 아직 예전 결과 모양
(result.json 에 schema 없음)으로 쓴다. 음성 점검(voice/live_check.py)의 /v1/turn 응답 시간은 voice 스위트가 잰다.
평가 지표 요약: summary 가 스위트 결과(label, reply, guards, intent, noise, voice, tts)를 질문 1~5 표 하나로 모은다 (계산은 scorecard.py, 대시보드도 같은 계산을 쓴다).
"""

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import settings
from Harness import limiter
from Harness.evals import gold, judge, report, systems


@dataclass(frozen=True)
class Suite:
    name: str
    description: str
    run: Callable[[argparse.Namespace], object]
    uses_systems: bool = False  # --systems 로 고를 수 있는지 (아니면 --systems 를 쓰지 않는다)
    uses_judge: bool = False  # 심판을 부르는지 (아니면 --judge-mode 를 쓰지 않는다)
    parse_systems: Callable[[str], list[str]] = systems.parse_names  # --systems 글 → 이름 목록 (잘못되면 ValueError·SystemUnavailable)
    default_systems: str = "A,B"
    needs_clova: Callable[[argparse.Namespace], bool] = lambda args: True  # 이 실행에 CLOVA 키가 필요한지


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


def _run_reply(args: argparse.Namespace) -> object:
    from Harness.evals import reply_eval

    return reply_eval.run(args)


def _reply_systems(text: str) -> list[str]:
    from Harness.evals import reply_eval

    return reply_eval.parse_systems(text)


def _batch_systems(text: str) -> list[str]:
    from Harness.evals import batch_eval

    return batch_eval.parse_systems(text)


def _run_batch(args: argparse.Namespace) -> object:
    from Harness.evals import batch_eval

    return batch_eval.run(args)


def _run_intent(args: argparse.Namespace) -> object:
    from Harness.evals import intent_eval

    return intent_eval.run(args)


def _intent_systems(text: str) -> list[str]:
    from Harness.evals import intent_eval

    return intent_eval.parse_systems(text)


def _run_noise(args: argparse.Namespace) -> object:
    from Harness.evals import noise_eval

    return noise_eval.run(args)


def _run_voice(args: argparse.Namespace) -> object:
    from Harness.evals import voice_eval

    return voice_eval.run(args)


def _voice_systems(text: str) -> list[str]:
    from Harness.evals import voice_eval

    return voice_eval.parse_systems(text)


def _run_tts(args: argparse.Namespace) -> object:
    from Harness.evals import tts_eval

    return tts_eval.run(args)


def _run_summary(args: argparse.Namespace) -> object:
    from Harness.evals import summary

    return summary.run(args)


def _run_all(args: argparse.Namespace) -> object:
    from Harness.evals import run_all

    return run_all.run_all(args, SUITES)


def _run_report(args: argparse.Namespace) -> object:
    from Harness.evals import report_md

    return report_md.run(args)


def _run_guards(args: argparse.Namespace) -> object:
    from Harness.evals import guards_eval

    return guards_eval.run(args)


def _guards_systems(text: str) -> list[str]:
    from Harness.evals import guards_eval

    return guards_eval.parse_judges(text)


SUITES: dict[str, Suite] = {suite.name: suite for suite in (
    Suite("critic", "LLM 검토기(reply_critic) 정확도: 판정 세트 놓침·오탐 (--ids 로 사례 고르기, 예전 결과 모양)", _run_critic),
    Suite("live", "에이전트 실제 호출: 가상 가게 t001 사례 7개의 과제 완료·호출 수·시간 (--ids 로 사례 이름, 예전 결과 모양)", _run_live),
    Suite("label", "리뷰 분류(질문 1): 분류기 rule, hcx, voice 의 아쉬운 리뷰 재현율·정밀도, 감정·불만 유형 F1. 정답지 필요 "
                   "(--systems 기본 rule,voice. hcx 는 실제 CLOVA. --scope balanced 면 64건만)",
          _run_label, uses_systems=True, parse_systems=_label_systems, default_systems="rule,voice",
          needs_clova=lambda args: "hcx" in args.system_names),
    Suite("reply", "답글(질문 2·4·5): 서버 경로 A(single_agent)·B(reply_agent.draft, 검토기 포함)의 적합률·안전 위반·과제 완료·3회 통과·호출 수·시간. "
                   "정답지 필요 (--split tune 48 기본, holdout 16, injection 20. --labels rule 이면 끝까지 실행. "
                   "--path voice 면 음성 경로 voice_single_agent·voice_reply 보조 실험. --systems S,A,B 의 S 는 지금 서비스 기준선)",
          _run_reply, uses_systems=True, uses_judge=True, parse_systems=_reply_systems),
    Suite("batch", "진단·묶음 조율(질문 2·4): A·B 의 심은 원인 찾기(d1~d4), 숫자 근거, 남은 충돌, 묶음 안 답글 적합, 재작업 한도. "
                   "건수로 적음 (d4 는 정답지가 있을 때만. --systems R,A,B 의 R 은 규칙 한 줄 기준선, 진단만)",
          _run_batch, uses_systems=True, uses_judge=True, parse_systems=_batch_systems),
    Suite("guards", "안전장치(질문 3): 판정기 regex, critic, judge_tools, judge_thinking 의 놓침·오거절·판단 불가·시간. 정답지 필요 "
                    "(critic_cases 41 + 정상 40 + 위반 40. --systems 기본 regex. --dry-run 이면 예상 호출 수만)",
          _run_guards, uses_systems=True, uses_judge=True, parse_systems=_guards_systems, default_systems="regex",
          needs_clova=lambda args: not args.dry_run and any(name != "regex" for name in args.system_names)),
    Suite("intent", "뜻 판정(질문 4, 공통): 규칙(rule)과 규칙+판정 에이전트(rule+judge)의 정확도·잘못 답한 비율·명령 무시·"
                    "판정 시간(3초)·규칙 비율. 세트 Harness/evals/data/intents_v1.json (rule 은 CLOVA 없이 돈다)",
          _run_intent, uses_systems=True, parse_systems=_intent_systems, default_systems="rule,rule+judge",
          needs_clova=lambda args: not args.dry_run and "rule+judge" in args.system_names),
    Suite("noise", "소음 강건성(모의 받아쓰기 오류, 오디오 아님): intent 세트에 오류를 강도 0~3 으로 넣고 강도별 뜻 판정 정확도·"
                   "오발성·명령 무시 (--levels 0,1,2,3, --systems 기본 rule,rule+judge. rule 은 CLOVA 없이 돈다)",
          _run_noise, uses_systems=True, parse_systems=_intent_systems, default_systems="rule,rule+judge",
          needs_clova=lambda args: not args.dry_run and "rule+judge" in args.system_names),
    Suite("voice", "응답 시간: POST /v1/turn 을 말 24개 대본으로 보내 종류별(브리핑 1초, 질문 3초, 주방 대화 3초) 목표 안 비율·"
                   "p50·p95·최댓값, 5초 초과율 (--systems 기본 rule+judge, rule 은 CLOVA 없이)",
          _run_voice, uses_systems=True, parse_systems=_voice_systems, default_systems="rule+judge",
          needs_clova=lambda args: not args.dry_run and "rule+judge" in args.system_names),
    Suite("all", "label → guards → reply → batch → intent 를 차례로 (스위트마다 기본 --systems). 실패해도 다음으로 가고 "
                 "끝에 결과 폴더를 출력한다. --baseline 이면 기준점으로 적는다",
          _run_all, needs_clova=lambda args: False),
    Suite("report", "결과 폴더들을 모아 보고서 report-<날짜>.md 를 쓴다 (CLOVA 없음. --results 비우면 스위트마다 최근 결과, "
                    "--out 으로 저장 위치)",
          _run_report, needs_clova=lambda args: False),
    Suite("tts", "TTS 합성 시간: 대표 문장 20개의 첫 소리·전체 합성 p50·p95 (CLOVA Voice 유료 호출. "
                 "TTS 를 쓸 수 없으면 결과를 남기지 않고 안 돌림)",
          _run_tts, needs_clova=lambda args: False),
    Suite("summary", "평가 지표 요약: 질문 1~5 의 대표 지표를 마크다운 표 하나로 (CLOVA 없음. --results 결과 폴더들, "
                     "비우면 모든 결과에서 지표마다 최근. --out 저장 위치. 대시보드 평가 탭 맨 위 카드와 같은 계산)",
          _run_summary, needs_clova=lambda args: False),
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
    parser.add_argument("--dry-run", action="store_true",
                        help="guards·intent·noise·voice: 세트와 예상 호출 수만 보여 주고 CLOVA 를 부르지 않는다")
    parser.add_argument("--levels", default="0,1,2,3", help="noise: 모의 받아쓰기 오류 강도 (쉼표로, 0~3)")
    parser.add_argument("--seed", default="A", help="noise: 오류를 넣는 seed. A(튜닝용, 기본), B(확인용), 또는 정수")
    parser.add_argument("--resume", default=None, metavar="결과폴더",
                        help="guards·reply: 끊긴 결과 폴더를 이어 돌린다 (cases.jsonl 에 있는 판정은 건너뜀)")
    parser.add_argument("--split", choices=("tune", "holdout", "injection"), default="tune",
                        help="reply: 답글 세트 (떼어 둔 holdout 은 이 값을 줄 때만 돈다)")
    parser.add_argument("--labels", choices=("gold", "rule"), default="gold",
                        help="reply: 리뷰 분류를 정답으로 줄지(gold), 음성 라벨 규칙을 거칠지(rule, 끝까지 실행)")
    parser.add_argument("--path", choices=("server", "voice"), default="server",
                        help="reply: server(주 실험, reply_agent.draft 대 single_agent) 또는 voice(보조, voice_reply 대 voice_single_agent)")
    parser.add_argument("--hcx-timeout", type=float, default=None, metavar="초",
                        help="label: hcx 분류기 호출 하나의 제한 시간 (평가 실행 안에서만. 운영 값은 hcx_classifier.TIMEOUT_SECONDS 그대로)")
    parser.add_argument("--system-concurrency", default="",
                        help="guards: 판정기마다 CLOVA 동시 호출 (예: judge_thinking=1). 적지 않은 판정기는 --concurrency")
    parser.add_argument("--system-runs", default="",
                        help="guards: 판정기마다 회차 (예: judge_tools=1,judge_thinking=1). 적지 않은 판정기는 --runs")
    parser.add_argument("--baseline", action="store_true",
                        help="all·한 스위트: 결과에 기준점 표시(config.baseline). report: 기준점 결과만 모은다")
    parser.add_argument("--results", default="", help="report·summary: 쉼표로 구분한 결과 폴더 (비우면 스위트마다 최근)")
    parser.add_argument("--out", default=None,
                        help="report·summary: 파일 경로 (기본 지금 폴더의 report-<날짜>.md, 평가지표-요약-<날짜>.md)")
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
    if suite.needs_clova(args) and not settings.clova_studio_api_key:
        raise SystemExit("server/.env 에 CLOVA_STUDIO_API_KEY 가 없어요")
    limiter.set_max_concurrent(args.concurrency)
    saved_baseline = report.BASELINE
    if args.baseline and suite.name not in ("all", "report", "summary"):  # all 은 스스로, report 는 기준점만 모으는 뜻
        report.BASELINE = True
    try:
        suite.run(args)
    except (judge.JudgeModelError, gold.GoldError) as error:
        raise SystemExit(f"멈춤: {error}") from None
    finally:
        report.BASELINE = saved_baseline
