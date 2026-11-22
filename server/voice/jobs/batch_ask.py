"""결재 묻기: 인턴 업무는 한 건씩, 사원 업무는 묶어서 (인사과 9장 4단계, donna-voice/docs/agent-structure.md 4-1).

ask(view, items, mode) → ask_action 응답. action {kind: "batch", items: [{job, ref}], rest: [...]}, 번호 붙은 checklist 카드.
  mode "each"(인턴): 첫 건만 묻고, 정하면 다음 건을 묻는다. "batch"(사원): 한 번에 (최대 4건, 넘는 것은 다음 질문).
  부르는 쪽이 hr.asks 로 mode 를 고르고, 물을 items 를 준다.
decide(view, name, edits, session, said): "응" → 모두 승인 / "두 번째는 빼" → 그것만 빼고 다시 묻기 /
  "두 번째는 빼고 올려" → 빼고 승인 / "안 해" → 모두 반려. 건마다 업무의 approve·reject 를 부르고 인사과에 기록한다.
session["batch"] 에 지금 묻는 것을 둔다 (remember). 다른 질문으로 넘어가면 지운다.
"좀 더 부드럽게"는 뒤에서 고치고 알림으로 다시 묻는다 (감사팀 9장, jobs/revise_jobs.py). 고치는 동안 정하면 고치기를 그만둔다.
업무마다 KINDS[job] 이 무엇을 보여 주고, 승인·반려하면 무엇을 하는지 정한다.
"""

import re
from dataclasses import dataclass
from typing import Callable

from voice import activity, clock, hr, proposals, repo, speech, width
from voice.jobs import queue, revise_jobs
from voice.clock import iso, parse
from voice.context import VoiceStore

ORDINAL = ["첫째", "둘째", "셋째", "넷째"]
MAX_ASK = width.MAX_ITEMS["rows"]


@dataclass
class Kind:
    pending: Callable[[VoiceStore, str], bool]  # 아직 물을 것인가 (이미 처리했으면 False)
    line: Callable[[VoiceStore, str], str]  # 묶어 물을 때 한 줄 ("국물이 샜다는 리뷰예요.")
    one: Callable[[VoiceStore, str], tuple[list[str], list[dict]]]  # 한 건만 물을 때 말과 카드
    item: Callable[[VoiceStore, str], dict]  # checklist 한 줄 {title, sub}
    approve: Callable[[VoiceStore, str], bool]  # 했으면 True (그 사이 작업 큐가 먼저 정했으면 False)
    reject: Callable[[VoiceStore, str], bool]
    many: str  # 묶어 물을 때 첫 줄: "아쉬운 리뷰가 {n} 있어요."
    question: str  # "써 둔 사과 답글을 올릴까요?"
    headline: str
    done: Callable[[int], str]  # 승인한 뒤: n건 → "사과 답글 2개를 올렸어요."
    none: tuple[str, ...]  # 모두 반려한 뒤 (say 한 줄에 한 문장)
    revise: Callable[[VoiceStore, str, str], bool] | None = None  # 고침 지시대로 다시 쓰기 (인사과 6단계). 고쳤으면 True


# ── 아쉬운 리뷰 답글 (negative_reply) ──


def _neg_pending(view: VoiceStore, ref: str) -> bool:
    review = view.review(ref)
    return bool(review and review.get("sentiment") == "negative" and review.get("reply_status", "none") == "none"
                and review.get("reply_ready") and not review.get("reply_deleted_at") and not review.get("reply_posting"))


def _neg_line(view: VoiceStore, ref: str) -> str:
    from voice.jobs.briefing import told

    return f"{told(view.review(ref)['summary'])} 리뷰예요."


def _neg_one(view: VoiceStore, ref: str) -> tuple[list[str], list[dict]]:
    from voice.jobs.briefing import _when, review_card, told

    review = view.review(ref)
    who = "배달로 드신 손님이" if review.get("order_channel") == "delivery" else "가게에서 드신 손님이"
    draft = {"text": review["reply_ready"]["text"], "posted_at": None, "by": "donna"}
    return ([f"{_when(parse(review['written_at']), view.now)} {who} {told(review['summary'])} 리뷰를 남기셨어요."],
            [review_card(review, draft)])


# J-10b: "서비스 준다는 말은 빼고 올려" (Figma v0.2.1 J, 2026-11-22). 혜택 문장을 규칙으로 빼고 바로 올린다 (모델로 다시 쓰지 않는다)
OFFER_RE = re.compile(r"서비스|쿠폰|무료|공짜|할인|사은품|증정|보상")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
AGENT_LABEL = {"negative_review": "위기 대처"}  # 인사과에 기록함 카드의 담당 이름 (Figma J-10b)


def split_offer(text: str) -> tuple[str, str, str | None]:
    """(남길 글, 뺀 글, 뺀 혜택 낱말). 혜택 문장이 없거나 다 빼면 남는 게 없으면 (text, '', None)."""
    sentences = [s for s in SENTENCE_RE.split(text.strip()) if s]
    offer = [s for s in sentences if OFFER_RE.search(s)]
    kept = [s for s in sentences if s not in offer]
    if not offer or not kept:
        return text, "", None
    return " ".join(kept), " ".join(offer), OFFER_RE.search(offer[0]).group(0)


def drop_offer_and_post(view: VoiceStore, ref: str, said: str | None) -> dict | None:
    """써 둔 사과 답글에서 혜택 문장을 빼고 올린 뒤 업무 수첩에 규칙을 적는다. 뺄 문장이 없으면 None (다른 길로)."""
    from voice import notebook
    from voice.jobs.briefing import answer, review_card, say

    review = repo.review(ref)
    ready = review.get("reply_ready") or {}
    kept, removed, word = split_offer(ready.get("text") or "")
    if word is None:
        return None
    repo.save_review({**review, "reply_ready": {**ready, "text": kept, "revised": [*(ready.get("revised") or []), said or ""]}})
    if not _neg_approve(view, ref):
        return None
    rule = f"사과할 때 {word} 준다는 말은 하지 않기"
    notebook.add(view.store_id, "negative_review", rule, said)
    hr.record(view.store_id, "negative_reply", ref, "edited", said)  # 같은 말로 수첩 판정을 또 하지 않는다 (notebook.judge_later)
    posted = repo.review(ref)
    card = review_card(posted, {"text": kept, "removed": removed, "posted_at": posted["reply_posted_at"], "by": "donna"})
    note = {"type": "quote", "id": "hr_note", "label": f"인사과에 기록함 · {AGENT_LABEL['negative_review']}", "text": rule}
    response = answer("빼고 올렸어요", [say(f"{word} 준다는 말은 빼고 올렸어요."), say(f"앞으로 {rule.replace('하지 않기', '하지 않을게요')}.", None, ["hr_note"])],
                      [card, note])
    response["own_screen"] = True
    return response


def _neg_item(view: VoiceStore, ref: str) -> dict:
    review = view.review(ref)
    return {"title": review["summary"], "sub": review["reply_ready"]["text"]}


def _rewrites_plain(view: VoiceStore, review: dict) -> bool:
    """올릴 때 plain 을 사장님 지시대로 고쳐 써야 하는가 (교정 할 일을 뺐고, 앞서 고쳐 달라고 했다). 고쳐 쓰기는 LLM 이라 뒤에서 한다."""
    ready = review["reply_ready"]
    fix = proposals.for_review(view.store_id, review["id"])
    return bool(ready.get("plain") and fix and fix["state"] in ("declined", "expired") and ready.get("revised"))


def ready_reply(view: VoiceStore, review: dict) -> tuple[str, str]:
    """써 둔 답글(reply_ready) 중 올릴 글 → (글, source).
    같은 리뷰의 교정 할 일을 뺐으면 그 조치를 약속하지 않는 글(plain)로 (영업 중 묶음 창과 밤사이 써 둔 글, plain 이 있을 때).
    "좀 더 부드럽게"는 조치를 적은 글(text)만 고치므로, 고친 적이 있으면 그 지시대로 plain 을 지금 고친다 (known-bugs B4).
    못 고치면 처음 plain 을 올린다 (지시는 빠져도 하지 않을 조치는 약속하지 않는다)."""
    from voice.agents import voice_reply

    ready = review["reply_ready"]
    fix = proposals.for_review(view.store_id, review["id"])
    if not (ready.get("plain") and fix and fix["state"] in ("declined", "expired")):
        return ready["text"], ready["source"]
    asked = ready.get("revised") or []
    # 영업 중 묶음 창의 plain 은 review_loop._batch 가 알림 기록(reply_plain + 사장님이 정한 보상 문장)으로 만든다. 보상 문장은 빼고
    # 고친 뒤 다시 붙인다. 밤사이 써 둔 plain(briefing.draft_negative, known-bugs B7)은 알림 기록도 보상 문장도 없다
    record = repo.get("alert", f"al_{review['id']}")
    base = record["reply_plain"] if record else ready["plain"]
    written = voice_reply.revise(view, review, "AUTO", base, ", ".join(asked)) if asked else None
    if written is None:
        return ready["plain"], ready["source"]
    preset = record["compensation"] if record and record["use_compensation"] else None
    text, notes = voice_reply.safe_reply(voice_reply.compose(written["text"], preset), preset, base)
    return text, ready["source"] if notes else written["source"]


def _neg_approve(view: VoiceStore, ref: str) -> bool:
    review = repo.review(ref)  # 말 처리를 시작할 때 읽은 view 가 아니라 지금 것 (그 사이 작업 큐가 올렸을 수 있다)
    if review.get("reply_status", "none") != "none" or review.get("reply_posting"):
        return False
    if _rewrites_plain(view, review):  # 할 일을 빼고 승인: plain 을 지시대로 뒤에서 고쳐(감사 포함) 다시 묻지 않고 올린다 (결정 15)
        marked = []

        def mark(job: dict) -> None:  # 뒤에서 올리기 전에 표시해 두어 다시 묻지 않는다
            marked.append(repo.save_review_if({**review, "reply_posting": job["id"]}, "none") is not None)

        revise_jobs.start(view.store_id, "post", ref, "negative_reply", ", ".join(review["reply_ready"]["revised"]), _post_work,
                          prepare=mark)
        return marked[0]
    return _post_ready(view, review, *ready_reply(view, review))


def _post_work(job: dict):
    """뒤에서: plain 을 고쳐 쓴 뒤 올린다. 못 고치면 고치지 않은 plain 을 올린다 (ready_reply)."""
    from voice.context import load

    view = load(job["store_id"])
    text, source = ready_reply(view, repo.review(job["ref"]))

    def apply() -> str:
        review = repo.review(job["ref"])
        if review.get("reply_posting") != job["id"]:
            return "discard"
        review.pop("reply_posting")
        return "ready" if _post_ready(view, review, text, source) else "discard"

    return apply


def _post_ready(view: VoiceStore, review: dict, text: str, source: str) -> bool:
    ref = review["id"]
    now = clock.now()
    review.update({
        "reply_status": "posted", "reply_by": "donna", "reply_text": text, "reply_source": source,
        "reply_posted_at": iso(now), "replied_in_minutes": max(1, round((now - parse(review["written_at"])).total_seconds() / 60)),
        "reply_trigger": "owner_yes",
    })
    if repo.save_review_if(review, "none") is None:
        return False
    activity.log(view.store_id, "donna", "아쉬운 리뷰에 사과 답글을 올렸어요", f"fix:{ref}:reply", at=now)
    return True


def _neg_revise(view: VoiceStore, ref: str, instruction: str) -> bool:
    from voice.agents import voice_reply

    review = repo.review(ref)
    ready = review["reply_ready"]
    # 영업 중 묶음 창의 글은 알림 기록의 사과 글 + 사장님이 정한 보상 문장이다 (review_loop.reply_text). 보상 문장은 에이전트에
    # 넘기지 않고 고친 뒤 다시 붙인다 (review_loop._revise 와 같게, known-bugs B5). 밤사이 써 둔 글(알림 기록 없음)은 보상 문장이 없다
    record = repo.get("alert", f"al_{ref}")
    key = ("reply_base" if record["use_card"] and record["card"] else "reply_plain") if record else None
    previous = record[key] if record else ready["text"]
    written = voice_reply.revise(view, review, "AUTO", previous, instruction)
    if written is None:
        return False
    _, notes = voice_reply.safe_reply(written["text"], None, previous)
    if notes:  # 고친 글이 보상 검사에 걸렸다: 고치지 않은 것으로
        return False
    preset = record["compensation"] if record and record["use_compensation"] else None
    if record:  # 다시 고치면 고친 글에서 이어 고친다
        repo.put("alert", record["id"], record["store_id"], {**record, key: written["text"]})
    # plain 은 그대로 두고 지시만 적어 둔다. 할 일을 빼고 올릴 때 ready_reply 가 그 지시대로 고친다 (known-bugs B4)
    revised = [*(ready.get("revised") or []), instruction]
    text = voice_reply.compose(written["text"], preset)
    # 고치는 사이 올렸거나 반려했으면 덮지 않는다 (뒤에서 고친다, 감사팀 9장)
    return repo.save_review_if({**review, "reply_ready": {**ready, "text": text, "source": written["source"], "revised": revised}},
                               "none") is not None


def _neg_reject(view: VoiceStore, ref: str) -> bool:
    review = repo.review(ref)
    if review.get("reply_status", "none") != "none":
        return False
    ready = review["reply_ready"]
    review.update({"reply_status": "drafted", "reply_by": "donna", "reply_text": ready["text"], "reply_source": ready["source"]})
    return repo.save_review_if(review, "none") is not None


# ── 좋은 리뷰 예약 답글 (positive_reply, 9-0 b) ──


def _when_label(review: dict) -> str:
    at = parse(review["reply_post_at"])
    return f"{speech.weekday(at.date())}요일 {speech.clock_label(at)}"


def _pos_pending(view: VoiceStore, ref: str) -> bool:
    review = view.review(ref)
    return bool(review and review.get("reply_status") == "awaiting")


def _pos_line(view: VoiceStore, ref: str) -> str:
    return f"{_when_label(view.review(ref))}에 올릴 답글이에요."


def _pos_one(view: VoiceStore, ref: str) -> tuple[list[str], list[dict]]:
    from voice.jobs.briefing import review_card

    review = view.review(ref)
    draft = {"text": review["reply_text"], "posted_at": None, "by": "donna", "scheduled_label": f"{_when_label(review)}에 올릴 답글"}
    why = (review.get("reply_reason") or {}).get("explanation")
    return (["좋은 리뷰 답글을 써 뒀어요."] + ([f"{why}."] if why else []), [review_card(review, draft)])


def _pos_item(view: VoiceStore, ref: str) -> dict:
    review = view.review(ref)
    return {"title": _when_label(review), "sub": review["reply_text"]}


def _pos_approve(view: VoiceStore, ref: str) -> bool:
    review = repo.review(ref)
    if review.get("reply_status") != "awaiting":
        return False
    post_at = max(parse(review["reply_post_at"]), clock.now())  # 올릴 때가 이미 지났으면 바로 올린다
    if repo.save_review_if({**review, "reply_status": "scheduled", "reply_trigger": "owner_yes", "reply_post_at": iso(post_at)},
                           "awaiting") is None:
        return False
    queue.add(view.store_id, "post_scheduled", post_at)
    return True


def _pos_revise(view: VoiceStore, ref: str, instruction: str) -> bool:
    from voice.agents import voice_reply

    review = repo.review(ref)
    occasion = {**(review.get("reply_reason") or {}), "post_at": review["reply_post_at"]}
    written = voice_reply.revise(view, review, "SCHEDULED", review["reply_text"], instruction, occasion=occasion)
    if written is None:
        return False
    return repo.save_review_if({**review, "reply_text": written["text"], "reply_source": written["source"]}, "awaiting") is not None


def _pos_reject(view: VoiceStore, ref: str) -> bool:
    review = repo.review(ref)
    if review.get("reply_status") != "awaiting":
        return False
    return repo.save_review_if({**review, "reply_status": "drafted"}, "awaiting") is not None


# ── 알바생 할 일 (review_fix_task, field_task, manual_task: 늘 결재, 상한 사원) ──


def _task_pending(view: VoiceStore, ref: str) -> bool:
    found = proposals.get(ref)
    return bool(found and found["state"] in proposals.LIVE)


def _task_line(view: VoiceStore, ref: str) -> str:
    title = proposals.get(ref)["payload"]["title"]
    return f"알바생 할 일 {speech.josa(title, '이에요', '예요')}."


def _task_one(view: VoiceStore, ref: str) -> tuple[list[str], list[dict]]:
    from voice.jobs import staff_tasks

    found = proposals.get(ref)
    card = {"type": "checklist", "id": "batch", "title": "알바생 할 일에 넣을 것",
            "items": [{"id": ref, "title": found["payload"]["title"], "sub": found["payload"].get("detail") or "", "state": "todo"}]}
    return [staff_tasks._why(view, found, view.now), f"알바생 할 일에 {speech.josa(found['payload']['title'], '을', '를')} 넣을게요."], [card]


def _task_item(view: VoiceStore, ref: str) -> dict:
    payload = proposals.get(ref)["payload"]
    return {"title": payload["title"], "sub": payload.get("detail") or ""}


def _task_approve(view: VoiceStore, ref: str) -> bool:
    # apply 는 접힌 제안도 넣는다 (다시 열기 길). 묶음 승인은 락 안에서 살아 있는지 다시 본다. RLock 이라 apply 안에서 다시 잡아도 된다
    with repo._lock:
        if not _task_pending(view, ref):
            return False  # 그 사이 작업 큐가 접었다
        proposals.apply(ref, "owner_yes")
    return True


def _task_reject(view: VoiceStore, ref: str) -> bool:
    with repo._lock:
        if not _task_pending(view, ref):
            return False  # 그 사이 작업 큐가 접었다
        proposals.decline(ref, "owner_no")
    return True


TASK = Kind(
    pending=_task_pending, line=_task_line, one=_task_one, item=_task_item, approve=_task_approve, reject=_task_reject,
    many="알바생 할 일이 {n} 있어요.", question="넣을까요?", headline="알바생 할 일 넣을까요?",
    done=lambda n: "알바생 할 일을 넣었어요." if n == 1 else f"알바생 할 일 {n}개를 넣었어요.", none=("네, 알바생 할 일은 넣지 않을게요.",))

KINDS: dict[str, Kind] = {
    "negative_reply": Kind(
        pending=_neg_pending, line=_neg_line, one=_neg_one, item=_neg_item, approve=_neg_approve, reject=_neg_reject,
        many="아쉬운 리뷰가 {n} 있어요.", question="써 둔 사과 답변을 올릴까요?", headline="사과 답변을 올릴까요?",
        done=lambda n: "사과 답글을 올렸어요." if n == 1 else f"사과 답글 {n}개를 올렸어요.", none=("네, 올리지 않을게요.", "초안은 남겨 둘게요."),
        revise=_neg_revise),
    "positive_reply": Kind(
        pending=_pos_pending, line=_pos_line, one=_pos_one, item=_pos_item, approve=_pos_approve, reject=_pos_reject,
        many="좋은 리뷰 답글이 {n} 있어요.", question="이렇게 예약할까요?", headline="답글 예약할까요?",
        done=lambda n: "답글을 예약했어요." if n == 1 else f"답글 {n}개를 예약했어요.", none=("네, 예약하지 않을게요.", "초안은 남겨 둘게요."),
        revise=_pos_revise),
    "review_fix_task": TASK, "field_task": TASK, "manual_task": TASK,
}


# ── 묻기 ──


def _live(view: VoiceStore, items: list[dict]) -> list[dict]:
    return [i for i in items if KINDS[i["job"]].pending(view, i["ref"])]


def ask(view: VoiceStore, items: list[dict], mode: str, *, lead: list[str] | None = None) -> dict | None:
    """items: [{job, ref}] (물을 순서대로). 물을 것이 없으면 None."""
    from voice.jobs.briefing import answer, say

    items = _live(view, items)
    if not items:
        return None
    asked, rest = (items[:1], items[1:]) if mode == "each" else (items[:MAX_ASK], items[MAX_ASK:])
    kinds = {i["job"] for i in asked}
    kind = KINDS[asked[0]["job"]]
    question = kind.question if len(kinds) == 1 else "이대로 할까요?"
    says = [say(text) for text in lead or []]
    if len(asked) == 1:
        texts, cards = kind.one(view, asked[0]["ref"])
        caption = "부정 리뷰는 꼭 여쭤보고 올려요" if asked[0]["job"] == "negative_reply" else None  # Figma J-10a
        says += [say(text, caption if n == 0 else None) for n, text in enumerate(texts)]
    else:
        says.append(say(kind.many.format(n=speech.count(len(asked), "개")) if len(kinds) == 1 else f"여쭤볼 게 {speech.count(len(asked), '개')} 있어요."))
        says += [say(f"{ORDINAL[n]}, {KINDS[i['job']].line(view, i['ref'])}") for n, i in enumerate(asked)]
        rows = [{"id": i["ref"], "title": f"{n + 1}. {KINDS[i['job']].item(view, i['ref'])['title']}",
                 "sub": KINDS[i["job"]].item(view, i["ref"])["sub"], "state": "todo"} for n, i in enumerate(asked)]
        cards = [{"type": "checklist", "id": "batch", "title": "여쭤볼 것", "items": rows}]
    says.append(say(question))
    response = answer(kind.headline if len(kinds) == 1 else "이대로 할까요?", says, cards, kind="ask_action",
                      action={"kind": "batch", "items": asked, "rest": rest, "mode": mode})
    response["expects_reply"] = True
    return response


def remember(response: dict, session: dict) -> None:
    """묶음 질문을 보냈으면 session 에 둔다. 다른 것을 보냈으면 지운다 (못 알아들음·흘려들음은 그대로)."""
    action = response.get("action") or {}
    if action.get("kind") == "batch":
        session["batch"] = {k: action[k] for k in ("items", "rest", "mode")}
    elif response.get("type") not in ("ignore", "not_understood") and not response.get("keep_batch"):
        session.pop("batch", None)  # keep_batch: 뒤에서 고치는 중 ("응"이면 지금 글로 정한다)


def _settle(view: VoiceStore, items: list[dict], approve: bool, said: str | None) -> None:
    for i in items:
        if not KINDS[i["job"]].pending(view, i["ref"]):
            continue  # 다른 기기에서 먼저 정했다
        if not (KINDS[i["job"]].approve if approve else KINDS[i["job"]].reject)(view, i["ref"]):
            continue  # 말 처리를 시작한 뒤 작업 큐가 먼저 정했다 (올렸다 등)
        hr.record(view.store_id, i["job"], i["ref"], "approved" if approve else "rejected", said)


def _done_says(view: VoiceStore, kept: list[dict], dropped: list[dict]) -> list[str]:
    out = []
    for job in dict.fromkeys(i["job"] for i in kept + dropped):
        mine = [i for i in kept if i["job"] == job]
        out += [KINDS[job].done(len(mine))] if mine else list(KINDS[job].none)
    return out


def decide(view: VoiceStore, name: str, edits: dict | None, session: dict, said: str | None = None) -> dict:
    """묶음 질문의 대답. 남은 건(인턴의 다음 건, 사원의 넘친 건)이 있으면 이어서 묻는다."""
    from voice.jobs.briefing import answer, say

    pending = session.get("batch") or {}
    asked = _live(view, pending.get("items") or [])
    rest = pending.get("rest") or []
    mode = pending.get("mode", "batch")
    if not asked:
        session.pop("batch", None)
        follow = ask(view, rest, mode)
        return follow or answer("지금은 물어본 게 없어요", [say("지금은 여쭤본 게 없어요.")], [])
    drop = [asked[i - 1] for i in (edits or {}).get("drop_index") or [] if 1 <= i <= len(asked)]
    keep = [i for i in asked if i not in drop]
    if name in ("action.cancel", "action.approve", "action.edit"):  # 고치는 중이면 그만둔다. 지금 글로 정한다 (감사팀 9-3)
        revise_jobs.cancel(view.store_id, "batch")
    if name == "action.cancel":
        _settle(view, asked, False, said)
        texts = _done_says(view, [], asked)
    elif name == "action.approve" and (edits or {}).get("drop_compensation") and len(asked) == 1 and asked[0]["job"] == "negative_reply":
        posted = drop_offer_and_post(view, asked[0]["ref"], said)  # J-10b "서비스 준다는 말은 빼고 올려"
        if posted is not None:
            session.pop("batch", None)
            follow = ask(load_view(view), rest, mode)
            return posted if follow is None else {**follow, "say": posted["say"] + follow["say"]}
        _settle(view, keep, True, said)
        texts = _done_says(view, keep, [])
    elif name == "action.approve":
        _settle(view, drop, False, said)
        _settle(view, keep, True, said)
        texts = _done_says(view, keep, drop)
    elif name == "action.revise":  # "좀 더 부드럽게": 묻는 글을 모두 뒤에서 지시대로 다시 쓰고 알림으로 다시 묻는다 (감사팀 9장)
        targets = [i for i in asked if KINDS[i["job"]].revise]
        if not targets:
            return ask(view, asked + rest, mode, lead=["지금은 고치지 못했어요."]) or answer("지금은 물어본 게 없어요", [say("지금은 여쭤본 게 없어요.")], [])
        for i in targets:  # 인사과 '조금 수정'과 수첩 판정은 지시를 받은 지금 (9-2)
            hr.record(view.store_id, i["job"], i["ref"], "edited", said)
        revise_jobs.start(view.store_id, "batch", ",".join(i["ref"] for i in targets), None, said or "", _revise_work,
                          items=asked + rest, mode=mode)
        return {**answer("고쳐서 알려 드릴게요", [say("네, 고쳐서 알려 드릴게요.")], []), "keep_batch": True}
    elif name == "action.edit" and drop:
        _settle(view, drop, False, said)
        if not keep:
            texts = _done_says(view, [], drop)
        else:
            dropped = ", ".join(ORDINAL[asked.index(i)] for i in drop)
            response = ask(view, keep + rest, "batch" if mode == "batch" else "each")
            response["say"] = [say(f"{speech.josa(dropped, '은', '는')} 빼고 할까요?")] + response["say"][-1:]
            return response
    else:
        lead = ["하시려면 '응', 안 하시려면 '안 해'라고 말씀해 주세요."]
        return ask(view, asked + rest, mode, lead=lead) or answer("지금은 물어본 게 없어요", [say("지금은 여쭤본 게 없어요.")], [])
    session.pop("batch", None)
    follow = ask(load_view(view), rest, mode)
    done = answer(width.fit("headline", "네, 그렇게 할게요", "알겠어요"), [say(t) for t in texts], [])
    if follow is None:
        return done
    return {**follow, "say": done["say"] + follow["say"]}


def _revise_work(job: dict):
    """뒤에서: 아직 묻는 글을 지시대로 고쳐 쓴다 (각 업무의 revise 가 저장까지 한다. 그 사이 정한 것은 덮지 않는다)."""
    from voice.context import load

    view = load(job["store_id"])
    revised = [i for i in job["items"] if KINDS[i["job"]].revise and KINDS[i["job"]].pending(view, i["ref"])
               and i["ref"] in job["ref"].split(",") and KINDS[i["job"]].revise(view, i["ref"], job["instruction"])]
    return lambda: "ready" if revised else "failed"


def reopen(view: VoiceStore, job: dict) -> dict | None:
    """고친 알림을 열었을 때: 아직 묻는 것을 다시 묻는다."""
    lead = ["이렇게 고쳤어요."] if job["state"] == "ready" else ["지금은 고치지 못했어요.", "이대로 할지 말씀해 주세요."]
    return ask(view, job["items"], job["mode"], lead=lead)


def load_view(view: VoiceStore) -> VoiceStore:
    from voice.context import load

    return load(view.store_id) or view

