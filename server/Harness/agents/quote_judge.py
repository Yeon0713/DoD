"""좁은 질문 하나만 LLM 에게 묻고, 답글에서 해당하는 부분을 글자 그대로 받는다. 판정은 부르는 쪽 코드가 한다.

- 보낼 모양: 리뷰: "…" / 답글: "…" / 질문 한 줄. 답은 found(해당 부분이 있는지)와 quotes(답글에서 글자 그대로).
- 질문(QUESTIONS)마다 프롬프트 파일이 따로 있다.
  compensation: 보상 제안이 있는지 (써도 되는지는 코드가 사장님 지시를 보고 정한다)
  fix: 리뷰의 불만을 고치겠다고 한 부분이 있는지 (없으면 코드가 거절한다)
  store_claim: 가게 사정(원래 어떻다, 이미 했다, 손님들이 무슨 말을 한다)을 말한 부분 (가게가 등록한 사실에 없으면 코드가 거절한다)
  owner_compensation: 사장님 지시에 보상을 주라는 내용이 있는지 (답글이 아니라 지시문을 검증한다)
  excuse: 문제의 원인을 대거나 남(배달앱, 기사, 손님 입맛)에게 돌린 부분 (앞으로 하겠다는 말이 아니면 코드가 거절한다)
  unasked: 손님이 리뷰에서 말하지 않은 이야기를 꺼낸 부분 (감사·사과 인사와 앞으로 하겠다는 말을 빼고 남으면 코드가 거절한다)
  memory: 손님을 아는 척한 부분 (단골에게 다시 찾아 준 것을 고마워하는 말 말고는 코드가 거절한다)
- 왜 나눠 묻는가: 기준 여러 개를 한 번에 판정하게 했더니, 사장님 지시가 없는데 "지시가 있으면 보상 허용"을 적용하거나
  고칠 점이 있는 답글을 "고칠 점이 없다"고 거절했다. 하나만 물으면 이런 섞임이 줄어든다.
- 리뷰를 함께 주는 까닭: 답글만 주었더니 "다음에는 꼭 제맛으로 드릴게요"(싱겁다는 불만에 대한 다짐)를 보상으로 골랐다.
- quote 가 답글에 글자 그대로 없으면 버린다. 있다면서 쓸 수 있는 quote 가 없으면 모양이 틀린 답으로 보고 한 번 더 묻는다.
- 호출이 실패하거나 모양이 두 번 틀리면 None 을 돌려준다. 부르는 쪽이 대신할 방법(정규식 등)을 정한다.
- ask 는 이름(QUESTIONS) 대신 Question 객체도 받는다. 음성 백엔드 감사팀의 질문은 그쪽에 둔다 (voice/audit/questions.py).
  그때 prompt 는 프롬프트 파일의 절대 경로이고, context 는 첫 줄에서 함께 주는 글(리뷰, 근거, 메뉴 …)의 이름이다.
"""

import re
from dataclasses import dataclass

from Harness import cache, clova_tools, trace
from Harness.spec import RunContext, Tool
from Harness.tools import array, load_prompt, obj, string

MAX_ATTEMPTS = 2
SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]*")
QUOTE_MARKS = " \"'“”‘’"


@dataclass(frozen=True)
class Question:
    name: str  # 기록(trace, 사용 기록)에 남는 이름
    prompt: str  # Harness/prompts/ 의 파일
    ask: str  # 사용자 메시지 끝에 붙는 질문
    found: str  # found 필드 설명
    quote: str  # quotes 필드 설명
    subject: str = "답글"  # 사용자 메시지에서 검증할 글을 부르는 이름
    context: str = "리뷰"  # 사용자 메시지 첫 줄에 함께 주는 글(ask 의 review_text)을 부르는 이름
    # False 면 found 만 본다: 참이면 검증한 글 전체를 옮긴 것으로 친다. 행동 하나처럼 짧은 글에 예·아니오만 물을 때
    # (모델이 함께 준 글 쪽을 옮겨 와 글자 그대로 검사에 걸리는 일을 막는다, 감사팀 2026-11-22)
    needs_quote: bool = True


QUESTIONS = {
    "compensation": Question(
        "compensation_judge", "compensation_judge.txt", "이 답글에 보상 제안이 있는지 검증해 줘.",
        "답글에 보상 제안이 있으면 true", "답글에서 보상을 제안한 부분을 글자 그대로",
    ),
    "fix": Question(
        "fix_judge", "fix_judge.txt", "이 답글이 리뷰의 불만을 고치겠다고 말했는지 검증해 줘.",
        "리뷰의 불만을 고치겠다고 한 부분이 있으면 true", "답글에서 고치겠다고 한 부분을 글자 그대로",
    ),
    "owner_compensation": Question(
        "owner_compensation_judge", "owner_compensation_judge.txt", "이 지시에 손님에게 보상을 주라는 내용이 있는지 검증해 줘.",
        "지시에 손님에게 보상을 주라는 내용이 있으면 true", "지시에서 보상을 주라고 한 부분을 글자 그대로", subject="사장님 지시",
    ),
    "store_claim": Question(
        "store_claim_judge", "store_claim_judge.txt", "이 답글에 가게 사정을 말한 부분이 있는지 검증해 줘.",
        "답글에 가게 사정을 말한 부분이 있으면 true", "답글에서 가게 사정을 말한 부분을 글자 그대로",
    ),
    "excuse": Question(
        "excuse_judge", "excuse_judge.txt", "이 답글에 변명하거나 남 탓을 한 부분이 있는지 검증해 줘.",
        "답글에 변명하거나 남 탓을 한 부분이 있으면 true", "답글에서 변명하거나 남 탓을 한 부분을 글자 그대로",
    ),
    "unasked": Question(
        "unasked_judge", "unasked_judge.txt", "이 답글에 손님이 리뷰에서 말하지 않은 이야기를 꺼낸 부분이 있는지 검증해 줘.",
        "손님이 리뷰에서 말하지 않은 이야기를 꺼낸 부분이 있으면 true", "답글에서 리뷰에 없는 이야기를 꺼낸 부분을 글자 그대로",
    ),
    "memory": Question(
        "memory_judge", "memory_judge.txt", "이 답글에 손님을 아는 척한 부분이 있는지 검증해 줘.",
        "답글에 손님을 아는 척한 부분이 있으면 true", "답글에서 손님을 아는 척한 부분을 글자 그대로",
    ),
    # 알바생 할 일 (voice/agents/fix_card.py, 2026-11-20): 알바생이 지금 매장에 있는 것으로 할 수 없는 일
    "staff_scope": Question(
        "staff_scope_judge", "staff_scope_judge.txt", "이 할 일에 알바생이 할 수 없는 일이 있는지 검증해 줘.",
        "알바생이 할 수 없는 일이 있으면 true", "할 일에서 알바생이 할 수 없는 부분을 글자 그대로", subject="할 일",
    ),
}


def submit_tool(question: Question) -> Tool:
    return Tool(
        "submit_judgement",
        "답글 검증 결과를 제출한다",
        obj({
            "found": {"type": "boolean", "description": question.found},
            "quotes": array(string(question.quote), "해당하는 부분들. 없으면 빈 목록"),
        }),
    )


def alt_tool(question: Question) -> Tool:
    """400 일 때 다시 물을 다른 모양: found 없이 quotes 만 (비어 있으면 없음)."""
    return Tool("submit_judgement", "답글 검증 결과를 제출한다",
                obj({"quotes": array(string(question.quote), "해당하는 부분들. 없으면 빈 목록")}))


def sentences(text: str) -> list[str]:
    """정규식으로 대신 거를 때 문장 단위로 보여 주려고 쓴다."""
    return [part.strip() for part in SENTENCE_RE.findall(text) if part.strip()]


def _squash(text: str) -> str:
    return " ".join(text.split())


def parse(arguments: dict, reply: str, needs_quote: bool = True) -> list[str] | None:
    """해당하는 부분들. 없으면 빈 목록, 모양이 틀리면 None. needs_quote 가 False 면 참일 때 [reply]."""
    quotes = arguments.get("quotes")
    found = arguments.get("found", bool(quotes) if isinstance(quotes, list) else None)  # 다른 모양(alt_tool)은 found 가 없다
    if not isinstance(found, bool) or not isinstance(quotes, list):
        return None
    if not found:
        return []
    if not needs_quote:
        return [reply.strip()]
    squashed = _squash(reply)
    kept = [q for q in (_squash(str(q)).strip(QUOTE_MARKS) for q in quotes) if q and q in squashed]
    return list(dict.fromkeys(kept)) or None


def user_message(question: Question, reply: str, review_text: str | None) -> str:
    rows = [f'{question.context}: "{review_text}"'] if review_text else []
    rows += [f'{question.subject}: "{reply}"', "", question.ask]
    return "\n".join(rows)


def ask(kind: "str | Question", reply: str, ctx: RunContext, review_text: str | None = None) -> list[str] | None:
    """답글에서 질문에 해당하는 부분들. 없으면 빈 목록, 묻지 못했으면 None. review_text 는 답글이 대답한 리뷰 글
    (Question.context 가 다르면 그 이름의 글). kind 는 QUESTIONS 의 이름 또는 Question."""
    if not reply.strip():
        return []
    question = kind if isinstance(kind, Question) else QUESTIONS[kind]
    submit = submit_tool(question)
    messages = [
        {"role": "system", "content": load_prompt(question.prompt, ctx.store)},
        {"role": "user", "content": user_message(question, reply, review_text)},
    ]
    force = {"type": "function", "function": {"name": submit.name}}
    # 같은 질문·같은 답글이면 앞서 받은 판정을 쓴다 (Harness/cache.py: 서버를 다시 켜도 파일에 남는다)
    key = (question.name, ctx.store_id, cache.digest([messages[1]["content"]]), cache.digest(messages[0]["content"]))
    remembered = cache.get(key)
    if isinstance(remembered, list):
        return list(remembered)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if ctx.call_budget is not None and not ctx.call_budget.take():
            return None
        answer = clova_tools.chat_with_tools(
            messages, [submit.schema()], tool_choice=force, temperature=0, feature=question.name, store_id=ctx.store_id, post=ctx.post,
            alt_tools=[alt_tool(question).schema()],
        )
        call_id = clova_tools.last_call_id()
        if answer is None:
            trace.record(run_id=ctx.run_id, parent_run_id=ctx.parent_run_id, agent=question.name, store_id=ctx.store_id,
                         step=attempt, kind="llm", name="failed")
            return None
        call = next((c for c in answer.tool_calls if c.name == submit.name), None)
        quotes = parse(call.arguments, reply, question.needs_quote) if call else None
        clova_tools.mark_verdict(call_id, quotes is not None, None if quotes is not None else "검증 답 모양이 틀림")
        trace.record(run_id=ctx.run_id, parent_run_id=ctx.parent_run_id, agent=question.name, store_id=ctx.store_id, step=attempt,
                     kind="submit", name=submit.name, detail=quotes if quotes is not None else (call.arguments if call else None))
        if quotes is not None:
            cache.put(key, list(quotes))
            return quotes
        if call is not None:  # 있다면서 답글에 없는 말을 옮겼다. 알려 주고 다시 받는다
            messages = [*messages, answer.as_assistant_message(), {"role": "tool", "toolCallId": call.id, "content": (
                f"옮긴 부분 {call.arguments.get('quotes')} 가 {question.subject}에 글자 그대로 없어요. "
                f"{question.subject}에서 글자 그대로 다시 옮겨 {submit.name} 로 내 줘. 해당하는 부분이 없으면 found 를 false 로 내.")}]
    return None
