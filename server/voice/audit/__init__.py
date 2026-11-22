"""감사팀: 인사과를 뺀 담당 결과물을 검사하고, 불합격이면 만든 담당에게 되돌린다 (donna-voice/docs/audit-team-plan.md).

  rules.py      1차 코드 감사. 담당이 제출할 때마다 돈다 (담당 SPEC.check 가 가리킨다)
  inspector.py  2차 LLM 감사. 1차를 통과한 제출에만 돈다 (담당 SPEC.audit). 기준마다 좁은 질문 하나, 판정은 코드
  questions.py  2차 감사의 새 질문 (프롬프트 prompts/*.txt)
  log.py        감사 기록(voice.db docs 의 audit)과 개발자 대시보드 요약
되돌림(2차 불합격 뒤 같은 대화로 지적을 돌려줌)은 Harness.runner 가 한다 (AgentSpec.audit, audit_returns).
감사팀이 한 일은 사장님께 알리지 않는다 (결정 9). 인사과 직급에도 반영하지 않는다 (결정 8).
실행 중 스위치는 두지 않는다 (18장 3번, 2026-11-22): 감사팀은 늘 돈다. 판정 세트 목표를 넘지 못한 기준은 코드에 넣지 않는다.
"""

from pathlib import Path

from Harness import cache

# 업무 → 그 결과를 만드는 담당 (실행 이름). 인사과 업무(hr.JOBS)에 없는 것은 사실 확인·연결 미룸
JOBS = {
    "negative_reply": ("voice_reply",),
    "positive_reply": ("voice_reply",),
    "review_fix_task": ("voice_fix_card",),
    "field_task": ("voice_field_tasks",),
    "manual_task": ("voice_manual_line",),
    "instagram_post": ("voice_topic_finder", "voice_caption_writer"),
    "holiday": ("voice_holiday_reader",),
    "improve_tip": ("voice_improve_tip",),
}
STAFF_TASK_JOBS = {"review_fix_task", "field_task", "manual_task"}  # 끝내 불합격이면 지금 물러나기 (결정 7)
HERE = Path(__file__).parent


def version() -> str:
    """감사 기준의 버전: 질문 프롬프트와 판정 코드의 해시. 담당 캐시 키에 넣어 기준이 바뀌면 예전 결과를 다시 쓰지 않는다 (8-6)."""
    files = sorted(HERE.glob("prompts/*.txt")) + [p for p in (HERE / "inspector.py", HERE / "questions.py") if p.exists()]
    return cache.digest([p.read_text(encoding="utf-8") for p in files])


def brief(audit: dict | None) -> dict | None:
    """결과물 문서에 적을 감사 요약 (회차 기록 trail 은 감사 기록 audit 에만 둔다)."""
    return None if audit is None else {"passed": audit.get("passed"), "rounds": audit.get("rounds", 0)}


def held(store_id: str, job: str, ref: str) -> bool:
    """그 결과물이 감사 보류(audit_hold) 건인지. 인사과는 보류 건의 반응을 남기지 않는다 (가정 e, 8-5).
    ref 는 인사과 기록의 ref: 답글은 리뷰 id, 인스타는 instagram:<가게>:<날짜>."""
    from voice import repo

    if job in ("negative_reply", "positive_reply"):
        return bool((repo.review(ref) or {}).get("audit_hold"))
    if job == "instagram_post" and ref.startswith("instagram:"):
        return bool((repo.get("marketing_plan", f"{store_id}:{ref.rsplit(':', 1)[1]}") or {}).get("audit_hold"))
    return False


def settle(store_id: str, job: str, audit: dict | None, *, offer: bool = False) -> str:
    """끝내 불합격(또는 감사 못 함)한 결과를 어떻게 할지 (결정 7, 가정 g). 'ok' | 'hold' | 'template' | 'fallback'.
    ok        그대로 지금 흐름 (합격, 감사 자리 없음, 템플릿 결과)
    fallback  알바생 할 일·사실 확인: 지금 물러나기 (템플릿 카드, 첫 제목, 제안 없음, 빈 목록)
    hold      대리·과장 건: 걸린 초안 그대로 그 건만 사장님께 묻는다
    template  인턴·사원 건: 템플릿으로 물러나 묻는다 (감사 못 함은 사장님이 보므로 ok)"""
    from voice import hr

    if audit is None or audit.get("passed") is True:
        return "ok"
    if job in STAFF_TASK_JOBS or job not in hr.JOBS:
        return "fallback"
    if hr.asks(store_id, job, offer=offer) is None:
        return "hold"
    return "ok" if audit.get("passed") is None else "template"
