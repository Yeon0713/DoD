"""F4 고칠 점 에이전트: 최근 4주 아쉬운 리뷰에서 공통점을 찾아 고칠 점 한 문장(화면 폭 34 안)을 쓴다.

도구가 요일·시간대 집계를 계산해서 준다 (모델에게 세게 하지 않는다).
검사: 폭 8~34, '~요'로 끝남, 보상·가격 지어내기 금지, 근거 대조 엄격 모드(글의 숫자는 모두 입력·도구 결과에 있어야 함).
물러나기: 가장 많은 주제 × 많이 몰린 요일·시간대로 만든 템플릿.
"""

import datetime as dt
from collections import Counter

from Harness import runner
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import NO_ARGS, array, obj, string
from voice import config, speech, width
from voice.agents import load_prompt
from voice.agents.voice_reply import TOPIC_NAMES
from voice.audit import rules
from voice.clock import parse
from voice.context import VoiceStore, run_context

TEMPLATES = {
    "delivery": "{when}엔 배달 시간을 10분 넉넉히 안내해 보세요",
    "taste": "{when}엔 간을 한 번 더 확인해 보세요",
    "portion": "{when}엔 담는 양을 한 번 더 맞춰 보세요",
    "service": "{when}엔 주문 확인을 한 번 더 챙겨 보세요",
    "hygiene": "조리 공간 위생을 한 번 더 살펴 보세요",
    "other": "아쉬운 리뷰 내용을 한 번 더 살펴 보세요",
}


def negatives(view: VoiceStore, now: dt.datetime) -> list[dict]:
    since = now - config.NEGATIVE_WINDOW
    return [r for r in view.reviews() if r.get("sentiment") == "negative" and since <= parse(r["written_at"]) <= now]


def stats(reviews: list[dict]) -> dict:
    """주제, 요일, 시간대별 건수. 많은 순서."""
    times = [parse(r["written_at"]) for r in reviews]
    return {
        "total": len(reviews),
        "topics": Counter(r.get("topic") or "other" for r in reviews).most_common(),
        "weekdays": Counter(f"{speech.weekday(t.date())}요일" for t in times).most_common(),
        "dayparts": Counter(speech.daypart(t.hour) for t in times).most_common(),
    }


def template(reviews: list[dict]) -> str:
    if not reviews:
        return TEMPLATES["other"]
    found = stats(reviews)
    topic = found["topics"][0][0]
    weekday, weekday_n = found["weekdays"][0]
    part, part_n = found["dayparts"][0]
    when = f"{weekday} {part}" if weekday_n >= 2 else part if part_n >= 2 else "바쁜 시간"
    return width.fit("tip", TEMPLATES[topic].format(when=when), TEMPLATES[topic].format(when="바쁜 시간"), TEMPLATES["other"])


# ── 도구 ──


def _view(ctx: RunContext) -> VoiceStore:
    return ctx.snapshot  # type: ignore[return-value]


def negative_reviews(ctx: RunContext, task: dict, args: dict) -> dict:
    rows = []
    for review in negatives(_view(ctx), ctx.now):
        at = parse(review["written_at"])
        rows.append({
            "day": f"{at.month}월 {at.day}일({speech.weekday(at.date())})", "time": f"{at.hour}시({speech.clock_label(at)})",
            "channel": "배달" if review.get("order_channel") == "delivery" else "매장", "topic": TOPIC_NAMES.get(review.get("topic") or "other"),
            "summary": review.get("summary"),
        })
    return {"period": "최근 4주", "reviews": rows}


def review_counts(ctx: RunContext, task: dict, args: dict) -> dict:
    found = stats(negatives(_view(ctx), ctx.now))
    return {
        "total": found["total"],
        "by_topic": [{"topic": TOPIC_NAMES.get(t, t), "count": n} for t, n in found["topics"]],
        "by_weekday": [{"weekday": w, "count": n} for w, n in found["weekdays"]],
        "by_daypart": [{"daypart": p, "count": n} for p, n in found["dayparts"]],
    }


NEGATIVE_REVIEWS = Tool("get_negative_reviews", "최근 4주 아쉬운 리뷰의 날짜, 시각, 주문 방식, 주제, 요약", NO_ARGS, negative_reviews)
REVIEW_COUNTS = Tool("get_review_counts", "최근 4주 아쉬운 리뷰를 주제·요일·시간대별로 센 것 (많은 순)", NO_ARGS, review_counts)
SUBMIT = Tool(
    "submit_tip",
    "고칠 점 한 문장을 제출한다",
    obj({
        "tip": string("사장님께 드리는 고칠 점 한 문장. 30자 안쪽, '~해 보세요'처럼 '요'로 끝"),
        "evidence": array(string("근거"), "이 문장의 근거 (어느 도구 결과의 무엇을 봤는지)"),
    }),
)


def user_message(task: dict, ctx: RunContext) -> str:
    return f"오늘: {ctx.now:%Y-%m-%d}\n최근 4주 아쉬운 리뷰를 보고 가장 먼저 고칠 점 한 가지를 submit_tip 으로 내 줘."


def fallback(task: dict, ctx: RunContext) -> dict:
    return {"tip": template(negatives(_view(ctx), ctx.now))}


SPEC = AgentSpec(
    name="voice_improve_tip",
    system_prompt=lambda task, ctx: load_prompt("improve_tip.txt", ctx.store),
    user_message=user_message,
    tools=[NEGATIVE_REVIEWS, REVIEW_COUNTS],
    submit=SUBMIT,
    check=rules.improve_tip,  # 1차 코드 감사 (감사팀)
    task_id=lambda task: f"IMPROVE:{task['date']}",
    fallback=fallback,
    finalize=lambda args, task, ctx: {"tip": str(args.get("tip") or "").strip()},
    budget=Budget(max_steps=5, max_rejections=2, max_seconds=40),
    temperature=0.3,
)


def suggest(view: VoiceStore, now: dt.datetime) -> dict:
    """고칠 점 → {text, source}. 아쉬운 리뷰가 없으면 text 는 None."""
    reviews = negatives(view, now)
    if not reviews:
        return {"text": None, "source": "NONE"}
    if not config.agent_on("improve"):
        return {"text": template(reviews), "source": "TEMPLATE"}
    proposal = runner.run(SPEC, {"date": f"{now:%Y-%m-%d}"}, run_context(view, now))
    if proposal is None:
        return {"text": template(reviews), "source": "TEMPLATE"}
    return {"text": proposal.content["tip"], "source": proposal.source}
