"""에이전트 하나를 적는 모양과 실행 맥락, 결과.

에이전트 하나를 더하는 일 = 프롬프트, 조회 도구 목록, 제출 도구, 검사기를 AgentSpec 하나로 적는 것.
task 는 에이전트마다 정한 키를 가진 dict 다 (각 에이전트 모듈 맨 위에 적어 둔다).
"""

import dataclasses
import datetime as dt
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

import httpx

from app.core.clova import Post
from Harness.grounding import Evidence
from Harness.trace import new_run_id


class CallBudget:
    """여러 실행이 함께 쓰는 CLOVA 호출 수 예산. supervisor 와 그 아래 일꾼 재작업이 같은 예산에서 뺀다."""

    def __init__(self, calls: int):
        self.remaining = calls
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.remaining <= 0:
                return False
            self.remaining -= 1
            return True


class StoreView(Protocol):
    """하네스가 가게 데이터에서 꼭 쓰는 것. 기존 StoreSnapshot 과 음성 백엔드(voice)의 가게 보기가 모두 맞춘다.
    그 밖의 칸은 각 에이전트의 도구가 읽는다."""

    store_id: str
    store: dict  # 가게 한 줄. name, category 를 쓴다


@dataclass
class RunContext:
    """실행 맥락. 도구는 여기서만 가게를 알아서, 모델이 다른 가게를 조회할 수 없다."""

    snapshot: StoreView
    now: dt.datetime
    run_id: str = field(default_factory=new_run_id)
    parent_run_id: str | None = None
    post: Post = httpx.post  # 테스트에서 가짜를 넣는다
    store_facts: list[str] = field(default_factory=list)  # 가게가 등록한 사실 메모. 받는 곳이 아직 없어 기본은 비어 있다
    call_budget: CallBudget | None = None
    # 이 실행이 넘기지 않을 시각 (runner.clock, monotonic). runner 가 시작할 때 채우고 일꾼(child)에게 물려준다 (H7)
    deadline: float | None = None

    @property
    def store_id(self) -> str:
        return self.snapshot.store_id

    @property
    def store(self) -> dict:
        """프롬프트와 기존 함수가 쓰는 가게 정보 {store_id, name, category}."""
        row = self.snapshot.store
        return {"store_id": self.snapshot.store_id, "name": row.get("name", ""), "category": row.get("category", "")}

    def child(self) -> "RunContext":
        """이 실행 아래에서 도는 일꾼 실행의 맥락. 호출 수 예산은 함께 쓴다."""
        return dataclasses.replace(self, run_id=new_run_id(), parent_run_id=self.run_id)


ToolFunc = Callable[[RunContext, dict, dict], object]  # (맥락, task, 모델이 보낸 인자) → JSON 으로 바꿀 수 있는 값


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema (type: object)
    func: ToolFunc | None = None  # 제출 도구는 실행할 함수가 없다

    def schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}

    def missing(self, args: dict) -> list[str]:
        return [key for key in self.parameters.get("required", []) if key not in args]


@dataclass(frozen=True)
class Budget:
    max_steps: int = 6  # CLOVA 를 부르는 최대 횟수
    max_rejections: int = 2  # 제출이 거절되어도 되는 횟수. 넘으면 물러난다
    max_seconds: float = 40.0
    # 말로 하는 대화용: max_seconds 를 넘기지 않는다. 호출 하나의 제한 시간을 남은 예산으로 두고,
    # 429 를 기다렸다 다시 부르거나 강제 제출 400 에 조건을 바꿔 다시 묻지 않는다 (같은 입력은 거의 다시 실패하고 시간만 두 배가 된다)
    strict: bool = False


@dataclass
class Proposal:
    """에이전트의 결과는 제안뿐이다. 실행은 사장님 승인 뒤 기존 코드가 한다."""

    agent: str
    task_id: str  # 보통 할 일 id(plan_id)
    content: dict
    source: Literal["AGENT", "FALLBACK"]
    run_id: str
    evidence: list[str] = field(default_factory=list)  # 본 근거의 출처(input, 도구 이름)
    notes: list[str] = field(default_factory=list)  # 예) "검토 안 됨"
    # 2차 감사 결과 {passed: True | False | None, rounds, reasons, trail}. 감사 자리(AgentSpec.audit)가 없거나 물러나기면 None.
    # passed False 는 되돌림을 다 쓰고도 불합격(끝내 불합격), None 은 감사를 못 함. trail 은 회차마다 {round, status, criterion, reason, quotes, calls, ms}
    audit: dict | None = None


CheckFunc = Callable[[dict, Evidence, dict, RunContext, list[str]], str | None]  # (제출 인자, 근거, task, 맥락, notes)


@dataclass
class AuditVerdict:
    """2차 감사 한 회차의 판정. 하네스는 누가 감사하는지 모른다 (음성 백엔드의 감사팀이 채운다, voice/audit/inspector.py)."""

    status: Literal["pass", "fail", "unchecked"]
    reason: str | None = None  # fail 일 때 담당에게 돌려줄 지적
    detail: dict = field(default_factory=dict)  # 기록용: criterion, quotes, calls


AuditFunc = Callable[[dict, Evidence, dict, RunContext], AuditVerdict]  # (1차를 통과한 제출 인자, 근거, task, 맥락)


@dataclass
class AgentSpec:
    name: str
    system_prompt: Callable[[dict, RunContext], str]
    user_message: Callable[[dict, RunContext], str]
    tools: list[Tool]
    submit: Tool
    check: CheckFunc  # 써도 되면 None, 안 되면 모델에게 돌려줄 거절 이유. notes 에 덧붙일 말을 넣을 수 있다
    task_id: Callable[[dict], str]
    fallback: Callable[[dict, RunContext], dict | None] | None = None  # 지금의 단일 호출. 실패하면 None
    finalize: Callable[[dict, dict, RunContext], dict] | None = None  # 통과한 제출 인자 → 제안 내용 (다듬기)
    budget: Budget = Budget()
    temperature: float = 0.3
    # 거절 메시지 끝에 붙이는 안내. {submit} 은 제출 도구 이름으로 바뀐다
    retry_hint: str = "이 부분만 고치고 나머지는 그대로 두어 {submit} 로 다시 제출해 줘."
    # 캐시 키 입력 해시에 더할 값. 도구가 읽는 task 칸처럼 user 메시지에 없지만 결과를 바꾸는 것 (JSON 으로 바꿀 수 있어야 한다).
    # None 이면(대부분의 에이전트) 예전과 같은 키를 쓴다
    cache_scope: Callable[[dict], object] | None = None
    # 시간 예산(마감)이 지난 뒤에도 물러나기(fallback)를 부를지. 사장님이 기다리는 에이전트는 False 로 둘 수 있다 (H7)
    fallback_after_deadline: bool = True
    # 2차 감사 자리: 1차 코드 검사(check)를 통과한 제출을 부를 함수. None 이면 지금과 같다 (메인 서버 하네스 에이전트)
    audit: AuditFunc | None = None
    audit_returns: int = 2  # 2차 불합격 뒤 같은 대화로 지적을 돌려줄 최대 횟수. 1차 거절(budget.max_rejections)과 따로 센다
    audit_seconds: float = 60.0  # 감사 한 회차의 상한. 넘으면 그 회차는 감사 못 함 (안전장치)

    def tool_schemas(self) -> list[dict]:
        return [tool.schema() for tool in self.tools] + [self.submit.schema()]

    def tool(self, name: str) -> Tool | None:
        return next((tool for tool in self.tools if tool.name == name), None)
