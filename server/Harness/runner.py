"""도구 호출 루프.

핵심은 최종 답도 도구(submit_*)로 받는 것이다. 제출이 검사에 걸리면 거절 이유를 tool 메시지로 돌려주고 루프를 이어 간다.
(기존 코드는 거절되면 이유를 말하지 않고 temperature 만 낮춰 다시 물어 같은 실수가 반복됐다)

1. 캐시를 본다. 같은 (에이전트, 가게, 입력 해시, 프롬프트 버전)이 있으면 바로 돌려준다.
2. system(프롬프트) + user(이번 일의 사실) + tools(조회 도구 + 제출 도구)로 CLOVA 를 부른다. toolChoice: auto
3. 응답에 따라
   - 조회 도구 호출: 파이썬 함수를 실행해 결과를 {"role": "tool", "toolCallId", "content"} 로 붙이고 근거 장부에도 적는다
   - 제출 도구 호출: 검사기 → 근거 대조. 통과하면 Proposal 로 끝, 걸리면 "거절: <이유>" 를 tool 메시지로 보낸다
   - 도구 없이 글만 옴: "submit 도구로 제출하라"를 한 번 붙이고 다음 요청은 toolChoice 로 제출 도구를 강제한다. 두 번째면 실패
   - 같은 조회 도구를 같은 인자로 다시 부름: 다시 실행하지 않고 "이미 조회했어요"를 돌려준다.
     한 응답의 조회가 모두 되풀이였으면 다음 요청은 제출을 강제한다 (실제 CLOVA 가 같은 조회를 반복하다 예산을 다 쓴 일이 있었다)
   - 마지막 단계는 언제나 제출을 강제한다
   - length 로 끝남: 실패
4. 예산(최대 단계, 거절 횟수, 시간, 함께 쓰는 호출 수)을 넘기면 멈추고 spec.fallback(지금의 단일 호출)을 부른다.
   그것도 실패하면 None 이고, 화면은 기본 문장을 쓴다.
5. 단계마다 trace 에 기록하고, 통과한 제안은 캐시에 넣는다.
"""

import json
import logging
import time
from functools import partial

from Harness import cache, clova_tools, trace
from Harness.grounding import Evidence
from Harness.spec import AgentSpec, Proposal, RunContext
from Harness.tools import to_content

logger = logging.getLogger(__name__)

clock = time.monotonic  # 테스트에서 바꾼다
MIN_CALL_SECONDS = 0.5  # 엄격한 예산(Budget.strict)에서 남은 시간이 거의 없어도 호출 하나에 주는 최소 시간


def cache_key(spec: AgentSpec, task: dict, ctx: RunContext, system: str, user: str) -> tuple[str, str, str, str]:
    return (spec.name, ctx.store_id, cache.digest([user, ctx.store_facts]), cache.digest(system))


def run(spec: AgentSpec, task: dict, ctx: RunContext) -> Proposal | None:
    task_id = spec.task_id(task)
    system = spec.system_prompt(task, ctx)
    user = spec.user_message(task, ctx)
    log = partial(trace.record, run_id=ctx.run_id, parent_run_id=ctx.parent_run_id, agent=spec.name, store_id=ctx.store_id)

    log(step=0, kind="start", name=task_id)  # 개발자 대시보드가 '지금 도는 실행'과 맡은 일을 이 줄로 안다
    key = cache_key(spec, task, ctx, system, user)
    cached = cache.get(key)
    if isinstance(cached, Proposal):
        log(step=0, kind="cache", name=task_id)
        return cached

    messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    evidence = Evidence([user])
    rejections, nudged, force_submit, started = 0, False, False, clock()
    seen_calls: set[str] = set()
    submit_only = {"type": "function", "function": {"name": spec.submit.name}}

    for step in range(1, spec.budget.max_steps + 1):
        if clock() - started > spec.budget.max_seconds:
            log(step=step, kind="end", name="time_budget")
            break
        if ctx.call_budget is not None and not ctx.call_budget.take():
            log(step=step, kind="end", name="call_budget")
            break
        # 글로만 답했거나, 조회만 되풀이했거나, 마지막 단계면 제출 도구를 강제한다
        forced = force_submit or step == spec.budget.max_steps
        strict = spec.budget.strict
        reply = clova_tools.chat_with_tools(
            messages, spec.tool_schemas(), feature=spec.name, store_id=ctx.store_id,
            tool_choice=submit_only if forced else "auto", temperature=spec.temperature, post=ctx.post,
            **({"timeout": max(MIN_CALL_SECONDS, spec.budget.max_seconds - (clock() - started)), "retry": False}
               if strict else {}),
        )
        call_id = clova_tools.last_call_id()
        if reply is None:
            log(step=step, kind="llm", name="failed")
            break
        log(step=step, kind="llm", name=reply.finish_reason + (" (submit 강제)" if forced else ""),
            detail=[{"tool": c.name, "args": c.arguments} for c in reply.tool_calls] or reply.content)
        if not reply.tool_calls:
            if reply.finish_reason == "length" or nudged:
                break
            nudged = force_submit = True
            messages.append(reply.as_assistant_message())
            messages.append({"role": "user", "content": f"답은 반드시 {spec.submit.name} 도구로 제출해 줘."})
            continue

        messages.append(reply.as_assistant_message())
        lookups = [c for c in reply.tool_calls if c.name != spec.submit.name]
        repeats = 0
        for call in reply.tool_calls:
            if call.name == spec.submit.name:
                notes: list[str] = []
                missing = spec.submit.missing(call.arguments)
                reason = f"빠진 값이 있어요: {', '.join(missing)}" if missing else _check(spec, call.arguments, evidence, task, ctx, notes)
                clova_tools.mark_verdict(call_id, reason is None, reason)
                log(step=step, kind="submit", name=spec.submit.name, detail={"accepted": reason is None, "reason": reason})
                if reason is None:
                    content = spec.finalize(call.arguments, task, ctx) if spec.finalize else dict(call.arguments)
                    proposal = Proposal(spec.name, task_id, content, "AGENT", ctx.run_id, evidence.sources(), notes)
                    cache.put(key, proposal)
                    log(step=step, kind="end", name="accepted")
                    return proposal
                rejections += 1
                result = f"거절: {reason}\n{spec.retry_hint.format(submit=spec.submit.name)}"
            else:
                signature = f"{call.name}:{json.dumps(call.arguments, ensure_ascii=False, sort_keys=True, default=str)}"
                if signature in seen_calls:
                    repeats += 1
                    result = f"이미 같은 값으로 조회했어요. 앞의 결과를 쓰고, 다 봤으면 {spec.submit.name} 로 제출해 줘."
                else:
                    seen_calls.add(signature)
                    result = _run_tool(spec, call.name, call.arguments, task, ctx, evidence)
                log(step=step, kind="tool", name=call.name, detail={"args": call.arguments, "result": result})
            messages.append({"role": "tool", "toolCallId": call.id, "content": result})
        if lookups and repeats == len(lookups):  # 새로 본 것이 없으면 다음엔 제출하게 한다
            force_submit = True
        if rejections >= spec.budget.max_rejections:
            log(step=step, kind="end", name="too_many_rejections")
            break

    return _fallback(spec, task, ctx, task_id, log)


def _check(spec: AgentSpec, args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    try:
        return spec.check(args, evidence, task, ctx, notes)
    except Exception as error:  # 검사기가 모양이 틀린 인자로 터지면 그 사실을 모델에게 알린다
        logger.exception("%s 검사 실패", spec.name)
        return f"제출 모양이 틀렸어요 ({type(error).__name__})"


def _run_tool(spec: AgentSpec, name: str, args: dict, task: dict, ctx: RunContext, evidence: Evidence) -> str:
    tool = spec.tool(name)
    if tool is None or tool.func is None:
        names = ", ".join([t.name for t in spec.tools] + [spec.submit.name])
        return f"오류: '{name}' 도구는 없어요. 쓸 수 있는 도구: {names}"
    missing = tool.missing(args)
    if missing:
        return f"오류: 빠진 값이 있어요: {', '.join(missing)}"
    try:
        result = to_content(tool.func(ctx, task, args))
    except Exception as error:
        logger.exception("%s 도구 %s 실패", spec.name, name)
        return f"오류: 도구 실행 실패 ({type(error).__name__}). 인자를 확인해 줘."
    evidence.add(name, result)
    return result


def _fallback(spec: AgentSpec, task: dict, ctx: RunContext, task_id: str, log) -> Proposal | None:
    if spec.fallback is None:
        log(step=0, kind="fallback", name="none")
        return None
    try:
        content = spec.fallback(task, ctx)
    except Exception:  # 물러나기까지 실패해도 화면은 기본 문장으로 계속 동작해야 한다
        logger.exception("%s 물러나기 실패", spec.name)
        content = None
    log(step=0, kind="fallback", name="ok" if content is not None else "failed")
    if content is None:
        return None
    return Proposal(spec.name, task_id, content, "FALLBACK", ctx.run_id)
