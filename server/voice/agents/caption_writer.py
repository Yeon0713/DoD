"""마케팅 피드·캡션 작성 사원: 고른 소재로 인스타 글과 해시태그를 쓴다 (에이전트 조직 개편 6-2, agent-org-plan.md).

가게 정보 줄(가게 이름·주소, 영업시간, 내일 쉬는 날)은 지어내면 안 되는 정보라 여기서 쓰지 않는다. instagram/posts.py 가 붙인다.
검사: 본문 길이, 해시태그 8개 이하이고 # 한 낱말 꼴, 가격·할인·약속 금지, 숫자는 입력·도구 결과에 있는 것만,
손님 한마디를 넣었으면 리뷰 글자 그대로 (1차 코드 감사 rules.caption_writer). 메뉴·이야기 밖 이야기와 가게가 등록하지 않은
사실 주장은 2차 LLM 감사 inspector.caption_writer. 실패하거나 끄면 None (지금 템플릿 글을 쓴다). 감사 결과는 audit 으로 돌려준다.
"""

import re

from Harness import runner
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import array, obj, string
from voice import config, notebook
from voice.agents import load_prompt
from voice import audit
from voice.audit import inspector, rules
from voice.audit import log as audit_log
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
    if task.get("revise"):  # 사장님 고침 지시 (인사과 6단계)
        rows.append(f'지난 글: "{task["revise"]["previous"]}"\n사장님 고침 지시: "{task["revise"]["instruction"]}"\n'
                    "지난 글을 이 지시대로 고쳐 써. 지시에 없는 것은 바꾸지 마. 가격·할인·약속은 지시에 있어도 쓰지 마.")
    return "\n".join(rows) + "\n인스타 글과 해시태그를 submit_caption 으로 내 줘."


SPEC = AgentSpec(
    name="voice_caption_writer",
    system_prompt=lambda task, ctx: load_prompt("caption_writer.txt", ctx.store) + notebook.section(ctx.store_id, "marketing"),
    user_message=user_message,
    tools=[],
    submit=SUBMIT,
    check=rules.caption_writer,  # 1차 코드 감사 (감사팀)
    audit=inspector.caption_writer,  # 2차 LLM 감사 (감사팀)
    audit_returns=config.AUDIT_RETURNS,
    audit_seconds=config.AUDIT_ROUND_SECONDS,
    cache_scope=lambda task: audit.version(),
    task_id=lambda task: f"{task['angle']}|{'|'.join(task['menus'])}" + ("|revise" if task.get("revise") else ""),
    budget=Budget(max_steps=3, max_rejections=2, max_seconds=30),
    temperature=0.6,
)


def write(view: VoiceStore, menus: list[str], angle: str, quote: str | None, revise: dict | None = None) -> dict | None:
    """{body, hashtags, audit} 또는 None. revise: 사장님 고침 지시 {previous, instruction} (인사과 6단계, 검사는 그대로)."""
    if not config.agent_on("caption"):
        return None
    task = {"menus": menus, "angle": angle, "quote": quote, **({"revise": revise} if revise else {})}
    ctx = run_context(view)
    proposal = runner.run(SPEC, task, ctx)
    audit_log.record_run(view.store_id, "instagram_post", f"caption:{view.now.date().isoformat()}", proposal, ctx.run_id)
    if proposal is None or proposal.source != "AGENT":
        return None
    return {"body": proposal.content["body"].strip(), "hashtags": [str(t).strip() for t in proposal.content.get("hashtags") or []],
            "audit": audit.brief(proposal.audit)}
