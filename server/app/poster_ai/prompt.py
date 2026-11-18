"""그림 모델에 줄 프롬프트 만들기: 상황 + 사장님이 고른 멘트·모양·더 넣을 말 + 첨부 그림(로고, 메뉴 사진)의 역할.

글자는 사장님이 고른 그대로 한 글자도 바꾸지 말고 넣으라고 한다 (그림 모델이 글자를 지어내지 않게).
인스타 스토리(9:16)는 위·아래에 앱 버튼이 덮이므로 중요한 글자는 가운데에 두라고 한다.
"""

from dataclasses import dataclass

from app.poster_ai.situation import Situation

STYLES = {
    "PHOTO": ("음식 사진을 크게", "Hero food photography: the menu photo fills most of the poster, warm natural light, text on a soft gradient band so it stays readable."),
    "CLEAN": ("깔끔한 디자인", "Clean modern layout: warm off-white or brand-brown solid background, the food photo as a neat rounded cut-out, generous whitespace, simple bold sans-serif Korean type."),
    "FESTIVAL": ("행사·응원 분위기", "Festive event mood through color and one or two small motifs that match the occasion (no confetti storms or piles of stickers)."),
    "WARM": ("따뜻한 손글씨", "Cozy hand-made feel: warm paper texture, hand-lettered style Korean headline, at most one or two small doodles."),
}

WEATHER_EN = {"HOT": "hot day", "COLD": "chilly day", "RAIN": "rainy day", "SNOW": "snowy day", "MONSOON": "rainy-season day"}


@dataclass
class PosterChoice:
    headline: str
    line: str
    extra: str = ""  # 더 넣고 싶은 말 (예: 쿠폰 안내, 영업시간)
    style: str = "PHOTO"
    menu: str = ""  # 멘트가 권하는 메뉴
    photo_labels: tuple[str, ...] = ()  # 첨부한 메뉴·매장 사진 이름 (첨부 순서대로)
    has_logo: bool = False


def build(s: Situation, c: PosterChoice) -> str:
    occasion = {
        "EVENT": f"Nearby local event on that day: \"{s.title}\" (Korean festival/event).",
        "GAME": f"Sports game on that day: \"{s.title}\". Fans watch and cheer.",
        "WEEKEND": "Ordinary weekend promotion.",
        "RAIN": "Rainy day: a same-day in-store event inviting customers to come in despite the rain (voice/instagram/story_event.py).",
    }[s.kind]
    weather = ", ".join(WEATHER_EN[t] for t in s.weather_tags) or ("winter-like cold weather" if s.season == "WINTER" else "summer heat" if s.season == "SUMMER" else "")
    images = []
    n = 1
    if c.has_logo:
        images.append(
            f"- Attached image {n}: the restaurant's LOGO. Its background has already been removed (transparent PNG). "
            "Reproduce it exactly as given, same shapes and letters, do not redraw, restyle or recolor it. "
            "Place it small near the top or bottom DIRECTLY on the poster: no white box, plate, badge, sticker, frame or background shape behind it. "
            "Put it over a calm area of the image where it stays readable."
        )
        n += 1
    for label in c.photo_labels:
        images.append(f"- Attached image {n}: real photo of \"{label}\" from this restaurant. The food shown must look like this photo (same dish, same bowl/plating). You may crop, enlarge or cut it out, but do not invent a different dish.")
        n += 1
    text = [f'- Headline (largest): "{c.headline.replace(chr(10), " / ")}"  (" / " marks a line break)', f'- Sub line: "{c.line}"']
    if c.extra.strip():
        text.append(f'- Extra info (smaller): "{c.extra.strip()}"')
    text.append(f'- Footer (small): "{s.store_name}" and "{s.address}"')
    lines = [
        "Create ONE vertical Instagram Story poster image for a small Korean restaurant.",
        "Canvas: portrait 9:16 (1080x1920 story). If 9:16 is not available, use the tallest portrait size.",
        f"Restaurant: {s.store_name} ({s.category}). Date shown on poster: {s.date_ko}.",
        occasion,
        f"Weather/season mood: {weather}." if weather else "",
        f"Featured menu: {c.menu}." if c.menu else "",
        f"Style: {STYLES.get(c.style, STYLES['PHOTO'])[1]}",
        "Design must be CLEAN and SIMPLE, not busy: one hero food photo, a calm uncluttered background, generous empty space, "
        "only the text listed below, at most 2 small decorative motifs, a limited palette of 2-3 colors. "
        "No cluttered collage, no busy scenery behind the text, no stacks of icons, stickers, banners, confetti or frames.",
        "Reference images:",
        *images,
        "Korean text to render EXACTLY as written (verbatim, correct Hangul spelling, no other words, no English):",
        *text,
        f'- Date line: "{s.date_ko}"',
        "Layout rules: keep the top 12% and bottom 15% free of important text (Instagram UI covers them); "
        "large, high-contrast, easy-to-read Korean typography for older readers; no prices, no QR codes, no fake discounts, "
        "no other brand names or logos, no watermarks, no people's faces.",
        "Use the built-in image generation tool exactly once. Do not run shell commands and do not write code. "
        "When done, reply with only the saved image file path.",
    ]
    return "\n".join(line for line in lines if line)
