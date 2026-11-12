"""리뷰 답글 초안을 HyperCLOVA X 로 쓴다. 사장님이 리뷰를 직접 읽고 쓴 것 같은 답글이 목표다.

흐름
  1. 가게 계산이 끝나면(store_snapshot_cache) write_drafts() 가 화면에 보일 답글·재주문 인사 초안을 한꺼번에 쓴다.
     같은 리뷰는 한 번만 부르고 결과를 서버 메모리에 기억한다. 이번 한 주 답글만 쓰므로 수가 적다.
  2. /api/plan 이 할 일마다 draft_text 로 초안을 싣는다. 초안을 못 쓰면 None 이고, 앱은 자기 기본 문장을 쓴다.
  3. 사장님이 '더 짧게', '더 정중하게'를 누르면 rewrite() 가 바로 다시 쓴다 (/api/replies/rewrite).

CLOVA 에 보내는 것
  - 리뷰 답글: 가게 이름·업종, 오늘 날짜, 리뷰 글(전화번호와 @닉네임은 가림), 별점, 불만 종류, 단골 여부
  - 재주문 인사: 가게 이름·업종, 오늘 날짜, 메뉴 이름. 손님의 지난 리뷰 글은 보내지 않는다
    (사장님이 손님을 개인적으로 기억하는 것처럼 쓰면 어색해서, 기억할 재료 자체를 주지 않는다)
보내지 않는 것: 손님 id, 주문 번호, 알바 이름

안전장치: 아래 중 하나라도 걸리면 버리고 한 번 더 쓴다(두 번째는 더 차분하게). 그래도 안 되면 초안 없음(None).
  - 너무 짧거나 길다, [손님 이름] 같은 빈칸이 남았다
  - 보상 약속(환불, 무료, 쿠폰, 할인, 서비스 제공, 다시 보내 드림 등)이 들어 있다. 보상은 사장님이 직접 정할 일이다
  - 가게가 알려 준 적 없는 가게 사정(국내산, 직접 갈아 만든 등)을 지어냈다
  - 재주문 인사에 우리 가게 메뉴 이름이 하나도 없다
  - 손님을 기억하는 척한다 (기억이 나요, 지난 방문 때, 지난번에 드신 등)

프롬프트 파일 (답글 말투를 바꾸려면 이 파일들만 고치면 된다. 새로 쓰는 초안부터 반영된다)
  prompts/review_reply_prompt.txt    리뷰 답글 초안
  prompts/reorder_nudge_prompt.txt   매달 단골 재주문 인사 (리뷰 답글이 아니라 다시 찾아 달라는 인사)
  prompts/rewrite_reply_prompt.txt   더 짧게 / 더 정중하게 다시 쓰기
프롬프트 안의 {가게이름}, {업종} 은 가게 정보로 바뀐다.
"""

import datetime as dt
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

import httpx

from app.analysis.review.hcx_classifier import mask_personal_info
from app.core import clova
from app.core.clova import Post
from app.core.config import settings
from app.core.seoul_time import now_seoul
from app.planner.data_shapes import PlanItem, Review
from app.planner.rule_complaint_fix import COMPLAINT_NAMES

logger = logging.getLogger(__name__)

RewriteStyle = Literal["short", "polite"]

PROMPTS_DIR = Path(__file__).parent / "prompts"
WORKERS = 2  # 동시에 CLOVA 를 부르는 수. 너무 많으면 요청 한도(429)에 걸린다
TIMEOUT_SECONDS = 12
MIN_LENGTH, MAX_LENGTH = 10, 300  # 초안 글자 수

CUSTOMER_KINDS = {
    "QUICK": "불만이 담긴 리뷰를 남긴 손님",
    "WEEKLY": "매주 오시는 단골 손님",
    "MONTHLY": "한 달에 한 번 오시는 단골 손님",
    "BASIC": "일반 손님",
}
PLATFORM_NAMES = {"BAEMIN": "배달의민족", "NAVER": "네이버 플레이스", "YOGIYO": "요기요", "COUPANG": "쿠팡이츠"}
SENTIMENT_NAMES = {"POSITIVE": "좋음", "NEGATIVE": "나쁨", "MIXED": "칭찬과 아쉬움이 섞임"}
STYLE_NAMES = {"short": "더 짧게", "polite": "더 정중하게"}
PREFIX_RE = re.compile(r"^(답글|초안|인사|다시 쓴 답글|결과)\s*[:：]\s*")
PLACEHOLDER_RE = re.compile(r"\[[^\]]*\]|OOO|○○|XXX|\{[^}]*\}")  # 빈칸을 그대로 남긴 답
QUOTES = "\"'“”‘’「」『』`"
# 사장님이 정하지 않은 보상 약속. 이런 말이 들어간 답은 쓰지 않는다
PROMISE_RE = re.compile(
    # "서비스를 제공"만으로는 거르지 않는다: "더 정확한 서비스를 제공하겠습니다"는 약속이 아니라 다짐이다
    r"환불|무료|공짜|쿠폰|할인|증정|적립|서비스로|서비스를\s?드[리릴]|(추가|덤|공짜)\s?서비스|보내\s?드리|다시\s?보내|제공해\s?드리"
    r"|내\s?드[리릴]|그냥\s?(드|내)|챙겨\s?드[리릴]|두\s?배|덤으로|하나\s?더"
    # 사장님이 하겠다고 한 적 없는 연락 약속 ("따로 연락드리겠습니다", "바로바로 연락드리도록")
    r"|연락\s?(을\s?)?드[리릴]"
)
# 가게가 알려 준 적 없는 가게 사정(재료 산지, 조리 방법). 이런 말이 들어간 답도 쓰지 않는다
# 사장님이 손님을 개인적으로 기억하는 척하는 말. 실제로는 알 수 없어서 쓰지 않는다
MEMORY_RE = re.compile(r"기억|지난\s?방문|지난번에?\s?(드신|시키신|주문하신|오셨|방문)|저번에?\s?(드신|시키신|주문하신|오셨|방문)")
MADE_UP_FACT_RE = re.compile(
    r"국내산|국산|수입산|유기농|직접\s?(갈|빚|뽑|우려)|갈아\s?만든|비결|매일\s?아침|\d+\s?시간\s?(우려|끓)"
    # 가게가 말한 적 없는 요즘 사정 ("요즘 주문이 겹치는 일이 잦아져서")
    r"|(요즘|최근|요새).{0,25}(잦아|많아져|늘어서|늘어나|몰리)"
)
NUMBER_RE = re.compile(r"\d+")
TEMPERATURES = (0.5, 0.3)  # 첫 번째, 다시 쓸 때

_drafts: dict[tuple[str, str, str], str | None] = {}  # (가게 id, 할 일 id, 리뷰 글) → 초안. 실패하면 None
_guard = threading.Lock()


def is_enabled() -> bool:
    return bool(settings.clova_studio_api_key)


def load_prompt(name: str, store: dict) -> str:
    """프롬프트 파일을 읽어 {가게이름}, {업종} 을 채운다. 매번 읽으므로 파일을 고치면 바로 반영된다."""
    text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
    return text.replace("{가게이름}", store["name"]).replace("{업종}", store["category"])


def clean_answer(answer: str | None) -> str:
    """모델 답에서 답글만 남긴다: 머리말과 감싼 따옴표를 떼고, 여러 줄은 한 문단으로 잇는다."""
    lines = [line.strip() for line in (answer or "").splitlines() if line.strip()]
    if not lines:
        return ""
    lines[0] = PREFIX_RE.sub("", lines[0])
    return " ".join(lines).strip().strip(QUOTES).strip()


def is_usable(text: str, menus: list[str] | None = None) -> bool:
    """초안으로 써도 되는지. 길이, 빈칸, 보상 약속을 본다. menus 를 주면(재주문 인사) 메뉴 이름이 하나는 있어야 한다."""
    if not (MIN_LENGTH <= len(text) <= MAX_LENGTH) or PLACEHOLDER_RE.search(text):
        return False
    if PROMISE_RE.search(text) or MADE_UP_FACT_RE.search(text) or MEMORY_RE.search(text):
        return False
    return not menus or any(menu in text for menu in menus)


def today_line(today: dt.date | None = None) -> str:
    today = today or now_seoul().date()
    return f"- 오늘 날짜: {today.month}월 {today.day}일 (계절에 맞지 않는 말은 하지 마)"


# ── 사용자 메시지 (CLOVA 에 넘기는 리뷰 정보) ──


def review_facts(review: Review, revisit_class: str | None) -> str:
    label = review.label
    complaints = ", ".join(COMPLAINT_NAMES[t] for t in label.complaint_types) if label and label.complaint_types else "없음"
    return "\n".join(
        [
            today_line(),
            f"- 손님: {CUSTOMER_KINDS.get(revisit_class or 'BASIC', '일반 손님')}",
            f"- 리뷰를 남긴 곳: {PLATFORM_NAMES.get(review.platform, review.platform)}",
            f"- 별점: {review.rating}점 (5점 만점)",
            f"- 리뷰 분위기: {SENTIMENT_NAMES.get(label.sentiment, '모름') if label else '모름'}",
            f"- 리뷰에서 찾은 불만: {complaints}",
            f"- 리뷰 글: {mask_personal_info(review.text)}",
        ]
    )


def reply_message(review: Review, revisit_class: str | None) -> str:
    return f"아래 리뷰에 달 답글을 써 줘.\n\n{review_facts(review, revisit_class)}"


def nudge_message(menus: list[str]) -> str:
    """재주문 인사 요청. 손님의 지난 리뷰는 넣지 않는다 (손님을 기억하는 척하지 않게)."""
    return (
        "한 달에 한 번쯤 주문해 주시는 단골 손님에게 보낼 재주문 인사를 써 줘.\n\n"
        f"{today_line()}\n"
        f"- 우리 가게 메뉴: {', '.join(menus) if menus else '알 수 없음'}"
    )


# ── 초안 쓰기 ──


def write_one(item: PlanItem, review: Review, store: dict, menus: list[str], *, post: Post = httpx.post) -> str | None:
    """할 일 하나의 초안을 지금 바로 쓴다. 실패하거나 검사를 통과하지 못하면 None."""
    nudge = item.task_type == "REORDER_NUDGE"
    if nudge:
        system, user = load_prompt("reorder_nudge_prompt.txt", store), nudge_message(menus)
    else:
        system, user = load_prompt("review_reply_prompt.txt", store), reply_message(review, item.revisit_class)
    for temperature in TEMPERATURES:
        answer = clean_answer(
            clova.ask(system, user, max_tokens=300, temperature=temperature, timeout=TIMEOUT_SECONDS, post=post)
        )
        if is_usable(answer, menus if nudge else None):
            return answer
    return None


def write_drafts(items: list[PlanItem], reviews: dict[str, Review], store: dict, menus: list[str]) -> dict[str, str]:
    """답글·재주문 인사 할 일들의 초안을 쓴다. 이미 쓴 리뷰는 다시 부르지 않는다. {할 일 id: 초안}"""
    todo, result = [], {}
    for item in items:
        if item.task_type not in ("REVISIT_REPLY", "REORDER_NUDGE"):
            continue
        review = _review_of(item, reviews)
        if review is None:
            continue
        key = (store["store_id"], item.plan_id, review.text)
        with _guard:
            if key in _drafts:
                if _drafts[key]:
                    result[item.plan_id] = _drafts[key]
                continue
        todo.append((item, review, key))

    if todo and is_enabled():
        with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="reply-writer") as pool:
            written = list(pool.map(lambda job: _safe_write(job[0], job[1], store, menus), todo))
        for (item, _, key), text in zip(todo, written):
            with _guard:
                _drafts[key] = text
            if text:
                result[item.plan_id] = text
    return result


def _safe_write(item: PlanItem, review: Review, store: dict, menus: list[str]) -> str | None:
    try:
        return write_one(item, review, store, menus)
    except Exception:  # 초안을 못 써도 화면은 앱 기본 문장으로 계속 동작해야 한다
        logger.exception("답글 초안 쓰기 실패: %s", item.plan_id)
        return None


def _review_of(item: PlanItem, reviews: dict[str, Review]) -> Review | None:
    """답글은 근거 리뷰, 재주문 인사는 그 단골의 가장 최근 리뷰를 쓴다."""
    if item.task_type == "REVISIT_REPLY":
        return reviews.get(item.basis.ref_id)
    customer = item.basis.ref_id
    own = [r for r in reviews.values() if r.customer_key == customer and r.written_at <= item.approval_request_at]
    return max(own, key=lambda r: r.written_at) if own else None


# ── 다시 쓰기 ──


def keeps_numbers(original: str, rewritten: str) -> bool:
    """사장님이 쓴 숫자(날짜, 시각, 전화번호, 가격)가 다시 쓴 글에 그대로 남았는지.

    '12월부터 … 2월 말에 … 033-123-4567' 을 다듬다가 '봄부터'로 바꾸거나 전화번호를 빼면 사장님이 한 말이 달라진다.
    """
    kept = NUMBER_RE.findall(rewritten)
    return all(number in kept for number in NUMBER_RE.findall(original))


def rewrite(text: str, style: RewriteStyle, store: dict, review: Review | None = None, *, post: Post = httpx.post) -> str | None:
    """사장님이 보고 있는 답글을 더 짧게 / 더 정중하게 다시 쓴다. 실패하면 None.

    보상 약속이 새로 생기거나 사장님이 쓴 숫자가 바뀌거나 빠진 답은 쓰지 않고 한 번 더 쓴다.
    """
    user = f"고칠 방향: {STYLE_NAMES[style]}\n\n지금 답글: {text}"
    if review is not None:
        user += f"\n\n참고할 리뷰\n{review_facts(review, None)}"
    # 사장님이 버튼을 누르고 기다리는 중이라 초안보다 한 번 더 시도한다 (약속, 숫자 규칙에 걸리는 답이 가끔 두 번 이어진다)
    for temperature in (*TEMPERATURES, 0.4):
        answer = clean_answer(
            clova.ask(
                load_prompt("rewrite_reply_prompt.txt", store), user,
                max_tokens=300, temperature=temperature, timeout=TIMEOUT_SECONDS, post=post,
            )
        )
        if is_usable(answer) and keeps_numbers(text, answer):
            return answer
    return None


def forget_all() -> None:
    """기억한 초안을 모두 지운다 (테스트용)."""
    with _guard:
        _drafts.clear()
