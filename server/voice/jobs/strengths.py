"""F5 좋은 리뷰 일주일 분석 (규칙, LLM 없음).

좋은 리뷰마다 아래 사전으로 좋아한 점을 찾고(한 리뷰에서 같은 점은 한 번만), 많이 나온 순서로 3개를 고른다.
'국물'은 가게 메뉴 중 국물 요리(전골·탕·찌개·국) 이름을 붙인다: "곱창전골 국물".
"""

import re

from voice import width

PATTERNS = {
    "soup": re.compile(r"국물"),
    "kind": re.compile(r"(?<!불)친절"),
    "portion": re.compile(r"양[이도]?\s?(많|넉넉|푸짐)|푸짐|넉넉"),
    "fast": re.compile(r"빨리\s?(왔|와|오)|빠른\s?배달|배달이?\s?빨"),
}
LABELS = {"kind": "친절한 응대", "portion": "넉넉한 양", "fast": "빠른 배달"}
HEADLINES = {"soup": "국물 맛을 좋아하세요", "kind": "친절함을 좋아하세요", "portion": "넉넉한 양을 좋아하세요", "fast": "빠른 배달을 좋아하세요"}
KEEP_TIPS = {
    "soup": "국물 맛은 지금처럼 진하게 지켜 주세요",
    "kind": "지금처럼 친절한 응대를 이어 가세요",
    "portion": "넉넉한 양은 지금처럼 지켜 주세요",
    "fast": "빠른 배달은 지금처럼 지켜 주세요",
}
SOUP_RE = re.compile(r"전골|탕|찌개|국$")


def keys_in(text: str) -> list[str]:
    return [key for key, pattern in PATTERNS.items() if pattern.search(text)]


def label_of(key: str, menus: list[dict]) -> str:
    if key == "soup":
        soup = next((m["name"] for m in menus if SOUP_RE.search(m["name"])), None)
        return width.fit("bars.label", f"{soup} 국물", "국물 맛") if soup else "국물 맛"
    return LABELS[key]


def analyze(reviews: list[dict], menus: list[dict]) -> dict:
    """좋은 리뷰들 → {total, top: [{key, label, count}] (최대 3, 많은 순), headline, keep_tip}."""
    counts: dict[str, int] = {}
    for review in reviews:
        for key in keys_in(review["text"]):
            counts[key] = counts.get(key, 0) + 1
    order = list(PATTERNS)
    top = sorted(counts.items(), key=lambda kv: (-kv[1], order.index(kv[0])))[:3]
    items = [{"key": key, "label": label_of(key, menus), "count": n} for key, n in top]
    first = items[0]["key"] if items else None
    return {
        "total": len(reviews),
        "top": items,
        "headline": HEADLINES[first] if first else "좋은 리뷰가 많아요",
        "keep_tip": KEEP_TIPS[first] if first else "지금처럼 맛과 응대를 지켜 주세요",
    }
