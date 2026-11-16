"""CLOVA X 심판. 생성된 답글(과 진단)이 조건 하나를 지키는지 묻고, 3번 물어 다수결로 정한다.

조건 (CONDITIONS, 조건마다 따로 부른다)
  fact         지어낸 가게 사정이 없다 (가게가 등록한 사실에 없는 재료·조리·영업 이야기, 손님들이 한다는 말, 이유 대기)
  policy       사장님이 정하지 않은 보상이 없고, 손님을 아는 척하지 않는다
  core         손님이 말한 불만·칭찬에 대답했다. 아무 리뷰에나 붙는 답이 아니다 (정답 답변을 참고로 준다)
  response     불만이 있으면 사과나 고칠 점이 있고, 변명·남 탓이 없다
  consistency  답글과 진단이 어긋나지 않는다 (진단 평가에서 쓴다)

보내는 것: 가게 업종, 메뉴 이름, 가게가 등록한 사실, 리뷰 글(mask_personal_info 를 거침), 분류 정답(감정, 불만 유형),
          공통 정책(prompts/judge_policy.txt), 생성 답글, core 에만 정답 답변("참고용 예시이며 표현이 달라도 된다"),
          consistency 에만 진단 글.
보내지 않는 것: 어느 시스템(A/B)이 썼는지, 손님 id, 주문 번호, 작성자, 사장님 답변일.

답 모양: {"ok": 예|아니오|판단 불가, "quotes": [답글에서 글자 그대로 옮긴 문제 문구], "reason": "…"}
  - ok 는 조건을 지키면 True, 어기면 False, 판단 불가면 None 으로 읽는다.
  - quotes 는 답글에 글자 그대로 있는 것만 남긴다(띄어쓰기 차이는 무시). ok=False 인데 준 문구가 하나도 답글에 없으면
    그 표는 버리고 한 번 더 묻는다. 두 번째도 그러면 그 표는 판단 불가.
    ok=False 이고 문구를 주지 않은 표는 받는다 (core·response 처럼 '빠진 것'이 문제인 경우는 옮길 문구가 없다).
  - 3표 중 과반이 같은 값이면 그 값, 아니면 판단 불가(None). 표는 모두 남긴다.

방식 (mode)
  tools     (기본) 추론을 끄고(thinking.effort = none) submit_judgement 도구를 강제한다. quote_judge 와 같은 모양.
            HCX-007 은 thinking 을 보내지 않으면 기본이 추론 켜짐(low)이라 function calling 과 부딪힌다.
            그래서 effort none 을 명시해서 보낸다. (CLOVA Studio 문서 2026-11-17 확인. 실제 요청 확인 결과는 아래 MODE_CHECK 에 적는다)
  thinking  추론을 켜고(effort THINKING_EFFORT) 도구 없이 JSON 하나만 답하게 한다. 답 끝의 JSON 을 읽고, 모양이 틀리면 한 번 더,
            또 틀리면 판단 불가. 추론 글은 저장하지 않고 토큰 수만 적는다. 추론 모델은 maxTokens 대신 maxCompletionTokens 를
            쓰고(최대 32,768, 추론과 답을 합친 수), function calling·stop 을 같이 쓸 수 없다.
  어느 방식을 쓸지는 심판 검증(변형 세트 놓침·오거절, 사람 표본 일치)으로 정하고 result.json 의 config.judge_mode 에 적는다.

MODE_CHECK: 실제 HCX-007 요청으로 tools 방식(effort none + 도구 강제)이 되는지는 아직 확인하지 않았다.

모델은 settings.eval_judge_model (기본 HCX-007). B 의 검토기(HCX-005)와 다른 모델이다.
호출이 400/404 로 MODEL_ERROR_LIMIT 번 이어서 실패하면 JudgeModelError 를 낸다. 조용히 다른 모델로 바꾸지 않는다.
사용 기록 이름은 eval_judge:<조건> 이다 (평가 실행 폴더의 clova_usage.db 에 남는다).
"""

import json
import re
import sqlite3
import threading
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.analysis.review.hcx_classifier import mask_personal_info
from app.core import clova_usage_log
from app.core.clova import Post
from app.core.config import settings
from Harness import clova_tools
from Harness.tools import array, obj, string

PROMPTS_DIR = Path(__file__).parent / "prompts"
POLICY_PROMPT = "judge_policy.txt"
JSON_ANSWER_PROMPT = "judge_json_answer.txt"

MODES = ("tools", "thinking")
VOTES = 3
TEMPERATURE = 0.3
MAX_ATTEMPTS = 2  # 표 하나를 얻으려고 묻는 최대 횟수 (모양이 틀리거나 문구가 답글에 없으면 한 번 더)
TOOLS_MAX_TOKENS = 1024  # function calling 하한
THINKING_EFFORT = "medium"
THINKING_MAX_TOKENS = 16384  # 추론 + 답. HCX-007 최대 32,768
TIMEOUT_SECONDS = 60
MODEL_ERROR_LIMIT = 3  # 400/404 가 이만큼 이어지면 멈춘다

ANSWERS = {"예": True, "아니오": False, "판단 불가": None}
QUOTE_MARKS = " \"'“”‘’"
SUBMIT_NAME = "submit_judgement"


class JudgeModelError(RuntimeError):
    """심판 모델 호출이 400/404 로 계속 실패한다. 모델 이름이나 요청 모양을 사람이 확인해야 한다."""


@dataclass(frozen=True)
class Condition:
    name: str
    prompt: str  # prompts/ 의 파일
    ask: str  # 사용자 메시지 끝에 붙는 질문
    gold_reply: bool = False  # 정답 답변을 참고로 주는지
    diagnosis: bool = False  # 진단 글을 주는지


CONDITIONS: dict[str, Condition] = {
    "fact": Condition("fact", "judge_cond_fact.txt", "이 답글이 가게 사정을 지어내지 않았는지 판정해 줘."),
    "policy": Condition("policy", "judge_cond_policy.txt", "이 답글이 사장님이 정하지 않은 보상을 약속하거나 손님을 아는 척하지 않았는지 판정해 줘."),
    "core": Condition("core", "judge_cond_core.txt", "이 답글이 손님이 리뷰에서 말한 내용에 대답했는지 판정해 줘.", gold_reply=True),
    "response": Condition("response", "judge_cond_response.txt", "이 답글이 불만에 알맞게 응대했는지 판정해 줘."),
    "consistency": Condition("consistency", "judge_cond_consistency.txt", "이 답글과 진단이 서로 어긋나지 않는지 판정해 줘.", diagnosis=True),
}
REPLY_CONDITIONS = ("fact", "policy", "core", "response")


@dataclass
class JudgeInput:
    """심판에게 줄 재료. 시스템 이름(A/B)은 넣지 않는다."""

    review_text: str
    reply: str
    category: str = ""  # 업종
    sentiment: str | None = None  # 분류 정답 (긍정, 부정, 혼합)
    complaint_types: list[str] = field(default_factory=list)
    menus: list[str] = field(default_factory=list)
    store_facts: list[str] = field(default_factory=list)
    gold_reply: str | None = None  # core 에만 보낸다
    diagnosis: str | None = None  # consistency 에만 보낸다
    owner_instruction: str | None = None  # 사장님 지시 (보상을 지시했으면 그 보상은 정책 위반이 아니다)


@dataclass
class Vote:
    ok: bool | None
    quotes: list[str] = field(default_factory=list)
    reason: str = ""
    error: str | None = None  # 표를 얻지 못한 까닭 (호출 실패, 모양 틀림, 문구가 답글에 없음)
    calls: int = 0
    tokens: list[int] = field(default_factory=lambda: [0, 0, 0])  # 입력, 출력, 그중 추론

    def as_dict(self) -> dict:
        return {"ok": self.ok, "quotes": self.quotes, "reason": self.reason, "error": self.error,
                "calls": self.calls, "tokens": self.tokens}


@dataclass
class Verdict:
    condition: str
    mode: str
    model: str
    votes: list[Vote]

    @property
    def ok(self) -> bool | None:
        return majority([vote.ok for vote in self.votes])

    @property
    def quotes(self) -> list[str]:
        """다수결이 False 일 때, False 를 낸 표들의 문구 (겹치면 하나만)."""
        if self.ok is not False:
            return []
        return list(dict.fromkeys(q for vote in self.votes if vote.ok is False for q in vote.quotes))

    @property
    def calls(self) -> int:
        return sum(vote.calls for vote in self.votes)

    @property
    def tokens(self) -> list[int]:
        return [sum(vote.tokens[i] for vote in self.votes) for i in range(3)]

    def as_dict(self) -> dict:
        """result.json cases[].verdicts[<조건>] 모양."""
        quotes = self.quotes
        return {"vote": [vote.ok for vote in self.votes], "ok": self.ok, "quote": quotes[0] if quotes else None,
                "quotes": quotes, "reasons": [vote.reason for vote in self.votes],
                "errors": [vote.error for vote in self.votes if vote.error], "mode": self.mode, "model": self.model,
                "calls": self.calls, "tokens": self.tokens}


def majority(values: Iterable[bool | None]) -> bool | None:
    """과반이 같은 값이면 그 값, 아니면 None. 판단 불가(None) 표도 한 표로 센다."""
    values = list(values)
    if not values:
        return None
    value, count = Counter(values).most_common(1)[0]
    return value if count * 2 > len(values) else None


# ── 프롬프트와 메시지 ──


def load_prompt(name: str, category: str) -> str:
    """prompts/<name> 을 읽어 {업종}, {공통정책} 을 채운다. 매번 읽으므로 고치면 바로 반영된다."""
    text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
    if "{공통정책}" in text:
        text = text.replace("{공통정책}", (PROMPTS_DIR / POLICY_PROMPT).read_text(encoding="utf-8").strip())
    return text.replace("{업종}", category or "음식점")


def system_prompt(condition: Condition, mode: str, category: str) -> str:
    text = load_prompt(condition.prompt, category)
    if mode == "thinking":
        text = text.rstrip() + "\n\n" + load_prompt(JSON_ANSWER_PROMPT, category)
    return text


def _quoted(text: str) -> str:
    return '"' + " ".join(text.split()) + '"'


def user_message(condition: Condition, judge_input: JudgeInput) -> str:
    facts = judge_input.store_facts
    rows = [
        "[가게]",
        f"메뉴: {', '.join(judge_input.menus) if judge_input.menus else '없음'}",
        "가게가 등록한 사실:" + ("".join(f"\n- {fact}" for fact in facts) if facts else " 없음"),
        "",
        "[리뷰]",
        _quoted(mask_personal_info(judge_input.review_text)),
        f"분류 정답: 감정 {judge_input.sentiment or '모름'}, 불만 유형 {', '.join(judge_input.complaint_types) or '없음'}",
    ]
    if judge_input.owner_instruction:
        rows += ["", "[사장님 지시]", _quoted(judge_input.owner_instruction)]
    if condition.gold_reply and judge_input.gold_reply:
        rows += ["", "[참고 답변] 실제 사장님이 쓴 답이야. 참고용 예시이며 표현이 달라도 된다.",
                 _quoted(mask_personal_info(judge_input.gold_reply))]
    if condition.diagnosis:
        rows += ["", "[진단]", _quoted(judge_input.diagnosis or "")]
    rows += ["", "[답글]", _quoted(judge_input.reply), "", condition.ask]
    return "\n".join(rows)


def submit_tool() -> dict:
    return {"type": "function", "function": {
        "name": SUBMIT_NAME,
        "description": "판정 결과를 제출한다",
        "parameters": obj({
            "ok": string("조건을 지키면 예, 어기면 아니오, 주어진 것만으로 정할 수 없으면 판단 불가", list(ANSWERS)),
            "quotes": array(string("답글에서 문제가 되는 부분을 글자 그대로"), "문제 문구들. 없으면 빈 목록"),
            "reason": string("판정 까닭 한두 문장"),
        }),
    }}


# ── 답 읽기 ──


def _squash(text: str) -> str:
    return " ".join(text.split())


def read_ok(value: object) -> tuple[bool, bool | None]:
    """(읽었는지, 값). 예/아니오/판단 불가 와 true/false/null 을 모두 받는다."""
    if value is None or isinstance(value, bool):
        return True, value
    if isinstance(value, str):
        text = value.strip()
        if text in ANSWERS:
            return True, ANSWERS[text]
        lowered = text.lower()
        if lowered in ("true", "false", "null"):
            return True, {"true": True, "false": False, "null": None}[lowered]
    return False, None


def parse_answer(arguments: object, reply: str) -> tuple[Vote | None, str | None]:
    """도구 인자나 JSON 답을 표로 바꾼다. (표, 다시 물을 까닭). 표가 None 이면 까닭이 있다."""
    if not isinstance(arguments, dict) or "ok" not in arguments:
        return None, "답 모양이 틀림 (ok 가 없음)"
    readable, ok = read_ok(arguments["ok"])
    quotes = arguments.get("quotes", [])
    if not readable or not isinstance(quotes, list):
        return None, "답 모양이 틀림"
    squashed = _squash(reply)
    given = [q for q in (_squash(str(q)).strip(QUOTE_MARKS) for q in quotes) if q]
    kept = list(dict.fromkeys(q for q in given if q in squashed))
    if ok is False and given and not kept:
        return None, f"옮긴 문구 {given} 가 답글에 글자 그대로 없음"
    reason = arguments.get("reason")
    return Vote(ok=ok, quotes=kept if ok is False else [], reason=reason if isinstance(reason, str) else ""), None


FENCE_RE = re.compile(r"```(?:json)?\s*$|^\s*```(?:json)?", re.MULTILINE)


def last_json(text: str) -> dict | None:
    """답 끝에 있는 JSON 객체. 코드 울타리(```)는 무시한다. 없으면 None."""
    cleaned = FENCE_RE.sub("", text or "").rstrip()
    decoder = json.JSONDecoder()
    for start in (i for i in range(len(cleaned) - 1, -1, -1) if cleaned[i] == "{"):
        try:
            value, end = decoder.raw_decode(cleaned, start)
        except ValueError:
            continue
        if isinstance(value, dict) and not cleaned[end:].strip():  # raw_decode 의 end 는 글 전체 기준 위치
            return value
    return None


# ── 모델 오류 감시 ──

_errors_lock = threading.Lock()
_model_errors = 0


def reset_model_errors() -> None:
    global _model_errors
    with _errors_lock:
        _model_errors = 0


def _last_http_status() -> int | None:
    call_id = clova_tools.last_call_id()
    if call_id is None or not Path(clova_usage_log.LOG_PATH).exists():
        return None
    with sqlite3.connect(clova_usage_log.LOG_PATH) as conn:
        row = conn.execute("SELECT http_status FROM calls WHERE id = ?", (call_id,)).fetchone()
    return row[0] if row else None


def _note_call(failed: bool, model: str) -> None:
    """호출 결과를 센다. 400/404 가 MODEL_ERROR_LIMIT 번 이어지면 JudgeModelError."""
    global _model_errors
    status = _last_http_status() if failed else None
    with _errors_lock:
        if failed and status in (400, 404):
            _model_errors += 1
            count = _model_errors
        else:
            _model_errors = 0
            count = 0
    if count >= MODEL_ERROR_LIMIT:
        raise JudgeModelError(
            f"심판 모델 {model} 호출이 {count}번 이어서 {status} 로 실패했어요. 모델 이름(EVAL_JUDGE_MODEL)과 요청 모양을 확인해 주세요."
        )


# ── 묻기 ──


def _ask(messages: list[dict], condition: Condition, mode: str, model: str, store_id: str | None, post: Post):
    if mode == "tools":
        return clova_tools.chat_with_tools(
            messages, [submit_tool()], tool_choice={"type": "function", "function": {"name": SUBMIT_NAME}},
            max_tokens=TOOLS_MAX_TOKENS, temperature=TEMPERATURE, timeout=TIMEOUT_SECONDS, post=post,
            feature=f"eval_judge:{condition.name}", store_id=store_id, model=model, thinking_effort="none", log_prefix="",
        )
    return clova_tools.chat_with_tools(
        messages, [], max_tokens=THINKING_MAX_TOKENS, temperature=TEMPERATURE, timeout=TIMEOUT_SECONDS, post=post,
        feature=f"eval_judge:{condition.name}", store_id=store_id, model=model, thinking_effort=THINKING_EFFORT, log_prefix="",
    )


def one_vote(condition: Condition, judge_input: JudgeInput, *, mode: str, model: str, store_id: str | None, post: Post) -> Vote:
    """표 하나. 모양이 틀리거나 문구가 답글에 없으면 한 번 더 묻고, 그래도 안 되면 판단 불가 표."""
    messages = [
        {"role": "system", "content": system_prompt(condition, mode, judge_input.category)},
        {"role": "user", "content": user_message(condition, judge_input)},
    ]
    calls, tokens, why = 0, [0, 0, 0], None
    for _ in range(MAX_ATTEMPTS):
        answer = _ask(messages, condition, mode, model, store_id, post)
        call_id = clova_tools.last_call_id()
        calls += 1
        _note_call(answer is None, model)
        if answer is None:
            return Vote(ok=None, error="호출 실패", calls=calls, tokens=tokens)
        tokens = [tokens[0] + (answer.input_tokens or 0), tokens[1] + (answer.output_tokens or 0),
                  tokens[2] + (getattr(answer, "thinking_tokens", None) or 0)]
        if mode == "tools":
            call = next((c for c in answer.tool_calls if c.name == SUBMIT_NAME), None)
            vote, why = parse_answer(call.arguments if call else None, judge_input.reply)
        else:
            call = None
            vote, why = parse_answer(last_json(answer.content), judge_input.reply)
        clova_tools.mark_verdict(call_id, vote is not None, why)
        if vote is not None:
            vote.calls, vote.tokens = calls, tokens
            return vote
        if call is not None:
            messages = [*messages, answer.as_assistant_message(), {"role": "tool", "toolCallId": call.id, "content": (
                f"{why}. 답글에서 글자 그대로 다시 옮겨 {SUBMIT_NAME} 로 내 줘. 옮길 문구가 없으면 quotes 를 빈 목록으로 내.")}]
        elif mode == "thinking":
            messages = [*messages, {"role": "assistant", "content": answer.content or ""}, {"role": "user", "content": (
                f"{why}. 설명 없이 JSON 하나만 다시 답해 줘. 문제 문구는 답글에서 글자 그대로 옮겨.")}]
    return Vote(ok=None, error=why, calls=calls, tokens=tokens)


def judge(condition: str, judge_input: JudgeInput, *, mode: str = "tools", votes: int = VOTES, model: str | None = None,
          store_id: str | None = None, post: Post = httpx.post) -> Verdict:
    """조건 하나를 votes 번 물어 다수결한 판정."""
    if mode not in MODES:
        raise ValueError(f"모르는 심판 방식: {mode} ({', '.join(MODES)})")
    spec = CONDITIONS[condition]
    model = model or settings.eval_judge_model
    if not judge_input.reply.strip():
        return Verdict(condition, mode, model, [Vote(ok=False, reason="빈 답글", error=None) for _ in range(votes)])
    return Verdict(condition, mode, model, [
        one_vote(spec, judge_input, mode=mode, model=model, store_id=store_id, post=post) for _ in range(votes)
    ])


def judge_all(judge_input: JudgeInput, conditions: Iterable[str] = REPLY_CONDITIONS, **options) -> dict[str, Verdict]:
    """여러 조건을 차례로 판정한다. 결과는 조건 이름 → Verdict."""
    return {name: judge(name, judge_input, **options) for name in conditions}
