"""마케팅 피드·캡션 작성 사원: 고른 소재로 인스타 글과 해시태그를 쓴다 (에이전트 조직 개편 6-2, agent-org-plan.md).

가게 정보 줄(가게 이름·주소, 영업시간, 내일 쉬는 날)은 지어내면 안 되는 정보라 여기서 쓰지 않는다. instagram/posts.py 가 붙인다.
검사: 본문 길이, 해시태그 8개 이하이고 # 한 낱말 꼴, 가격·할인·약속 금지, 숫자는 입력·도구 결과에 있는 것만,
손님 한마디를 넣었으면 리뷰 글자 그대로. 실패하거나 끄면 None (지금 템플릿 글을 쓴다).
"""

import re

from Harness import guards, runner
from Harness.grounding import Evidence, ungrounded_numbers
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import array, obj, string
from voice import config
from voice.agents import load_prompt
from voice.context import VoiceStore, run_context

MIN_BODY, MAX_BODY = 20, 300
MAX_TAGS = 8
TAG_RE = re.compile(r"^#[\w가-힣]+$")
QUOTED_RE = re.compile(r"[“\"]([^”\"]+)[”\"]")

SUBMIT = Tool("submit_caption", "인스타 글과 해시태그", obj({
    "body": string("인스타 글 본문 (가게 주소·영업시간은 쓰지 마. 따로 붙는다)"),
    "hashtags": array(string("#으로 시작하는 해시태그 한 낱말"), f"해시태그 {MAX_TAGS}개 이하"),
}))


def user_message(task: dict, ctx: RunContext) -> str:
    rows = [f"올릴 메뉴: {', '.join(task['menus'])}", f"이야기: {task['angle']}"]
    if task.get("quote"):
        rows.append(f'손님 한마디(쓰려면 글자 그대로): "{task["quote"]}"')
    return "\n".join(rows) + "\n인스타 글과 해시태그를 submit_caption 으로 내 줘."


def check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    body = (args.get("body") or "").strip()
    tags = [str(t).strip() for t in args.get("hashtags") or []]
    if not MIN_BODY <= len(body) <= MAX_BODY:
        return f"본문은 {MIN_BODY}~{MAX_BODY}자로 써 주세요 (지금 {len(body)}자)"
    if len(tags) > MAX_TAGS or any(not TAG_RE.match(t) for t in tags):
        return f"해시태그는 #으로 시작하는 한 낱말로 {MAX_TAGS}개까지만 써 주세요"
    reason = guards.first(guards.price_or_discount(body), guards.promise(body))
    if reason:
        return reason
    loose = ungrounded_numbers(body, evidence)
    if loose:
        return f"입력에 없는 숫자를 썼어요: {', '.join(dict.fromkeys(loose))}"
    quoted = [q for q in QUOTED_RE.findall(body) if q.strip()]
    if quoted and any(q.strip() != (task.get("quote") or "") for q in quoted):
        return "따옴표 안의 손님 한마디는 주어진 글자 그대로만 쓸 수 있어요"
    return None


SPEC = AgentSpec(
    name="voice_caption_writer",
    system_prompt=lambda task, ctx: load_prompt("caption_writer.txt", ctx.store),
    user_message=user_message,
    tools=[],
    submit=SUBMIT,
    check=check,
    task_id=lambda task: f"{task['angle']}|{'|'.join(task['menus'])}",
    budget=Budget(max_steps=3, max_rejections=2, max_seconds=30),
    temperature=0.6,
)


def write(view: VoiceStore, menus: list[str], angle: str, quote: str | None) -> dict | None:
    """{body, hashtags} 또는 None."""
    if not config.agent_on("caption"):
        return None
    proposal = runner.run(SPEC, {"menus": menus, "angle": angle, "quote": quote}, run_context(view))
    if proposal is None or proposal.source != "AGENT":
        return None
    return {"body": proposal.content["body"].strip(), "hashtags": [str(t).strip() for t in proposal.content.get("hashtags") or []]}
