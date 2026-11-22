"""업무 수첩 (인사과 4-8, donna-voice/docs/agent-structure.md 9장 7단계).

사장님의 수정 지시 중 '계속 지킬 규칙'을 담당마다(+ 가게 공통 칸) 적어 두고, 담당이 다음 초안부터 지키게 한다.
모델을 학습시키지 않는다: 프롬프트에 규칙 목록과 최근 그대로 승인된 예시(답글·캡션만) 3개를 넣는다 (section).
규칙 중 코드로 볼 수 있는 것(금지 낱말, 이모티콘)은 검사에 더한다 (checks).

저장: repo 종류 notebook, id <가게>:<담당> | <가게>:common
  {store_id, agent, rules: [{id, text, said, at, banned_words, no_emoji, replaced_by, removed_at}]}
  새 규칙이 옛 규칙을 덮으면 옛 규칙에 replaced_by 를 적어 남긴다 (되살릴 수 있게). 말로 지우면 removed_at.
판정(agents/notebook_rule)은 hr.record 가 edited·rejected 이고 사장님 말이 있을 때 뒤에서 부른다 (9-0 o, judge_later).
"""

import re
import threading

from voice import clock, config, hr, notices, repo, speech
from voice.clock import iso

KIND = "notebook"
COMMON = "common"
MAX_RULES = 10  # 담당마다 프롬프트에 넣는 규칙 수. 넘으면 오래된 것부터 뺀다 (9-3)
EXAMPLES = 3
AGENT_NAMES = {"revisit": "좋은 리뷰 답글", "negative_review": "아쉬운 리뷰 답글·교정", "marketing": "인스타 글", "story_event": "포스터",
               "field_variable": "현장 변수 할 일", "manual_coach": "매뉴얼화", "holiday": "휴무 공지", COMMON: "가게 공통"}
EXAMPLE_JOBS = {"revisit": "positive_reply", "negative_review": "negative_reply", "marketing": "instagram_post"}
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def doc_id(store_id: str, agent: str) -> str:
    return f"{store_id}:{agent}"


def _doc(store_id: str, agent: str) -> dict:
    return repo.get(KIND, doc_id(store_id, agent)) or {"store_id": store_id, "agent": agent, "rules": []}


def _live(rules: list[dict]) -> list[dict]:
    return [r for r in rules if not r.get("replaced_by") and not r.get("removed_at")]


def rules(store_id: str, agent: str) -> list[dict]:
    """그 담당이 지킬 규칙: 담당 칸 + 공통 칸 (오래된 것 먼저)."""
    found = _live(_doc(store_id, agent)["rules"]) + (_live(_doc(store_id, COMMON)["rules"]) if agent != COMMON else [])
    return sorted(found, key=lambda r: r["at"])


def all_rules(store_id: str) -> list[dict]:
    """가게의 모든 살아 있는 규칙 (읽어 주기·지우기 목록). {..., agent}."""
    found = [{**r, "agent": d["agent"]} for d in repo.all_of(KIND, store_id) for r in _live(d["rules"])]
    return sorted(found, key=lambda r: r["at"])


def add(store_id: str, agent: str, text: str, said: str | None, *, replaces: list[str] | None = None,
        banned_words: list[str] | None = None, no_emoji: bool = False) -> dict:
    """규칙 하나를 적는다. replaces 의 옛 규칙(어느 칸이든)에는 replaced_by 를 적는다."""
    with repo.lock():
        rid = f"nb_{store_id}_{repo.next_number(f'notebook:{store_id}'):04d}"
        rule = {"id": rid, "text": text, "said": said, "at": iso(clock.now()), "banned_words": banned_words or [],
                "no_emoji": no_emoji, "replaced_by": None, "removed_at": None}
        for old in replaces or []:
            replace(store_id, old, rid)
        found = _doc(store_id, agent)
        repo.put(KIND, doc_id(store_id, agent), store_id, {**found, "rules": found["rules"] + [rule]})
        return rule


def _update(store_id: str, rule_id: str, **change) -> dict | None:
    with repo.lock():
        for found in repo.all_of(KIND, store_id):
            for i, r in enumerate(found["rules"]):
                if r["id"] == rule_id:
                    rules_ = list(found["rules"])
                    rules_[i] = {**r, **change}
                    repo.put(KIND, doc_id(store_id, found["agent"]), store_id, {**found, "rules": rules_})
                    return rules_[i]
    return None


def replace(store_id: str, old_id: str, new_id: str) -> dict | None:
    return _update(store_id, old_id, replaced_by=new_id)


def remove(store_id: str, rule_id: str) -> dict | None:
    return _update(store_id, rule_id, removed_at=iso(clock.now()))


def examples(store_id: str, agent: str) -> list[str]:
    """최근 그대로 승인된 글 (답글·캡션만, 9장 7단계)."""
    from voice import marketing

    job = EXAMPLE_JOBS.get(agent)
    if job is None:
        return []
    texts = []
    for event in reversed(hr.events(store_id, job)):
        if event["reaction"] != "approved":
            continue
        if job == "instagram_post":
            plan = repo.get(marketing.KIND, marketing.plan_id(store_id, event["ref"].rsplit(":", 1)[-1]))
            text = (plan or {}).get("body")
        else:
            text = (repo.review(event["ref"]) or {}).get("reply_text")
        if text and text not in texts:
            texts.append(text)
        if len(texts) == EXAMPLES:
            break
    return texts


def section(store_id: str, agent: str) -> str:
    """프롬프트 끝에 붙일 글. 규칙도 예시도 없으면 빈 글자 (프롬프트가 바뀌지 않아 캐시가 그대로 맞는다)."""
    found = rules(store_id, agent)[-MAX_RULES:]
    shown = examples(store_id, agent)
    if not found and not shown:
        return ""
    parts = ["\n\n[사장님 업무 수첩]"]
    if found:
        parts.append("사장님이 정한 규칙이에요. 꼭 지켜:\n" + "\n".join(f"- {r['text']}" for r in found))
    if shown:
        parts.append("사장님이 고치지 않고 그대로 승인한 글이에요. 말투를 참고만 하고 그대로 베끼지 마:\n" + "\n".join(f"- {t}" for t in shown))
    return "\n".join(parts)


def checks(store_id: str, agent: str, text: str) -> str | None:
    """규칙 중 코드로 볼 수 있는 것을 어겼으면 거절 문구."""
    for r in rules(store_id, agent):
        hit = [w for w in r.get("banned_words") or [] if w and w in text]
        if hit:
            return f"사장님 수첩 규칙 '{r['text']}'을 어겼어요: {', '.join(hit)} 는 쓰지 마세요"
        if r.get("no_emoji") and EMOJI_RE.search(text):
            return f"사장님 수첩 규칙 '{r['text']}'을 어겼어요: 이모티콘을 빼 주세요"
    return None


# ── 뒤에서 규칙 판정 (9-0 o) ──


def _spawn(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True, name="notebook-rule").start()


spawn = _spawn  # 테스트에서는 바로 돌린다


def judge_later(store_id: str, job: str, said: str) -> None:
    """hr.record 가 edited·rejected 를 남길 때 부른다. 대답을 늦추지 않게 뒤에서 판정한다."""
    if any(r.get("said") == said for r in all_rules(store_id)):  # 이미 그 말로 규칙을 적었다 (batch_ask.drop_offer_and_post)
        return
    if config.hr_on() and said and hr.JOBS[job].get("agent"):
        spawn(_judge, store_id, job, said)


def _judge(store_id: str, job: str, said: str) -> dict | None:
    from voice.agents import notebook_rule
    from voice.context import load

    view = load(store_id)
    agent = hr.JOBS[job]["agent"]
    if view is None:
        return None
    current = rules(store_id, agent)
    found = notebook_rule.judge(view, said, hr.JOBS[job]["name"], current)
    if not found or not found["is_rule"]:
        return None
    rule = add(store_id, COMMON if found["scope"] == "common" else agent, found["text"], said, replaces=found["replaces"],
               banned_words=found["banned_words"], no_emoji=found["no_emoji"])
    line = f"수첩에 적었어요. 앞으로 {speech.josa(found['text'], '을', '를')} 지킬게요."
    notices.push(store_id, KIND, "업무 수첩에 규칙을 적었어요", say=[line])
    return rule


# ── 말로 관리 (9-0 p) ──

ORDINAL = ["첫 번째", "두 번째", "세 번째", "네 번째", "다섯 번째", "여섯 번째", "일곱 번째", "여덟 번째", "아홉 번째", "열 번째"]
SKIP_WORDS = ("규칙", "수첩", "지워", "지우", "빼", "삭제", "없애", "취소", "줘", "그", "거", "것")


def _listing(found: list[dict]) -> list[str]:
    return [f"{ORDINAL[i] if i < len(ORDINAL) else f'{i + 1}번째'}, {AGENT_NAMES.get(r['agent'], r['agent'])}: {r['text']}."
            for i, r in enumerate(found)]


def read(store_id: str) -> dict:
    """"수첩에 뭐 적혀 있어?" """
    from voice.jobs.briefing import answer, say

    found = all_rules(store_id)
    if not found:
        return answer("수첩이 비어 있어요", [say("업무 수첩에 적은 규칙이 아직 없어요.")], [])
    rows = [{"id": r["id"], "kind": "task", "label": AGENT_NAMES.get(r["agent"], r["agent"])[:6], "value": r["text"]} for r in found[:4]]
    return answer(f"수첩 규칙 {len(found)}개예요", [say(f"업무 수첩에 규칙이 {speech.count(len(found), '개')} 있어요."),
                                                  *[say(line) for line in _listing(found)]], [{"type": "rows", "id": "notebook", "rows": rows}])


def remove_by_words(store_id: str, said: str | None, session: dict) -> dict:
    """"이모티콘 규칙 지워": 낱말로 고른다. 못 고르면 목록을 읽어 주고 번호로 고르게 한다 (session notebook_pending)."""
    from voice.dialog import intent_rules
    from voice.jobs.briefing import answer, say

    found = all_rules(store_id)
    if not found:
        return answer("수첩이 비어 있어요", [say("업무 수첩에 적은 규칙이 아직 없어요.")], [])
    n = intent_rules.normalize(said or "")
    pending = session.pop("notebook_pending", None)
    index = [int(m.group(2)) if m.group(2) else intent_rules.ORDINAL_WORDS[m.group(1)] for m in intent_rules.ORDINAL_RE.finditer(n)]
    if index and pending:
        picked = [r for r in found if r["id"] == pending[index[0] - 1]] if 1 <= index[0] <= len(pending) else []
    else:
        words = [w for w in re.findall(r"[가-힣A-Za-z]{2,}", (said or "")) if not any(w.startswith(s) for s in SKIP_WORDS)]
        picked = [r for r in found if any(w[:2] in intent_rules.normalize(r["text"]) for w in words)] if words else []
    if len(picked) != 1:
        session["notebook_pending"] = [r["id"] for r in found]
        response = answer("어느 규칙을 지울까요?", [say("어느 규칙을 지울까요?"), *[say(line) for line in _listing(found)],
                                                  say("'두 번째 규칙 지워'처럼 말씀해 주세요.")], [])
        response["expects_reply"] = True
        response["notebook_ask"] = True  # 다음 말이 이 대답이 아니면 turn.handle 이 notebook_pending 을 지운다 (앱에는 보내지 않는다)
        return response
    remove(store_id, picked[0]["id"])
    return answer("규칙을 지웠어요", [say(f"수첩에서 '{picked[0]['text']}' 규칙을 지웠어요.")], [])
