"""LLM 검토: 답글이 리뷰에 맞게 쓰였는지 판정한다 (리뷰 답글 전용, 설계 문서 '검사기 3번').

입구는 inspect 다. 기준마다 좁은 질문 하나로 답글에서 해당하는 부분만 옮겨 오게 하고(quote_judge), 판정은 코드가 한다.
  - 보상 제안: 있으면 사장님 지시에 보상이 있을 때만 허용
  - 불만을 고치겠다는 말: 리뷰에 불만이 있는데 없으면 거절 (사과는 없어도 된다)
  - 가게 사정: 가게가 등록한 사실과 맞지 않으면 거절 (앞으로 하겠다는 말은 뺀다)
  - 변명·남 탓: 있으면 거절 (앞으로 하겠다는 말은 뺀다)
  - 손님을 아는 척: 단골에게 다시 찾아 준 것을 고마워하는 말 말고는 거절
  - 리뷰와 상관없는 말: 감사·사과 인사와 앞으로 하겠다는 말을 빼고 남으면 거절
왜 이렇게 하는가: 처음에는 기준 여섯 개를 LLM 한 번에 판정하게 했는데(판정 세트 놓침 23%, 오탐 16%), 기준끼리 섞이고
("지시가 있으면 보상 허용"을 지시 없이 적용), 무엇이든 '리뷰와 무관'으로 붙이고, 답글에 없는 말을 근거로 댔다.
기준마다 좁게 물으니 놓침 23% → 2%, 오탐 16% → 3% 로 줄었다 (2026-11-15 측정, critic_eval).
- 질문을 부를 수 없으면 그 기준의 금지어 정규식으로 대신 거른다. 마지막 질문(리뷰와 상관없는 말)까지 부를 수 없으면 None 을
  돌려주고, 부르는 쪽(reply_agent)이 '검토 안 됨'으로 처리한다.
"""

import re
from dataclasses import dataclass, field

from Harness.agents import quote_judge
from Harness.guards import MADE_UP_FACT_RE, MEMORY_RE, promise_hit
from Harness.spec import RunContext

KINDS = {
    "OFF_TOPIC": "리뷰와 상관없는 말",
    "NO_APOLOGY_OR_FIX": "고칠 점을 말하지 않음",
    "BLAME": "변명·남 탓",
    "COMPENSATION": "보상 약속",
    "MADE_UP_FACT": "지어낸 가게 사정",
    "FAKE_MEMORY": "손님을 기억하는 척",
}
# 단골에게는 다시 찾아 준 것을 고마워해도 된다. 지난 주문·자리·기억을 말하면 단골이어도 안 된다
REGULAR_THANKS_RE = re.compile(r"(자주|매주|매달|또|늘|다시|꾸준히)\s?(찾아|주문|시켜|들러)")
KNOWS_TOO_MUCH_RE = re.compile(r"기억|지난|저번|자리|앉|드셨던|시키셨던|드시던|시키시던")
# 손님이 리뷰에 스스로 자주 온다고 쓴 경우 ("늘 시켜 먹는데") 는 단골처럼 고마워해도 된다
SAYS_REGULAR_RE = re.compile(r"(늘|자주|매번|매주|맨날|항상|또)\s?(시켜|주문|와|오|들러|먹)")
# 앞으로 하겠다는 말은 가게 사정이 아니다. 실제 CLOVA 가 "간을 다시 확인하겠습니다"도 가게 사정으로 옮겨 와 코드에서 뺀다
FUTURE_RE = re.compile(r"겠|[할볼릴을줄]게|게요")
# 인사말. 리뷰와 상관없는 말로 옮겨 와도 뺀다 (실제 CLOVA 가 "주문해 주셔서 감사합니다"를 상관없는 말로 거절했다)
GREETING_RE = re.compile(r"감사|고맙|죄송|미안|사과드")
JOINT_RE = re.compile(r"(?<=는데|은데|지만)\s+")  # "국내산만 쓰는데 굽는 시간을 보겠습니다" 처럼 사정과 약속이 붙은 말을 나눈다
@dataclass
class Violation:
    kind: str
    quote: str
    reason: str

    def describe(self) -> str:
        return f"{KINDS[self.kind]} '{self.quote}'" + (f" ({self.reason})" if self.reason else "")


@dataclass
class Verdict:
    ok: bool
    violations: list[Violation] = field(default_factory=list)


def inspect(
    reply: str, ctx: RunContext, *, review_text: str | None = None, has_complaint: bool = False,
    regular: bool = False, owner_instruction: str | None = None,
) -> Verdict | None:
    """보상 → 고칠 점 → 가게 사정 → 변명 → 아는 척 → 리뷰와 상관없는 말 순서로 본다.
    앞에서 걸리면 거기서 돌려주고(고친 뒤 다시 검토), 마지막 질문을 부를 수 없으면 None. regular 는 매주·매달 오는 단골인지."""
    offers = quote_judge.ask("compensation", reply, ctx, review_text)
    if offers is None:  # 판별을 못 부르면 금지어 정규식으로 대신 거른다 (아래 질문들도 같다)
        offers = [part for part in quote_judge.sentences(reply) if promise_hit(part)]
    if offers and not owner_gives(owner_instruction, offers, ctx):
        return _reject("COMPENSATION", offers, "사장님이 정하지 않은 보상 제안이에요")

    if has_complaint:
        fixes = quote_judge.ask("fix", reply, ctx, review_text)
        if fixes == []:  # 묻지 못했으면(None) 이 기준은 건너뛴다
            return _reject("NO_APOLOGY_OR_FIX", [reply], "리뷰에 불만이 있는데 무엇을 고칠지 말하지 않았어요. 불만과 관련해 앞으로 어떻게 할지 한 가지 넣어 주세요")

    claims = quote_judge.ask("store_claim", reply, ctx, review_text)
    claims = _regex_hits(MADE_UP_FACT_RE, reply) if claims is None else claims
    unbacked = [claim for claim in claims if not only_promises(claim) and not backed_by_facts(claim, ctx.store_facts)]
    if unbacked:
        return _reject("MADE_UP_FACT", unbacked, "가게가 등록한 사실에 없는 가게 사정이에요. 빼고, 앞으로 할 일만 말해 주세요")

    excuses = quote_judge.ask("excuse", reply, ctx, review_text)
    excuses = [] if excuses is None else excuses  # 정규식으로 대신할 말이 없어 묻지 못하면 건너뛴다
    excuses = [part for part in excuses if not only_promises(part)]
    if excuses:
        return _reject("BLAME", excuses, "변명이나 남 탓이에요. 문제의 이유는 빼고, 사과와 앞으로 고칠 것만 말해 주세요")

    knows = quote_judge.ask("memory", reply, ctx, review_text)
    knows = _regex_hits(MEMORY_RE, reply) if knows is None else knows
    regular = regular or bool(review_text and SAYS_REGULAR_RE.search(review_text))
    pretend = [part for part in knows if not (regular and REGULAR_THANKS_RE.search(part) and not KNOWS_TOO_MUCH_RE.search(part))]
    if pretend:
        reason = "사장님은 손님을 개인적으로 알지 못해요. 이번 리뷰에 나온 내용으로만 대답해 주세요"
        if not regular:
            reason += " (단골 손님이 아니라 다시 찾아 준 것에 고마워하는 말도 쓸 수 없어요)"
        return _reject("FAKE_MEMORY", pretend, reason)

    unasked = quote_judge.ask("unasked", reply, ctx, review_text)
    if unasked is None:
        return None
    unasked = [part for part in unasked if not small_talk(part)]
    if unasked:
        return _reject("OFF_TOPIC", unasked, "손님이 리뷰에서 말하지 않은 이야기예요. 빼고 리뷰에 나온 내용에만 대답해 주세요")
    return Verdict(ok=True)


def _reject(kind: str, quotes: list[str], reason: str) -> Verdict:
    return Verdict(ok=False, violations=[Violation(kind, quote, reason) for quote in quotes])


def _regex_hits(regex: re.Pattern, reply: str) -> list[str]:
    """LLM 을 부를 수 없을 때: 정규식에 걸린 문장들."""
    return [part for part in quote_judge.sentences(reply) if regex.search(part)]


def small_talk(part: str) -> bool:
    """감사·사과 인사이거나 앞으로 하겠다는 말뿐인지 (문장마다 본다)."""
    return all(GREETING_RE.search(piece) or only_promises(piece) for piece in quote_judge.sentences(part))


def only_promises(claim: str) -> bool:
    """앞으로 하겠다는 말뿐인지. 사정과 약속이 붙어 있으면("~쓰는데 ~보겠습니다") 사정 쪽이 남아 False."""
    return all(FUTURE_RE.search(piece) for piece in JOINT_RE.split(claim) if piece.strip())


def backed_by_facts(claim: str, facts: list[str]) -> bool:
    """가게 사정이 가게가 등록한 사실과 맞는지. 사실의 끝말(서술어)을 뺀 앞부분이 그대로 들어 있으면 맞다고 본다.
    예) 사실 "국내산 돼지고기만 써요" ↔ 답글 "국내산 돼지고기만 쓰고 있지만" (앞부분 "국내산 돼지고기만" 이 같다)"""
    squashed = " ".join(claim.split())
    for fact in facts:
        words = fact.split()
        core = " ".join(words[:-1]) if len(words) >= 2 else fact.strip()
        if core and core in squashed:
            return True
    return False


# 사장님 지시와 답글의 보상 문장을 낱말로 맞대 볼 때 빼는 흔한 말
COMMON_WORDS = {"다음", "주문", "주문때", "손님", "고객", "고객님", "말씀", "같이", "함께", "그리고", "다시", "드린", "드리", "드릴", "준다", "해줘"}
PARTICLE_RE = re.compile(r"(으로|에서|에게|께서|부터|까지|이랑|하고|라고|다고|을|를|은|는|이|가|도|로|에|와|과|만|때)$")


def owner_gives(instruction: str | None, offers: list[str], ctx: RunContext) -> bool:
    """사장님 지시에 보상이 들어 있는지.
    1) 보상 정규식에 걸리면 그렇다  2) 지시 전용 질문으로 묻는다
    3) 질문을 부를 수 없으면, 답글의 보상 문장과 지시에 같은 낱말(예: "만두")이 있는지로 본다.
       사장님이 무언가 지시했는데 호출 실패 한 번으로 그 보상을 거절하지 않으려는 것이다."""
    if not instruction:
        return False
    if promise_hit(instruction):
        return True
    asked = quote_judge.ask("owner_compensation", instruction, ctx)
    if asked is not None:
        return bool(asked)
    return shares_word(instruction, offers)


def _words(text: str) -> set[str]:
    words = {PARTICLE_RE.sub("", word) for word in re.findall(r"[가-힣A-Za-z0-9]+", text)}
    return {word for word in words if len(word) >= 2 and word not in COMMON_WORDS}


def shares_word(instruction: str, offers: list[str]) -> bool:
    """답글의 보상 문장과 사장님 지시에 같은 낱말이 있는지. 예) 지시 "만두 서비스 드린다고 해 줘" ↔ 답글 "만두 서비스를 드리겠습니다"."""
    wanted = _words(instruction)
    return any(wanted & _words(offer) for offer in offers)
