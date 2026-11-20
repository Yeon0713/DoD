"""결재 묻기: 인턴 업무는 한 건씩, 사원 업무는 묶어서 (인사과 9장 4단계, donna-voice/docs/agent-structure.md 4-1).

ask(view, items, mode) → ask_action 응답. action {kind: "batch", items: [{job, ref}], rest: [...]}, 번호 붙은 checklist 카드.
  mode "each"(인턴): 첫 건만 묻고, 정하면 다음 건을 묻는다. "batch"(사원): 한 번에 (최대 4건, 넘는 것은 다음 질문).
  부르는 쪽이 hr.asks 로 mode 를 고르고, 물을 items 를 준다.
decide(view, name, edits, session, said): "응" → 모두 승인 / "두 번째는 빼" → 그것만 빼고 다시 묻기 /
  "두 번째는 빼고 올려" → 빼고 승인 / "안 해" → 모두 반려. 건마다 업무의 approve·reject 를 부르고 인사과에 기록한다.
session["batch"] 에 지금 묻는 것을 둔다 (remember). 다른 질문으로 넘어가면 지운다.
업무마다 KINDS[job] 이 무엇을 보여 주고, 승인·반려하면 무엇을 하는지 정한다.
"""

from dataclasses import dataclass
from typing import Callable

from voice import activity, clock, hr, proposals, repo, speech, width
from voice.jobs import queue
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
    approve: Callable[[VoiceStore, str], None]
    reject: Callable[[VoiceStore, str], None]
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
                and review.get("reply_ready") and not review.get("reply_deleted_at"))


def _neg_line(view: VoiceStore, ref: str) -> str:
    from voice.jobs.briefing import told

    return f"{told(view.review(ref)['summary'])} 리뷰예요."


def _neg_one(view: VoiceStore, ref: str) -> tuple[list[str], list[dict]]:
    from voice.jobs.briefing import _when, review_card, told

    review = view.review(ref)
    who = "배달로 드신 손님이" if review.get("order_channel") == "delivery" else "가게에서 드신 손님이"
    draft = {"text": review["reply_ready"]["text"], "posted_at": None, "by": "donna", "scheduled_label": "올리기 전 답글"}
    return ([f"{_when(parse(review['written_at']), view.now)} {who} {told(review['summary'])} 리뷰를 남기셨어요."],
            [review_card(review, draft)])


def _neg_item(view: VoiceStore, ref: str) -> dict:
    review = view.review(ref)
    return {"title": review["summary"], "sub": review["reply_ready"]["text"]}


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


def _neg_approve(view: VoiceStore, ref: str) -> None:
    review = view.review(ref)
    text, source = ready_reply(view, review)
    now = clock.now()
    review.update({
        "reply_status": "posted", "reply_by": "donna", "reply_text": text, "reply_source": source,
        "reply_posted_at": iso(now), "replied_in_minutes": max(1, round((now - parse(review["written_at"])).total_seconds() / 60)),
        "reply_trigger": "owner_yes",
    })
    repo.save_review(review)
    activity.log(view.store_id, "donna", "아쉬운 리뷰에 사과 답글을 올렸어요", f"fix:{ref}:reply", at=now)


def _neg_revise(view: VoiceStore, ref: str, instruction: str) -> bool:
    from voice.agents import voice_reply

    review = view.review(ref)
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
    repo.save_review({**review, "reply_ready": {**ready, "text": text, "source": written["source"], "revised": revised}})
    return True


def _neg_reject(view: VoiceStore, ref: str) -> None:
    review = view.review(ref)
    ready = review["reply_ready"]
    review.update({"reply_status": "drafted", "reply_by": "donna", "reply_text": ready["text"], "reply_source": ready["source"]})
    repo.save_review(review)


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


def _pos_approve(view: VoiceStore, ref: str) -> None:
    review = view.review(ref)
    post_at = max(parse(review["reply_post_at"]), clock.now())  # 올릴 때가 이미 지났으면 바로 올린다
    repo.save_review({**review, "reply_status": "scheduled", "reply_trigger": "owner_yes", "reply_post_at": iso(post_at)})
    queue.add(view.store_id, "post_scheduled", post_at)


def _pos_revise(view: VoiceStore, ref: str, instruction: str) -> bool:
    from voice.agents import voice_reply

    review = view.review(ref)
    occasion = {**(review.get("reply_reason") or {}), "post_at": review["reply_post_at"]}
    written = voice_reply.revise(view, review, "SCHEDULED", review["reply_text"], instruction, occasion=occasion)
    if written is None:
        return False
    repo.save_review({**review, "reply_text": written["text"], "reply_source": written["source"]})
    return True


def _pos_reject(view: VoiceStore, ref: str) -> None:
    repo.save_review({**view.review(ref), "reply_status": "drafted"})


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


TASK = Kind(
    pending=_task_pending, line=_task_line, one=_task_one, item=_task_item,
    approve=lambda view, ref: proposals.apply(ref, "owner_yes"), reject=lambda view, ref: proposals.decline(ref, "owner_no"),
    many="알바생 할 일이 {n} 있어요.", question="넣을까요?", headline="알바생 할 일 넣을까요?",
    done=lambda n: "알바생 할 일을 넣었어요." if n == 1 else f"알바생 할 일 {n}개를 넣었어요.", none=("네, 알바생 할 일은 넣지 않을게요.",))

KINDS: dict[str, Kind] = {
    "negative_reply": Kind(
        pending=_neg_pending, line=_neg_line, one=_neg_one, item=_neg_item, approve=_neg_approve, reject=_neg_reject,
        many="아쉬운 리뷰가 {n} 있어요.", question="써 둔 사과 답글을 올릴까요?", headline="사과 답글 올릴까요?",
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
        says += [say(text) for text in texts]
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
    elif response.get("type") not in ("ignore", "not_understood"):
        session.pop("batch", None)


def _settle(view: VoiceStore, items: list[dict], approve: bool, said: str | None) -> None:
    for i in items:
        if not KINDS[i["job"]].pending(view, i["ref"]):
            continue  # 다른 기기에서 먼저 정했다
        (KINDS[i["job"]].approve if approve else KINDS[i["job"]].reject)(view, i["ref"])
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
    if name == "action.cancel":
        _settle(view, asked, False, said)
        texts = _done_says(view, [], asked)
    elif name == "action.approve":
        _settle(view, drop, False, said)
        _settle(view, keep, True, said)
        texts = _done_says(view, keep, drop)
    elif name == "action.revise":  # "좀 더 부드럽게": 묻는 글을 모두 지시대로 다시 써서 다시 묻는다
        revised = [i for i in asked if KINDS[i["job"]].revise and KINDS[i["job"]].revise(view, i["ref"], said or "")]
        for i in revised:
            hr.record(view.store_id, i["job"], i["ref"], "edited", said)
        lead = ["이렇게 고쳤어요."] if revised else ["지금은 고치지 못했어요."]
        return ask(load_view(view), asked + rest, mode, lead=lead) or answer("지금은 물어본 게 없어요", [say("지금은 여쭤본 게 없어요.")], [])
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


def load_view(view: VoiceStore) -> VoiceStore:
    from voice.context import load

    return load(view.store_id) or view

