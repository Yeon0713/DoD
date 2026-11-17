"""답글 코드 검사 (CLOVA 없음). server/scripts/eval_review_reply.py 의 judge() 에서 리뷰 답글 부분을 옮겨 왔다 (원래 스크립트는 그대로 둔다).

checks(text, review_text, order_channel, sentiment, complaint_types, own_menus, other_menus, today) → 검사 이름 → 값
  length_ok     10~300자
  blank_bad     채우지 않은 빈칸(자리 표시: [가게명], {이름}, ○○, OO, XX, ___)이 남음
  emoji_bad     이모지 2개 이상
  season_bad    11~2월에 여름 말, 6~8월에 겨울 말
  hall_ok       홀(배달 아님) 리뷰에 배달·포장 말이 없음 (원래 스크립트는 플랫폼 NAVER 로 봤다. 정답지에는 주문 경로가 있어 그것을 쓴다)
  other_menus   가게 메뉴 목록에 없는 메뉴 이름 (알려진 메뉴 이름 중 이 가게 목록에 없는 것)
  sentence_count 문장 수 (참고 값)
  apology_ok    불만이 있으면 사과가 있음, 불만이 없고 혼합이 아니면 사과가 없음 (해당 없으면 없음)
  picks_review  리뷰에 나온 메뉴·말을 답글이 짚음 (리뷰에 짚을 말이 없으면 없음)
형식 조건(format_ok)은 기준 문서("도나 신뢰성 평가 계획" v2)의 여섯 가지: length_ok, blank_bad, emoji_bad, hall_ok, season_bad,
other_menus. apology_ok·picks_review·sentence_count 는 참고 값이라 적합에 넣지 않는다 (응대·핵심 내용은 심판이 본다).
"""

import re

APOLOGY_RE = re.compile(r"죄송|송구|사과드")
DELIVERY_RE = re.compile(r"배달|포장|라이더|배송")
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")
SUMMER_WORDS = re.compile(r"여름|더위|무더위|폭염|장마|열대야|휴가철")
WINTER_WORDS = re.compile(r"겨울|추위|한파|폭설|연말|새해|크리스마스")
REVIEW_WORDS = [  # 리뷰 말 집기: 리뷰와 답글에 같이 나오면 짚은 것으로 본다
    r"배달", r"포장", r"양(이|도|은|을|많|적|넉넉)", r"짜", r"싱겁", r"맵|매워|매운", r"식었|식어", r"늦", r"친절", r"바삭",
    r"소스", r"국물", r"면", r"위생", r"머리카락", r"이물질", r"가격|비싸", r"고기", r"튀김", r"맥주", r"안주",
    r"주차", r"웨이팅|대기", r"분위기", r"깨끗", r"환불", r"서비스",
]
BLANK_RE = re.compile(r"\[[^\]]*\]|\{[^}]*\}|○○|OO|XX|_{3,}")
MIN_CHARS, MAX_CHARS = 10, 300
FORMAT_KEYS = ("length_ok", "blank_bad", "emoji_bad", "hall_ok", "season_bad", "other_menus")
FAILURE_NAMES = {"length_ok": f"길이({MIN_CHARS}~{MAX_CHARS}자)", "blank_bad": "빈칸", "emoji_bad": "이모지",
                 "hall_ok": "매장 리뷰에 배달 말", "season_bad": "반대 계절", "other_menus": "메뉴 목록 외 메뉴"}


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?~])\s+", text.strip()) if s.strip()]


def season_violation(text: str, today: str) -> bool:
    month = int(today[5:7])
    if month in (11, 12, 1, 2):
        return bool(SUMMER_WORDS.search(text))
    if month in (6, 7, 8):
        return bool(WINTER_WORDS.search(text))
    return False


def blank_out(text: str, names: list[str]) -> str:
    for name in sorted(names, key=len, reverse=True):
        text = text.replace(name, " ")
    return text


def other_store_menus(text: str, own: list[str], others: list[str]) -> list[str]:
    rest = blank_out(text, own)
    return sorted({name for name in others if len(name) >= 2 and name not in own and name in rest})


def checks(text: str, *, review_text: str, order_channel: str | None, sentiment: str, complaint_types: list[str],
           own_menus: list[str], other_menus: list[str], today: str) -> dict:
    result: dict = {
        "length_ok": MIN_CHARS <= len(text) <= MAX_CHARS,
        "blank_bad": bool(BLANK_RE.search(text)),
        "emoji_bad": len(EMOJI_RE.findall(text)) > 1,
        "season_bad": season_violation(text, today),
        "other_menus": other_store_menus(text, own_menus, other_menus),
        "sentence_count": len(sentences(text)),
    }
    if order_channel != "delivery":
        result["hall_ok"] = not DELIVERY_RE.search(text)
    menus_in_review = [m for m in own_menus if m in review_text]
    words_in_review = [w for w in REVIEW_WORDS if re.search(w, review_text)]
    if menus_in_review or words_in_review:
        result["picks_review"] = any(m in text for m in menus_in_review) or any(re.search(w, text) for w in words_in_review)
    if complaint_types:
        result["apology_ok"] = bool(APOLOGY_RE.search(text))
    elif sentiment != "MIXED":
        result["apology_ok"] = not APOLOGY_RE.search(text)
    return result


def format_failures(result: dict) -> list[str]:
    bad = [key for key in FORMAT_KEYS if (result.get(key) is False if key in ("length_ok", "hall_ok") else bool(result.get(key)))]
    return [FAILURE_NAMES[key] for key in bad]


def format_ok(result: dict) -> bool:
    return not format_failures(result)
