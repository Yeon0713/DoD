"""아쉬운 리뷰의 원인 나누기 (규칙, LLM 없음). 2026-11-18 팀 개선안의 네 가지:
  packaging     ① 배달 지연·포장 (국물 샘, 늦음, 면 불음)
  missing       ② 메뉴 누락·오배송
  taste_temp    ③ 맛·온도 (식음, 간)
  hall_service  ④ 홀 응대
그 밖(양, 위생, 모름)은 other: 사과만 하고 알바생 카드는 만들지 않는다.

원인마다 정해 둔 것
  summary      "국물이 샜대요" (화면 폭 17 안. 도나가 말할 때 "국물이 샜다는 …"으로 바꿔 쓴다)
  card_title   알바생 교정 카드 제목 ("배달 용기 이중 실링")
  card_detail  카드 자세히에 보일 한 문장 (무엇을 어떻게)
  reply        원인과 실제로 할 조치를 적은 사과 (템플릿. 에이전트가 켜져 있으면 에이전트가 같은 조치로 쓴다)
  plain        조치를 빼고 사과만 한 글 (사장님이 "카드는 넣지 마" 했을 때, 대답이 없어 사과만 먼저 올릴 때)
보상 말(서비스, 환불, 다시 보내 드림 …)은 여기 넣지 않는다. 보상은 사장님이 정한 문장을 따로 붙인다 (voice_reply.compose).
"""

import re

from voice import width
from voice.jobs import label

COMPENSATION_KEYS = ("packaging", "missing", "taste_temp", "hall_service")
TYPE_NAMES = {"packaging": "배달·포장", "missing": "메뉴 누락", "taste_temp": "맛·온도", "hall_service": "홀 응대", "other": "그 밖"}

RULES = [
    ("missing", "missing", re.compile(r"누락|빠졌|빠져|빠진|안\s?왔|안\s?와서|다른\s?(메뉴|음식)|잘못\s?(왔|온)|오배송")),
    ("packaging", "leak", re.compile(r"샜|새서|새어|새요|흘러|넘쳐|쏟아|터졌|흥건|뚜껑")),
    # 늦어서 식었다·불었다는 배달 지연이 원인이다 (식음·불음보다 먼저 본다. 주문 기록 전에는 교정 카드를 만들지 않는다)
    ("packaging", "late", re.compile(r"늦[게어었]|오래\s?걸|한\s?시간|기다렸")),
    ("taste_temp", "cold", re.compile(r"식어서|식었|미지근|차가")),
    ("packaging", "swollen", re.compile(r"불어서|불었|퍼져|퍼졌")),
    ("hall_service", "hall", re.compile(r"불친절|응대|태도|대답|무시|직원")),
    ("taste_temp", "taste", re.compile(r"싱거|짜[요서고]|짰|맛이\s?(없|별로|이상)|간이")),
]

DETAILS = {
    "leak": {
        "summary": "국물이 샜대요", "card_title": "배달 용기 이중 실링",
        "card_detail": "국물 메뉴는 랩을 두 번 씌우고 뚜껑에 테이프를 한 번 더 붙여 주세요",
        "reply": "국물이 새서 불편하게 해 드려 정말 죄송합니다. 오늘부터 국물 메뉴는 랩을 두 번 씌우고 뚜껑을 한 번 더 확인해서 보내겠습니다.",
    },
    "late": {
        "summary": "배달이 늦었대요", "card_title": "배달 주문 바로 포장",
        "card_detail": "배달 주문이 들어오면 홀 주문보다 먼저, 들어온 순서대로 바로 포장해 주세요",
        "reply": "오래 기다리시게 해서 정말 죄송합니다. 배달 주문은 들어온 순서대로 바로 포장하도록 바로잡겠습니다.",
    },
    "swollen": {
        "summary": "면이 불어서 왔대요", "card_title": "배달 칼국수 면·국물 따로 담기",
        "card_detail": "배달 칼국수는 면과 국물을 따로 담아 주세요",
        "reply": "면이 불어서 도착해 정말 죄송합니다. 앞으로 배달 칼국수는 면과 국물을 따로 담겠습니다.",
    },
    "missing": {
        "summary": "메뉴가 빠졌대요", "card_title": "봉투 닫기 전 주문서 대조",
        "card_detail": "포장 봉투를 닫기 전에 주문서와 메뉴를 하나씩 맞춰 보세요",
        "reply": "주문하신 메뉴가 빠져서 정말 죄송합니다. 오늘부터 봉투를 닫기 전에 주문서와 하나씩 맞춰 보겠습니다.",
    },
    "cold": {
        "summary": "국물이 식어서 왔대요", "card_title": "포장 직전 국물 데우기",
        "card_detail": "배달 국물은 포장하기 바로 전에 한 번 더 끓여 담아 주세요",
        "reply": "따뜻하게 드시지 못해 정말 죄송합니다. 배달 국물은 포장하기 바로 전에 한 번 더 끓여 담겠습니다.",
    },
    "taste": {
        "summary": "맛이 아쉬웠대요", "card_title": "국물 간 한 번 더 보기",
        "card_detail": "국물은 내기 전에 간을 한 번 더 봐 주세요",
        "reply": "맛이 아쉬우셨다니 죄송합니다. 오늘부터 국물은 내기 전에 간을 한 번 더 보겠습니다.",
    },
    "hall": {
        "summary": "직원이 대답을 안 했대요", "card_title": "손님이 부르면 먼저 대답하기",
        "card_detail": "바쁠 때도 손님이 부르시면 '네, 바로 갈게요' 하고 먼저 대답해 주세요",
        "reply": "불러 주셨는데 바로 응대하지 못해 정말 죄송합니다. 손님이 부르시면 먼저 대답하도록 직원들과 다시 이야기하겠습니다.",
    },
}
PLAIN = {
    "packaging": "불편하게 해 드려 정말 죄송합니다. 포장과 배달을 꼭 다시 살펴보겠습니다.",
    "missing": "주문하신 메뉴가 빠져서 정말 죄송합니다. 주문을 꼭 다시 살펴보겠습니다.",
    "taste_temp": "만족스럽게 드시지 못해 정말 죄송합니다. 조리 상태를 꼭 다시 살펴보겠습니다.",
    "hall_service": "응대가 불편하셨다니 정말 죄송합니다. 다음에는 더 세심하게 챙기겠습니다.",
    "other": "아쉬운 점을 남겨 주셔서 감사합니다. 말씀해 주신 부분을 꼭 살펴보겠습니다.",
}
STRONG_HALL = re.compile(r"불친절|응대|태도")
# 배달 지연은 기사 탓인지 가게(조리·포장) 탓인지 주문 기록 없이 가를 수 없어 교정 카드를 만들지 않는다 (2026-11-20 결정).
# TODO(주문 기록): 주문 시각·조리 시간이 연결되면 late 를 다시 교정 대상으로
NO_CARD_YET = {"late"}
FROM_TOPIC = {"delivery": ("packaging", "late"), "taste": ("taste_temp", "taste"), "service": ("hall_service", "hall")}


def classify(review: dict) -> dict:
    """{type, detail, summary, card(title, detail) | None, reply, plain}. 아쉬운 리뷰에만 부른다."""
    text = review.get("text", "")
    found = None
    for kind, detail, pattern in RULES:
        if not pattern.search(text):
            continue
        if kind == "hall_service" and review.get("order_channel") != "hall" and not STRONG_HALL.search(text):
            continue  # 배달 리뷰의 "대답", "직원"은 홀 응대로 보지 않는다
        found = (kind, detail)
        break
    if found is None:
        found = FROM_TOPIC.get(review.get("topic") or label.classify(text, int(review.get("rating") or 0))[1], ("other", None))
    kind, detail = found
    if detail is None:
        summary = review.get("summary") or label.NEGATIVE_SUMMARIES["other"]
        return {"type": "other", "detail": None, "summary": summary, "card": None, "reply": PLAIN["other"], "plain": PLAIN["other"]}
    spec = DETAILS[detail]
    told = label.retell(text)  # 손님이 짧게 쓴 한 문장은 그대로 옮긴다 ("면이 불어서 왔대요")
    summary = told if told and width.fits(told, "review.summary") else spec["summary"]
    if detail in NO_CARD_YET:  # 가게 탓인지 알 수 없다. 조치를 약속하지 않고 사과만 한다
        return {"type": kind, "detail": detail, "summary": summary, "card": None, "reply": PLAIN[kind], "plain": PLAIN[kind]}
    return {"type": kind, "detail": detail, "summary": summary, "card": {"title": spec["card_title"], "detail": spec["card_detail"]},
            "reply": spec["reply"], "plain": PLAIN[kind]}
