"""브리핑 밖의 말 (v0.2.1 하루 시나리오 D-01 ~ D-06, D-17 ~ D-33).

알바생에게 시키기, 전화 예약 적기, 매뉴얼 더하기, 보낸 것 취소, 알림 읽기, 오늘 정리, 인스타, 처음 한 번 하는 설정.
뜻은 규칙으로만 알아듣는다 (에이전트가 붙으면 F8로 바뀐다). 문장은 Figma 대본을 따른다.

보내거나 적는 일은 늘 한 번 확인받는다: 응답 type "ask" + expects_reply, 세션의 pending 에 기다리는 일을 둔다.
"""
from __future__ import annotations

import datetime as dt
import re

from . import briefing as br
from .data import STATE, WEEKDAYS, at, clock_label, date_label, new_id, now, present_staff, staff_by_call
from .briefing import S, kor

YES = ("응", "그래", "좋아", "네", "어그", "그렇게", "맞아", "보내", "적어", "넣어", "해줘", "그걸로", "부탁", "올려")
NO = ("아니", "됐어", "싫어", "하지마", "안돼", "취소", "말고")


def norm(text: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", (text or "").lower())


def _answer(headline: str, say: list[dict], cards: list[dict] | None = None, ask: str | None = None) -> dict:
    out = {"type": "ask" if ask else "answer", "briefing": None, "headline": headline, "say": say, "cards": cards or [], "expects_reply": bool(ask)}
    if ask:
        out["ask"] = {"key": ask}
    return out


def _rows(card_id: str, rows: list[tuple[str, str, str]], title: str | None = None) -> dict:
    c = {"type": "rows", "id": card_id, "rows": [{"id": i, "kind": k, "value": v} for i, k, v in rows]}
    if title:
        c["title"] = title
    return c


def _time_ago(iso: str) -> str:
    return clock_label(dt.datetime.fromisoformat(iso))


# ---------- 할 일의 제목 만들기 (목업 규칙) ----------
KNOWN_TASKS = [
    # (말에 들어 있는 것, 제목, 짧은 이름, 하는 때, 매일/오늘만, 꼭 확인, 할 것/하지 말 것)
    (("전분",), "감자전 전분 한 숟갈 더", "감자전 반죽", "open", "today", False, "do"),
    (("장칼국수",), "새뱅이 장칼국수 주문 받지 않기", "장칼국수 품절", "open", "today", False, "dont"),
    (("새뱅이",), "새뱅이 장칼국수 주문 받지 않기", "장칼국수 품절", "open", "today", False, "dont"),
    (("알레르기",), "메밀 알레르기 먼저 여쭤보기", "메밀 알레르기 확인", "open", "daily", True, "do"),
    (("면", "따로"), "배달 칼국수는 면과 국물 따로 담기", "배달 면 따로 담기", "open", "daily", False, "do"),
    (("바닥",), "바닥 닦기", "바닥 닦기", "open", "today", False, "do"),
    (("수저",), "수저 채우기", "수저 채우기", "open", "today", False, "do"),
    (("냉장고",), "마감 때 냉장고 온도 적기", "냉장고 온도", "closing", "daily", False, "do"),
]


SAID = [
    (("전분",), "감자전 전분 더 넣으라고 해"),
    (("장칼국수",), "장칼국수 오늘 주문 받지 말라고 해"),
    (("새뱅이",), "장칼국수 오늘 주문 받지 말라고 해"),
    (("알레르기",), "메밀 알레르기 매뉴얼에 넣어 줘"),
    (("면", "따로"), "배달 면 따로 담으라고 매뉴얼에 넣어 줘"),
]


def short_said(text: str) -> str | None:
    """사장님 말 풍선에 보일 다듬은 말. 긴 말은 뜻만 남겨 줄인다 (owner_said 는 '다듬은 글자', 문서 4-3)."""
    t = norm(text)
    for keys, said in SAID:
        if all(k in t for k in keys):
            return said
    r = parse_reservation(text) if "예약" in t else None
    if r:
        return f"{WEEKDAYS[r['date'].weekday()]}요일 {r['hour'] - 12 if r['hour'] > 12 else r['hour']}시 {next((w for w, n in NUM.items() if n == r['people']), r['people'])} 분 예약 적어 줘"
    return None


def task_from(text: str) -> dict:
    t = norm(text)
    for keys, title, short, phase, repeat, must, kind in KNOWN_TASKS:
        if all(k in t for k in keys):
            if "매뉴얼" in t and repeat == "today":
                repeat = "daily"
            return {"title": title, "short": short, "phase": phase, "repeat": repeat, "must_confirm": must, "kind": kind}
    # 모르는 일: "…(하)라고 해 줘" 앞의 말을 "…기"로 만든다 (닦으 → 닦기, 채우 → 채우기)
    m = re.search(r"(?:한테|에게|모두|다들)?\s*(.+?)(?:으?라고|하지\s*말라고|말라고)", text)
    body = (m.group(1) if m else text).strip()
    body = re.sub(r"^.*?(한테|에게)\s*", "", body)
    body = re.sub(r"으$", "", body)
    title = body if body.endswith("기") else f"{body}기"
    return {"title": title, "short": title, "phase": "open", "repeat": "daily" if "매뉴얼" in t else "today", "must_confirm": False, "kind": "do"}


def _who(text: str) -> tuple[str, dict | None, str | None]:
    """받는 사람. ('all', None, None) / ('one', staff, None) / ('unknown', None, 들은 이름)."""
    m = re.search(r"([가-힣]{1,4}?)(?:이)?(?:한테|에게)", text)
    if not m or m.group(1) in ("모두", "다들", "다", "전부", "알바생", "알바"):
        return "all", None, None
    word = m.group(1)
    s = staff_by_call(word) or staff_by_call(word.rstrip("이"))
    if s:
        return "one", s, None
    return "unknown", None, word.rstrip("이")


def _recipient_label(to: str) -> str:
    if to == "all":
        return "오늘 나온 사람 모두"
    if to == "everyone":
        return f"알바생 {len([s for s in STATE['staff'] if s['joined']])}명 모두"
    s = next(x for x in STATE["staff"] if x["id"] == to)
    return f"{s['call']} 씨"


def _confirm_task(task: dict, to: str) -> dict:
    """보내기 전에 확인받는다 (D-17, D-19, D-20)."""
    today = task["repeat"] == "today"
    dont = task["kind"] == "dont"
    to_label = _recipient_label(to)
    rows = [("cf_to", "person", to_label)]
    if task["must_confirm"]:
        rows.append(("cf_task", "warning", task["title"]))
        rows.append(("cf_when", "time", "매일 영업 중에"))
        headline = "모두에게 확인받을까요?"
        say = [S(f"매뉴얼 영업 중에 \"{task['title']}\"를 넣고, {to_label.replace('명 모두', ' 명 모두').replace('알바생 5', '알바생 다섯')}에게 확인을 받을까요?", ["cf_task"])]
        caption = None
    else:
        rows.append(("cf_task", "ban" if dont else "task", task["title"]))
        rows.append(("cf_when", "time", "오늘만" if today else "매일"))
        if today:
            headline = "오늘만 이렇게 보낼까요?"
            say = [S(f"{to_label}에게 \"{'오늘은 ' if dont else '오늘 '}{task['title']}\"를 보낼게요.", ["cf_task"]),
                   S("내일은 원래대로예요. 맞아요?" if dont else "오늘만이에요. 맞아요?", ["cf_when"])]
            caption = "내일은 원래대로 돌아가요." if dont else None
        else:
            headline = "매뉴얼에 넣을까요?"
            say = [S(f"매뉴얼 영업 중에 \"{task['title']}\"를 넣을게요. 맞아요?", ["cf_task"])]
            caption = None
    if caption:
        say[0]["caption"] = caption
    return _answer(headline, say, [_rows("confirm", rows)], ask="send_task")


def _send(task: dict, to: str, owner_words: str | None) -> dict:
    tk = {
        "id": new_id("tk"), "title": task["title"], "short": task.get("short", task["title"]), "phase": task["phase"],
        "repeat": task["repeat"], "must_confirm": task["must_confirm"], "kind": task["kind"],
        "sent_at": now().isoformat(), "owner_words": owner_words, "to": to,
        "done": {}, "confirmed": {}, "canceled": False,
    }
    STATE["tasks"].append(tk)
    STATE["last_sent"] = tk["id"]
    return tk


# ---------- 처음 한 번 하는 설정 (D-01 ~ D-06) ----------
def instagram_connect_card() -> dict:
    return _answer(
        "인스타를 연결해 주세요",
        [S("인스타를 연결해 주세요.", caption="비밀번호는 도나가 보지 않아요."), S("버튼을 누르면 인스타 화면이 열려요."),
         S("로그인은 거기서 하시고, 비밀번호는 제가 보지 않아요.")],
        [_rows("safe", [("sf_login", "lock", "인스타 화면에서 로그인해요"), ("sf_ask", "message", "올리기 전에 꼭 여쭤봐요"),
                        ("sf_off", "off", "언제든 끊을 수 있어요")]),
         {"type": "action", "id": "connect", "label": "인스타그램으로 연결하기", "action": "instagram_connect"}],
    )


def menus_answer() -> dict:
    card = br.menus_card(4)
    card.update(title=None, editable=True)
    return _answer("메뉴 사진을 가져왔어요",
                   [S("네이버 플레이스에 올리신 메뉴 사진을 가져왔어요."), S("이번 달 많이 나간 순서예요."),
                    S("바꾸고 싶은 사진만 \"바꾸기\"로 새로 찍으면 돼요.")], [card])


def invite_answer(s: dict) -> dict:
    code = next((c for c, sid in STATE["invites"].items() if sid == s["id"]), None)
    if not code:
        code = {"st_harin": "482017", "st_jungwoo": "735106"}.get(s["id"], f"{(len(STATE['invites']) + 5) * 137 % 900000 + 100000}")
        STATE["invites"][code] = s["id"]
    spaced = f"{code[:3]} {code[3:]}"
    spoken = " ".join("공일이삼사오육칠팔구"[int(ch)] for ch in code)
    spoken = f"{spoken[:5]}, {spoken[6:]}"
    copula = "예요" if code[-1] in "2459" else "이에요"
    msg = f"{STATE['store']['name']} 알바생 할 일 페이지예요.\n아래 주소로 들어와서\n초대 코드를 넣어 주세요."
    return _answer(f"{s['call']} 씨 초대 코드예요",
                   [S(f"{s['call']} 씨 초대 코드를 만들었어요."), S(f"{spoken}{copula}."), S(f"화면의 글을 {s['call']} 씨에게 보내 주세요.")],
                   [{"type": "invite", "id": "invite", "message": msg, "url": "donna.app/s/choongjang", "code": spaced}],
                   ask="invite_share")


def manual_setup_answer() -> dict:
    return _answer("기본 매뉴얼로 시작할까요?",
                   [S("음식점에서 많이 쓰는 매뉴얼로 시작할까요?", caption="안 맞는 건 말로 빼면 돼요."),
                    S("영업 준비, 영업 중, 마감 세 묶음이에요."),
                    S(f"{STATE['store']['name']}에 안 맞는 건 빼고, 더할 건 말로 넣으면 돼요.")],
                   [{"type": "manual", "id": "manual", "groups": [
                       {"id": "mn_before", "kind": "before_open", "label": "영업 준비", "text": "바닥과 테이블 청소, 수저 채우기"},
                       {"id": "mn_open", "kind": "open", "label": "영업 중", "text": "빈 테이블 정리, 품절 안내"},
                       {"id": "mn_closing", "kind": "closing", "label": "마감", "text": "바닥 청소, 냉장고 온도 적기"},
                   ]}], ask="manual_setup")


def staff_list_answer() -> dict:
    joined = [s for s in STATE["staff"] if s["joined"]]
    here = {s["id"] for s in present_staff()}
    items = [{"id": s["id"], "name": s["name"], "sub": f"{_time_ago(s['in_at'])}에 들어옴" if s["id"] in here else "오늘 아직 안 나옴"} for s in joined]
    return _answer(f"알바생 {len(joined)}명이에요",
                   [S(f"알바생은 {kor(len(joined))} 명이에요."), S(f"오늘 나온 사람은 {kor(len(here))} 명이에요." if here else "오늘 나온 사람은 아직 없어요.")],
                   [{"type": "people", "id": "staff", "title": "알바생", "items": items}])


# ---------- 영업 중 (D-17 ~ D-33) ----------
def task_status_answer() -> dict:
    tasks = [t for t in STATE["tasks"] if not t["canceled"] and t["phase"] != "before_open" and t["kind"] == "do"]
    staff = {s["id"]: s for s in STATE["staff"]}

    def finished(t):
        marks = t["confirmed"] if t["must_confirm"] else t["done"]
        return (min(marks.items(), key=lambda kv: kv[1]) if not t["must_confirm"] else max(marks.items(), key=lambda kv: kv[1])) if marks else None

    left = [t for t in tasks if not finished(t)]
    done = [t for t in tasks if finished(t)]
    items = []
    for t in left:
        items.append({"id": t["id"], "title": t["title"], "sub": "모두에게 보냄" if t["to"] in ("all", "everyone") else f"{staff[t['to']]['call']} 씨에게 보냄", "state": "todo"})
    for t in done:
        sid, when = finished(t)
        items.append({"id": t["id"], "title": ("알레르기 여쭤보기 확인" if "알레르기" in t["title"] else t["short"] if t["repeat"] == "today" and len(t["title"]) > 12 else t["title"]),
                      "sub": f"{staff[sid]['call']} 씨가 {_time_ago(when)}에 함", "state": "done"})
    if left:
        head = f"{left[0]['short']}만 남았어요" if len(left) == 1 else "아직 안 한 게 있어요"
        say = [S(f"{left[0]['short']} 적기만 남았어요." if len(left) == 1 and left[0]["short"] == "냉장고 온도" else f"{head}.")]
        if len(left) == 1 and left[0]["phase"] == "closing":
            say.append(S("마감 때 하는 일이에요."))
    else:
        head = "다 했어요"
        say = [S("시킨 건 다 했어요.")]
    if done:
        names = ", ".join(("메밀 알레르기 확인" if "알레르기" in t["title"] else "스토리 손님 서비스" if "스토리" in t["title"] else t["short"]) for t in done[:3])
        say.append(S(f"{names}은 다 했어요." if names[-1] in "인반" else f"{names}는 다 했어요."))
    return _answer(head, say, [{"type": "checklist", "id": "sent", "title": "알바생에게 시킨 것", "items": items}])


def notice_read_answer() -> dict:
    ig = STATE["instagram"]
    m = ig["story_mentions"][-1] if ig["story_mentions"] else None
    if not m:
        return _answer("새 알림이 없어요", [S("새 알림이 없어요.")])
    return _answer("스토리에 올려 주셨어요",
                   [S("손님 한 분이 스토리에 올려 주셨어요.", ["nt_who"]), S("서비스 드리기는 알바생에게 보냈어요.", ["nt_task"]),
                    S("리스토리는 인스타에서 직접 눌러 주셔야 해요.", ["nt_restory"])],
                   [_rows("story", [("nt_who", "person", f"@{m['handle']} 님이 올림"), ("nt_task", "task", "알바생이 서비스 드려요"),
                                    ("nt_restory", "instagram", "내 스토리 올리기는 직접")])])


def day_summary_answer() -> dict:
    ig = STATE["instagram"]
    left = [t for t in STATE["tasks"] if not t["canceled"] and t["kind"] == "do" and t["phase"] != "before_open"
            and not (t["confirmed"] if t["must_confirm"] else t["done"])]
    stories = len(ig["story_mentions"])
    rows = [("sm_reviews", "reviews", "답글 5개, 새 리뷰 2개"), ("sm_insta", "instagram", f"피드 {1 if ig['posted_at'] else 0}개, 손님 스토리 {stories}개")]
    say = [S("오늘 106만 원 팔았어요."), S("지난주 화요일보다 10만 원 적어요.", caption="지난주 화요일보다 10만 원 적어요."),
           S("리뷰 다섯 개에 답했고 새 리뷰가 두 개 왔어요.", ["sm_reviews"])]
    if ig["posted_at"] and stories:
        say.append(S(f"아침에 올린 피드를 보고 손님 {kor(stories)} 분이 스토리에 태그해 주셨어요.", ["sm_insta"]))
    if left:
        rows.append(("sm_staff", "staff", f"알바생은 {left[0]['short']}만 남음"))
        say.append(S(f"알바생에게 시킨 건 {left[0]['short']}만 남았어요.", ["sm_staff"]))
    out = _answer("오늘 106만 원 팔았어요", say, [_rows("summary", rows)])
    out["focus_rest"] = "sm_staff"
    return out


def instagram_status_answer() -> dict:
    ig = STATE["instagram"]
    if not ig["connected"]:
        return _answer("인스타 연결이 끊겼어요", [S("인스타 연결이 끊겼어요. 다시 연결해 주세요.")])
    n = len(ig["story_mentions"])
    rows = [("is_feed", "image", "오늘 아침 인기 메뉴 피드" if ig["posted_at"] else "오늘은 아직 안 올림")]
    if n:
        rows.append(("is_story", "users", f"손님 {n}명이 스토리에 올림"))
    say = [S(f"오늘 아침에 올린 인기 메뉴 피드에 좋아요가 {kor(ig['likes']) if ig['likes'] < 16 else '마흔두' if ig['likes'] == 42 else ig['likes']} 개예요.", ["is_feed"])]
    if n:
        served = all(t["done"] for t in STATE["tasks"] if "스토리" in t["title"] and not t["canceled"])
        tail = ("서비스를 받으셨어요." if n == 1 else f"{kor(n)} 분 모두 서비스를 받으셨어요.") if served else "서비스는 알바생에게 보냈어요."
        say.append(S(f"손님 {kor(n)} 분이 스토리에 매장을 태그해 주셨고, {tail}", ["is_story"]))
    return _answer(f"좋아요가 {ig['likes']}개예요", say, [_rows("insta", rows)])


def tomorrow_answer() -> dict:
    d = now().date() + dt.timedelta(days=1)
    resv = [r for r in STATE["reservations"] if dt.datetime.fromisoformat(r["starts_at"]).date() == d]
    w = next((x for x in STATE["weather"] if x["date"] == d.isoformat()), None)
    w2 = next((x for x in STATE["weather"] if x["date"] == (d + dt.timedelta(days=1)).isoformat()), None)
    rows, say = [], [S(f"내일은 {WEEKDAYS[d.weekday()]}요일이에요.")]
    if w:
        rows.append(("tm_weather", "weather", f"{w['label']}" + (", 모레는 비" if w2 and w2["label"] == "비" else "")))
    if resv:
        joined = {"흐림": "흐리고 ", "비": "비가 오고 ", "맑음": "맑고 ", "구름": "구름이 끼고 "}.get(w["label"], "") if w else ""
        say.append(S(f"{joined}저녁 예약이 {kor(len(resv))} 팀이에요.", ["tm_weather"]))
    rows.append(("tm_staff", "staff", "알바생 매뉴얼은 평소대로"))
    replies = [it for it in STATE["scheduled"] if dt.datetime.fromisoformat(it["post_at"]).date() == d + dt.timedelta(days=1)]
    if w2 and w2["label"] == "비" and replies:
        rows.append(("tm_reply", "clock", f"{WEEKDAYS[(d + dt.timedelta(days=1)).weekday()]}요일 아침 답글 {len(replies)}개"))
        say.append(S(f"모레 {WEEKDAYS[(d + dt.timedelta(days=1)).weekday()]}요일엔 비가 와서, 비 오는 날 옹심이를 권하는 답글이 아침에 나가요.", ["tm_reply"]))
    say.append(S("자세한 건 내일 아침 브리핑에서 말씀드릴게요."))
    return _answer(f"저녁 예약이 {len(resv)}팀이에요" if resv else "내일은 평소와 같아요", say, [_rows("tomorrow", rows)])


def cancel_answer() -> dict:
    tid = STATE.get("last_sent")
    t = next((x for x in STATE["tasks"] if x["id"] == tid), None)
    if not t or t["canceled"]:
        return _answer("취소할 게 없어요", [S("방금 보낸 것이 없어요.")])
    if t["done"]:
        sid = next(iter(t["done"]))
        s = next(x for x in STATE["staff"] if x["id"] == sid)
        return _answer("벌써 했어요", [S(f"{s['call']} 씨가 벌써 했어요. 취소하지 않았어요.")])
    t["canceled"] = True
    t["canceled_at"] = now().isoformat()
    return _answer("취소했어요", [S(f"\"{t['title']}\"를 취소했어요."), S("알바생 화면에서 지웠어요.", caption="알바생 화면에서 지웠어요.")],
                   [{"type": "checklist", "id": "canceled", "title": "알바생에게 시킨 것",
                     "items": [{"id": t["id"], "title": t["title"], "sub": f"{_time_ago(t['canceled_at'])}에 취소함", "state": "canceled"}]}])


def unknown_name_answer(word: str) -> dict:
    here = present_staff()
    near = next((s for s in STATE["staff"] if s["joined"] and (s["call"].startswith(word) or word.startswith(s["call"][:1]))), None)
    items = [{"id": s["id"], "name": s["name"], "sub": f"{_time_ago(s['in_at'])}에 들어옴"} for s in here]
    say = [S(f"{word} 씨는 없어요.")]
    if near:
        say.append(S(f"비슷한 이름은 {near['call']} 씨예요."))
        say.append(S(f"{near['call']} 씨에게 보낼까요?", caption=f"{near['call']} 씨에게 보낼까요?"))
    return _answer(f"{word} 씨는 없어요", say, [{"type": "people", "id": "present", "title": "오늘 나온 알바생", "items": items}],
                   ask="pick_staff"), near


def not_joined_answer(s: dict) -> dict:
    invited = s.get("invited_at")
    days = (now().date() - dt.datetime.fromisoformat(invited).date()).days if invited else None
    when = "어제" if days == 1 else "오늘" if days == 0 else f"{days}일 전"
    return _answer(f"{s['call']} 씨는 아직 안 들어왔어요",
                   [S(f"{s['call']} 씨는 아직 알바생 화면에 안 들어왔어요."),
                    S("들어와야 할 일을 볼 수 있어요.", caption="들어와야 할 일을 볼 수 있어요."),
                    S("초대를 다시 보낼까요, 아니면 다른 사람에게 보낼까요?")],
                   [_rows("invite_state", [("nj_invite", "invite", f"{when} 카카오톡으로 초대함")])], ask="not_joined")


# ---------- 전화 예약 (D-18) ----------
WEEK = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
NUM = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10, "열한": 11, "열두": 12}


def parse_reservation(text: str) -> dict | None:
    m = re.search(r"([월화수목금토일])요일", text)
    if not m:
        return None
    d = now().date()
    ahead = (WEEK[m.group(1)] - d.weekday()) % 7 or 7
    day = d + dt.timedelta(days=ahead)
    hm = re.search(r"(\d{1,2})\s*시", text)
    hour = int(hm.group(1)) if hm else 19
    if hour < 10 or "저녁" in text or "오후" in text:
        hour = hour + 12 if hour < 12 else hour
    pm = re.search(r"(\d+)\s*(?:분|명)", text.replace("시", " ")) or None
    people = int(pm.group(1)) if pm and int(pm.group(1)) < 60 else None
    if people is None:
        for w, n in sorted(NUM.items(), key=lambda kv: -len(kv[0])):
            if re.search(rf"{w}\s*(분|명)", text):
                people = n
                break
    nm = re.search(r"([가-힣]+\s*사장님|[가-힣]{2,4})\s*이름으로", text)
    name = nm.group(1).replace(" ", " ") if nm else None
    if name and not name.endswith("님"):
        name = f"{name} 님"
    return {"date": day, "hour": hour, "people": people or 2, "name": name}


def reservation_confirm(r: dict) -> dict:
    t = dt.time(r["hour"])
    day_word = WEEKDAYS[r["date"].weekday()]
    who = f"{r['name']}, {r['people']}명" if r["name"] else f"{r['people']}명"
    spoken = f"{r['date'].month}월 {r['date'].day}일 {day_word}요일 {clock_label(t)}, {kor(r['people'])} 분" + (f", {r['name']}" if r["name"] else "") + ". 맞아요?"
    return _answer(f"{day_word}요일 {clock_label(t)}, 맞아요?", [S(spoken, ["rv_date", "rv_time", "rv_who"])],
                   [_rows("reservation", [("rv_date", "date", date_label(r["date"])), ("rv_time", "time", clock_label(t)), ("rv_who", "phone", who)])],
                   ask="reservation")


# ---------- 알아듣기 ----------
def classify(t: str, raw: str, sess: dict) -> str | None:
    """브리핑 밖의 요청이면 intent, 아니면 None. t 는 norm() 한 말."""
    p = sess.get("pending")
    if p:
        if p["kind"] in ("pick_staff", "not_joined") and re.search(r"(한테|에게)", raw):
            return "pending.redirect"
        if p["kind"] == "not_joined" and "초대" in t:
            return "pending.reinvite"
        if p["kind"] == "invite_share" and ("카카오" in t or "보내" in t):
            return "invite.share"
        if p["kind"] == "invite_share" and ("알겠" in t or "됐" in t):
            return "pending.no"
        if any(w in t for w in NO) and not t.startswith("응"):
            return "pending.no"
        if any(t.startswith(w) or w in t for w in YES):
            return "pending.yes"
    if "취소" in t and ("보낸" in t or "방금" in t):
        return "task.cancel"
    if "알림" in t and "읽" in t:
        return "notice.read"
    if "인스타" in t and "열어" in t:
        return "instagram.open"
    if "인스타" in t and "연결" in t:
        return "instagram.connect"
    if "인스타" in t and ("어때" in t or "어떻" in t or "좋아요" in t):
        return "instagram.status"
    if "메뉴" in t and "사진" in t:
        return "menus.show"
    if "초대" in t:
        return "staff.invite"
    if ("알바" in t and ("누구" in t or "몇명" in t)) or "누구있" in t:
        return "staff.list"
    if "매뉴얼" in t and ("만들" in t or "정해" in t or "짜" in t):
        return "manual.setup"
    if "시킨" in t and ("했" in t or "어떻" in t):
        return "staff.status"
    if "예약" in t and ("적어" in t or "잡아" in t or "넣어" in t):
        return "reservation.add"
    if "정리" in t and ("오늘" in t or t.startswith("정리")):
        return "day.summary"
    if "내일" in t and ("뭐" in t or "있" in t or "어때" in t):
        return "tomorrow"
    if "다시보내" in t and re.search(r"(한테|에게)", raw):
        return "task.resend"
    if "매뉴얼" in t and ("넣어" in t or "더해" in t or "추가" in t):
        return "manual.add"
    if re.search(r"(라고|말라고)(해|좀|전해)?(줘|주세요)?$", t) or "하라고" in t or "말라고" in t:
        return "staff.task"
    return None


def handle(intent: str, raw: str, sess: dict) -> dict:
    p = sess.get("pending")
    if intent == "pending.no":
        sess["pending"] = None
        if p and p["kind"] == "invite_share":
            return _answer("알겠어요", [S("알겠어요.")])
        return _answer("보내지 않았어요", [S("알겠어요. 보내지 않았어요.")])
    if intent == "pending.yes" and p:
        sess["pending"] = None
        return _do(p, sess)
    if intent == "pending.redirect" and p:
        kind, s, word = _who(raw)
        if kind != "one":
            return unknown_name_answer(word or "그")[0]
        sess["pending"] = None
        tk = _send(p["task"], s["id"], p.get("words"))
        return _sent_answer(tk)
    if intent == "pending.reinvite" and p:
        sess["pending"] = None
        s = next(x for x in STATE["staff"] if x["id"] == p["staff_id"])
        out = invite_answer(s)
        sess["pending"] = {"kind": "invite_share", "staff_id": s["id"]}
        return out
    if intent == "invite.share":
        sess["pending"] = None
        s = next((x for x in STATE["staff"] if p and x["id"] == p.get("staff_id")), None)
        return {**_answer("카카오톡을 열게요", [S("카카오톡을 열게요. 받을 사람은 직접 골라 주세요.")]), "open": "kakao_share"}
    if intent == "task.cancel":
        return cancel_answer()
    if intent == "notice.read":
        return notice_read_answer()
    if intent == "instagram.open":
        return {**_answer("인스타를 열게요", [S("그 스토리가 있는 인스타 화면을 열게요.")]), "open": "instagram"}
    if intent == "instagram.connect":
        return instagram_connect_card()
    if intent == "instagram.status":
        return instagram_status_answer()
    if intent == "menus.show":
        return menus_answer()
    if intent == "staff.invite":
        kind, s, word = _who(raw.replace("초대", "한테 초대"))
        if kind != "one":
            name = re.search(r"([가-힣]{2,3}?)(?:이)?\s*초대", raw)
            word = name.group(1) if name else None
            s = staff_by_call(word) if word else None
        if not s:
            return _answer("누구를 초대할까요?", [S("누구를 초대할까요? 이름을 말씀해 주세요.")])
        sess["pending"] = {"kind": "invite_share", "staff_id": s["id"]}
        return invite_answer(s)
    if intent == "staff.list":
        return staff_list_answer()
    if intent == "manual.setup":
        sess["pending"] = {"kind": "manual_setup", "extra": "냉장고" in norm(raw)}
        return manual_setup_answer()
    if intent == "staff.status":
        return task_status_answer()
    if intent == "reservation.add":
        r = parse_reservation(raw)
        if not r:
            return _answer("무슨 요일이에요?", [S("무슨 요일, 몇 시 예약인지 말씀해 주세요.")])
        sess["pending"] = {"kind": "reservation", "r": r}
        return reservation_confirm(r)
    if intent == "day.summary":
        return day_summary_answer()
    if intent == "tomorrow":
        return tomorrow_answer()
    if intent == "task.resend":
        kind, s, word = _who(raw)
        target = next((t for t in reversed(STATE["tasks"]) if t["must_confirm"] and not t["canceled"]), None)
        if kind == "one" and target:
            STATE["notices"].append({"id": new_id("nt"), "for": "staff", "staff_id": s["id"], "task_id": target["id"], "at": now().isoformat()})
            return _answer(f"{s['call']} 씨 화면에 다시 띄웠어요", [S(f"{s['call']} 씨 화면에 다시 띄웠어요.")])
        return _answer("누구에게 보낼까요?", [S("누구에게 다시 보낼까요?")])
    if intent in ("manual.add", "staff.task"):
        task = task_from(raw)
        if intent == "manual.add":
            task["repeat"] = "daily"
            if not task["must_confirm"]:
                task["kind"] = "rule"  # 늘 지키는 규칙. 알바생 화면에 체크할 일로 올라가지 않는다
        kind, s, word = _who(raw)
        if kind == "unknown":
            out, near = unknown_name_answer(word)
            sess["pending"] = {"kind": "pick_staff", "task": task, "to": near["id"] if near else None, "words": raw}
            return out
        if kind == "one" and not s["joined"]:
            sess["pending"] = {"kind": "not_joined", "task": task, "staff_id": s["id"], "words": raw}
            return not_joined_answer(s)
        to = s["id"] if kind == "one" else ("everyone" if task["must_confirm"] or task["repeat"] == "daily" else "all")
        sess["pending"] = {"kind": "send_task", "task": task, "to": to, "words": raw, "in_briefing": bool(sess.get("idx"))}
        return _confirm_task(task, to)
    return _answer("잘 못 들었어요", [S("잘 못 들었어요. 한 번 더 말씀해 주세요.")])


def _sent_answer(tk: dict) -> dict:
    to = _recipient_label(tk["to"])
    return _answer("알바생 화면에 올렸어요", [S(f"{to}에게 보냈어요." if tk["repeat"] == "today" else "매뉴얼에 넣었어요.")],
                   [_rows("sent", [("st_to", "person", to), ("st_task", "ban" if tk["kind"] == "dont" else "warning" if tk["must_confirm"] else "task", tk["title"]),
                                   ("st_when", "time", "오늘만" if tk["repeat"] == "today" else "매일")])])


def _do(p: dict, sess: dict) -> dict:
    if p["kind"] == "send_task":
        tk = _send(p["task"], p["to"], p.get("words"))
        if p.get("in_briefing") and "면" in tk["title"]:
            br.morning("manual")
            return {"continue_briefing": True, "prefix": S("매뉴얼에 넣었어요."), "caption": "배달 면 따로 담기는 매뉴얼에 넣었어요."}
        return _sent_answer(tk)
    if p["kind"] == "pick_staff" and p.get("to"):
        return _sent_answer(_send(p["task"], p["to"], p.get("words")))
    if p["kind"] == "reservation":
        r = p["r"]
        starts = dt.datetime(r["date"].year, r["date"].month, r["date"].day, r["hour"], tzinfo=now().tzinfo)
        STATE["reservations"].append({"id": new_id("rs"), "starts_at": starts.isoformat(), "party_size": r["people"],
                                      "kind": "group" if r["people"] >= 8 else "general", "name": r["name"]})
        return _answer("예약을 적었어요", [S("적었어요. 그날 아침 브리핑 일정에 같이 나와요.")],
                       [_rows("reservation", [("rv_date", "date", date_label(r["date"])), ("rv_time", "time", clock_label(dt.time(r["hour"]))),
                                              ("rv_who", "phone", f"{r['name']}, {r['people']}명" if r["name"] else f"{r['people']}명")])])
    if p["kind"] == "manual_setup":
        STATE["manual"] = {"before_open": ["바닥과 테이블 청소", "수저 채우기"], "open": ["빈 테이블 정리", "품절 안내"], "closing": ["바닥 청소", "냉장고 온도 적기"]}
        if not any(t["id"] == "tk_floor" for t in STATE["tasks"]):
            STATE["tasks"] += [
                {"id": "tk_floor", "title": "오픈 전 바닥 닦기", "short": "바닥 닦기", "phase": "before_open", "repeat": "daily", "must_confirm": False,
                 "kind": "do", "sent_at": None, "owner_words": None, "to": "all", "done": {}, "confirmed": {}, "canceled": False},
                {"id": "tk_fridge", "title": "마감 때 냉장고 온도 적기", "short": "냉장고 온도", "phase": "closing", "repeat": "daily", "must_confirm": False,
                 "kind": "do", "sent_at": None, "owner_words": None, "to": "all", "done": {}, "confirmed": {}, "canceled": False},
            ]
        return _answer("매뉴얼을 정했어요", [S("매뉴얼을 정했어요."), S("날마다 그날 나온 알바생 화면에 올라가요.")])
    return _answer("알겠어요", [S("알겠어요.")])
