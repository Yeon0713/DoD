"""사후 보고와 사후 취소 (인사과 4-7, donna-voice/docs/agent-structure.md 9장 5단계, 9-0 g·h).

대리·과장이 묻지 않고 처리한 것(hr_event done)을 아침 브리핑 단계 done_report(쉬는 날 다음, 게이지 1)에서 알린다.
  대리: 업무마다 건수와 첫 건을 말하고, 나머지는 자세히 보기·읽어 주기로. 과장: 월요일에 지난주 건수만.
  단계 응답을 앱에 보낸 때 reported_at 을 적는다 (turn.handle). 듣지 못한 보고는 다음 보고에 이어 붙는다.
사후 취소: "두 번째 거 취소해", "그 답글 지워", "어제 인스타 지워" (뜻 report.undo). 번호는 그날 보고한 순서다.
  답글은 reply_status 를 none 으로 돌리고 reply_deleted_at 을 적는다 (v0.2.0 은 플랫폼에 올리지 않으므로 상태만).
  인스타는 posts.delete 가 Graph API 로 지운다. 보고를 들은 날 영업이 끝나기 전이면 인사과가 한 단계 내린다 (말하지 않음).
"""

import datetime as dt
import re

from voice import clock, hours, hr, repo, speech
from voice.clock import iso
from voice.context import VoiceStore
from voice.dialog import intent_rules
from voice.instagram import posts
from voice.instagram.graph import InstagramError

ORDINAL = ["첫 번째", "두 번째", "세 번째", "네 번째", "다섯 번째", "여섯 번째", "일곱 번째", "여덟 번째"]
REPLY_JOBS = ("positive_reply", "negative_reply")
LINES = {
    "positive_reply": lambda n: f"좋은 리뷰 {speech.count(n, '개')}에 답글을 올렸어요.",
    "negative_reply": lambda n: f"아쉬운 리뷰 {speech.count(n, '개')}에 사과 답글을 올렸어요.",
    "instagram_post": lambda n: "인스타에 게시물을 올렸어요." if n == 1 else f"인스타에 게시물 {speech.count(n, '개')}를 올렸어요.",
    "story_poster": lambda n: "인스타 스토리에 이벤트 포스터를 올렸어요." if n == 1 else f"인스타 스토리에 이벤트 포스터 {speech.count(n, '개')}를 올렸어요.",
}
ROW_LABELS = {"positive_reply": "좋은 리뷰 답글", "negative_reply": "아쉬운 리뷰 답글", "instagram_post": "인스타 게시물",
              "story_poster": "이벤트 스토리"}


def describe(view: VoiceStore, event: dict) -> str:
    """한 건을 말로: "들깨 국물이 고소했다는 리뷰에 단 답글", "인스타 게시물"."""
    from voice.jobs.briefing import told

    if event["job"] in REPLY_JOBS:
        summary = (view.review(event["ref"]) or {}).get("summary")
        return f"{told(summary)} 리뷰에 단 답글" if summary else "리뷰에 단 답글"
    return "이벤트 스토리" if event["job"] == "story_poster" else "인스타 게시물"


def step(view: VoiceStore, now: dt.datetime, skip: frozenset[str] | set[str] = frozenset()) -> tuple[dict | None, dict | None]:
    """브리핑 단계 done_report. 응답의 report 칸(보고한 hr_event id)은 앱에 보내지 않고 turn.handle 이 보고했다고 적는다.
    skip: 다른 단계가 이미 보여 주고 보고하는 hr_event id (H-10 바로 단 사과 답글, briefing.step_negative_done)."""
    from voice.jobs.briefing import answer, review_card, say

    items = [e for e in hr.report_items(view.store_id, now) if e["id"] not in skip]
    if not items:
        return None, None
    daily = [e for e in items if e["rank_at"] != "manager"]
    weekly = [e for e in items if e["rank_at"] == "manager"]
    says, rows = [say("제가 알아서 처리한 게 있어요.")], []
    for job in dict.fromkeys(e["job"] for e in daily):
        mine = [e for e in daily if e["job"] == job]
        says.append(say(LINES[job](len(mine))))
        says.append(say(f"{'첫 번째는 ' if len(mine) > 1 else ''}{describe(view, mine[0])}이에요."))
        rows.append({"id": f"dr_{job}", "kind": "done", "label": ROW_LABELS[job], "value": f"{len(mine)}건"})
    for job in dict.fromkeys(e["job"] for e in weekly):
        n = sum(1 for e in weekly if e["job"] == job)
        says.append(say(f"지난주 {hr.JOBS[job]['name']} {speech.count(n, '건')}을 처리했어요."))
        rows.append({"id": f"dw_{job}", "kind": "done", "label": ROW_LABELS[job], "value": f"지난주 {n}건"})
    if daily:  # "그거 지워"는 알바생 일 취소(staff.cancel)라서 무엇을 지울지 같이 말하게 한다
        example = "두 번째 거 지워" if len(daily) > 1 else ("그 인스타 지워" if daily[0]["job"] == "instagram_post" else "그 답글 지워")
        says.append(say(f"되돌릴 게 있으면 '{example}'처럼 말씀해 주세요."))
    response = answer("제가 처리한 것이에요", says, [{"type": "rows", "id": "done_report", "rows": rows[:4]}],
                      report=[e["id"] for e in items])
    reading = [say(f"{ORDINAL[i] if i < len(ORDINAL) else f'{i + 1}번째'}, {describe(view, e)}이에요.") for i, e in enumerate(daily)]
    shown = [review_card(view.review(e["ref"]), {"text": view.review(e["ref"]).get("reply_text"), "by": "donna",
                                                "posted_at": view.review(e["ref"]).get("reply_posted_at")})
             for e in daily if e["job"] in REPLY_JOBS][:4] or response["cards"]
    detail = {"show": answer("제가 처리한 것이에요", [say("화면에 띄웠어요.")], shown, kind="show_detail"),
              "read": answer("제가 처리한 것이에요", reading or [say("지난주 건수만 있어요.")], response["cards"])}
    return response, detail


# ── 사후 취소 ──


def _candidates(store_id: str, today: dt.date) -> tuple[list[dict], bool]:
    """번호가 가리키는 목록과, 지금이 사후 취소 기간(보고를 들은 날 영업이 끝나기 전)인지."""
    found = hr.reported_on(store_id, today)
    if found:
        return found, True
    for back in range(1, 8):  # 기간이 지난 것도 지울 수는 있다 (강등은 하지 않음)
        found = hr.reported_on(store_id, today - dt.timedelta(days=back))
        if found:
            return found, False
    return [], False


def _open_now(store: dict, now: dt.datetime) -> bool:
    return hours.business_day(store, now) is not None  # 자정 넘김 가게의 새벽은 어제 영업


def _pick(items: list[dict], n: str) -> list[dict]:
    index = [int(m.group(2)) if m.group(2) else intent_rules.ORDINAL_WORDS[m.group(1)] for m in intent_rules.ORDINAL_RE.finditer(n)]
    if index:
        return [items[i - 1] for i in index[:1] if 1 <= i <= len(items)]
    if "인스타" in n or "게시물" in n:
        return [e for e in items if e["job"] == "instagram_post"]
    if re.search(r"답글", n):
        return [e for e in items if e["job"] in REPLY_JOBS]
    return items


def _delete(view: VoiceStore, event: dict) -> None:
    if event["job"] in REPLY_JOBS:
        review = view.review(event["ref"])
        repo.save_review({**review, "reply_status": "none", "reply_deleted_at": iso(clock.now()),
                          "reply_deleted_text": review.get("reply_text")})
    else:
        posts.delete(view.store_id, event["ref"])


def undo(view: VoiceStore, said: str | None) -> dict:
    """"두 번째 거 지워", "그 답글 지워", "어제 인스타 지워"."""
    from voice.jobs.briefing import answer, say

    now = clock.now()
    items, in_time = _candidates(view.store_id, now.date())
    if not items:
        return answer("되돌릴 게 없어요", [say("제가 알아서 처리한 것 중에 되돌릴 게 없어요.")], [])
    picked = _pick(items, intent_rules.normalize(said or ""))
    if len(picked) != 1:
        lines = [say(f"{ORDINAL[i] if i < len(ORDINAL) else f'{i + 1}번째'}, {describe(view, e)}이에요.") for i, e in enumerate(items)]
        response = answer("어느 것을 지울까요?", [say("어느 것을 지울까요?"), *lines, say("'두 번째 거 지워'처럼 말씀해 주세요.")], [])
        response["expects_reply"] = True
        return response
    event = picked[0]
    if event.get("undone_at"):
        return answer("이미 지웠어요", [say("그건 이미 지웠어요.")], [])
    try:
        _delete(view, event)
    except InstagramError as error:
        return answer("지우지 못했어요", [say("인스타에서 지우지 못했어요."), say("인스타 앱에서 직접 지워 주세요.")], [], error=str(error))
    repo.put(hr.EVENT_KIND, event["id"], view.store_id, {**event, "undone_at": iso(now)})
    hr.undo(view.store_id, event, in_time and _open_now(view.store, now), said)
    what = describe(view, event)
    return answer("지웠어요", [say(f"{speech.josa(what, '을', '를')} 지웠어요.")], [])

