"""비교할 시스템. 스위트는 같은 사례를 고른 시스템마다 넣고, 결과를 system 이름("A", "B")으로 나눠 적는다.

  B  멀티 에이전트 하네스 (지금 코드): 답글·진단·마케팅 일꾼이 나눠 맡고, reply_critic 이 따로 검토하고,
     conflicts + supervisor 가 묶음을 조율한다.
  A  단일 에이전트 (Harness/agents/single_agent.py): 에이전트 하나가 맡은 일 묶음 전체를 조사하고 한 번에 제출한다.
     별도 LLM 검토 없이 스스로 다시 읽고 고친다. 모델, 읽기 전용 도구, 규칙 검사, 근거 대조, 공통 정책, 실행 예산,
     빈 캐시, 물러나기 경로는 B 와 같게 둔다.

시스템 하나는 일 이름 → 함수 묶음이다. 함수는 Proposal 또는 None 을 돌려준다 (못 만든 것도 결과로 센다).
  draft(item, ctx)                       리뷰 답글 초안 / 재주문 인사
  rewrite(text, ctx, instruction, review_id)  답글 다시 쓰기
  diagnose(item, ctx)                    반복 불만 원인 분석
  campaign(item, ctx)                    메뉴판 후보 + 포스터 멘트
  coordinate(batch, proposals, ctx)      알림 묶음 조율 (A 는 스스로 맞추므로 받은 제안을 그대로 돌려줄 수 있다)
일 이름이 없는 시스템에 그 일을 맡기면 KeyError 대신 SystemUnavailable 을 낸다.
"""

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field

TASKS = ("draft", "rewrite", "diagnose", "campaign", "coordinate")
SINGLE_AGENT_MODULE = "Harness.agents.single_agent"


class SystemUnavailable(RuntimeError):
    """그 시스템이 아직 없거나 그 일을 하지 못한다."""


@dataclass
class System:
    name: str
    description: str
    tasks: dict[str, Callable] = field(default_factory=dict)

    def task(self, name: str) -> Callable:
        if name not in self.tasks:
            raise SystemUnavailable(f"시스템 {self.name} 은 '{name}' 일을 하지 못해요")
        return self.tasks[name]


def _system_b() -> System:
    from Harness.agents import campaign_agent, complaint_agent, reply_agent
    from Harness.supervisor import coordinate_batch

    return System("B", "멀티 에이전트 하네스 (지금 코드)", {
        "draft": reply_agent.draft,
        "rewrite": reply_agent.rewrite,
        "diagnose": complaint_agent.diagnose,
        "campaign": campaign_agent.plan_campaign,
        "coordinate": coordinate_batch,
    })


def _system_a() -> System:
    """single_agent 모듈의 SYSTEM_TASKS(일 이름 → 함수)를 읽는다. 모듈이 아직 없으면 SystemUnavailable."""
    try:
        module = importlib.import_module(SINGLE_AGENT_MODULE)
    except ModuleNotFoundError as error:
        if error.name != SINGLE_AGENT_MODULE:
            raise
        raise SystemUnavailable("단일 에이전트 A(Harness/agents/single_agent.py)가 아직 없어요") from None
    tasks = getattr(module, "SYSTEM_TASKS", None)
    if not isinstance(tasks, dict):
        raise SystemUnavailable(f"{SINGLE_AGENT_MODULE} 에 SYSTEM_TASKS(일 이름 → 함수)가 없어요")
    unknown = sorted(set(tasks) - set(TASKS))
    if unknown:
        raise SystemUnavailable(f"{SINGLE_AGENT_MODULE}.SYSTEM_TASKS 에 모르는 일 이름이 있어요: {', '.join(unknown)}")
    return System("A", "단일 에이전트", dict(tasks))


BUILDERS: dict[str, Callable[[], System]] = {"A": _system_a, "B": _system_b}


def get(name: str) -> System:
    if name not in BUILDERS:
        raise SystemUnavailable(f"모르는 시스템: {name} (A, B 중에서 고르세요)")
    return BUILDERS[name]()


def parse_names(text: str) -> list[str]:
    """'A,B' → ['A', 'B'] (순서 유지, 중복 제거). 모르는 이름이면 SystemUnavailable."""
    names = list(dict.fromkeys(part.strip().upper() for part in text.split(",") if part.strip()))
    unknown = [name for name in names if name not in BUILDERS]
    if unknown:
        raise SystemUnavailable(f"모르는 시스템: {', '.join(unknown)} (A, B 중에서 고르세요)")
    return names
