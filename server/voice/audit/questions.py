"""감사팀 2차 감사의 새 질문 (감사팀 계획 7-2). 묻는 법은 Harness.agents.quote_judge 와 같다: 해당하는 부분을 글자 그대로 옮겨 오게 하고
판정은 inspector.py 의 코드가 한다. 프롬프트는 prompts/<이름>.txt (원칙 한 줄 + 판단 기준 몇 줄, 예시를 늘리지 않는다).

context 는 사용자 메시지 첫 줄에 함께 주는 글의 이름, subject 는 검증할 글의 이름이다.
"""

from pathlib import Path

from Harness.agents.quote_judge import Question

PROMPTS = Path(__file__).parent / "prompts"


def _q(name: str, ask: str, found: str, quote: str, subject: str, context: str) -> Question:
    return Question(f"audit_{name}_judge", str(PROMPTS / f"{name}.txt"), ask, found, quote, subject=subject, context=context)


CARD_PROMISE = _q("card_promise", "이 답글이 가게가 할 조치를 하겠다고 말했는지 검증해 줘.",
                  "답글에 그 조치를 하겠다고 한 부분이 있으면 true", "답글에서 그 조치를 하겠다고 한 부분을 글자 그대로",
                  "답글", "가게가 할 조치")
OCCASION_CLAIM = _q("occasion_claim", "이 답글에 올리는 날 정보와 맞지 않는 이야기가 있는지 검증해 줘.",
                    "올리는 날 정보와 맞지 않는 날씨·행사·경기·계절 이야기가 있으면 true", "답글에서 그 부분을 글자 그대로",
                    "답글", "올리는 날 정보")
FIX_RELEVANCE = _q("fix_relevance", "이 할 일에 리뷰 불만을 줄이는 행동이 있는지 검증해 줘.",
                   "할 일에 그 불만을 직접 줄이는 행동이 있으면 true", "할 일에서 그 행동을 글자 그대로",
                   "할 일", "리뷰 불만")
FIELD_LINK = _q("field_link", "이 할 일에 근거와 상관없는 부분이 있는지 검증해 줘.",
                "할 일에 근거와 상관없는 부분이 있으면 true", "할 일에서 근거와 상관없는 부분을 글자 그대로",
                "할 일", "근거")
TODAY_NEED = _q("today_need", "이 할 일을 오늘 안 하면 손님이 바로 겪는 일이 생기는지 검증해 줘.",
                "오늘 안 하면 오늘 손님이 바로 겪는 일이 생기면 true", "할 일에서 오늘 손님과 바로 이어지는 부분을 글자 그대로",
                "할 일", "근거")
MANUAL_ADDED = _q("manual_added", "다듬은 한 줄에 반복된 할 일들에 없는 행동이 있는지 검증해 줘.",
                  "반복된 할 일들에 없는 행동이 있으면 true", "다듬은 한 줄에서 그 행동을 글자 그대로",
                  "다듬은 한 줄", "반복해서 넣은 할 일들")
ANGLE_MENU = _q("angle_menu", "이 이야기에 고른 메뉴와 상관없는 부분이 있는지 검증해 줘.",
                "고른 메뉴와 상관없는 부분이 있으면 true", "이야기에서 그 부분을 글자 그대로",
                "이야기", "고른 메뉴")
CAPTION_OFF = _q("caption_off", "이 글에 올릴 메뉴와 이야기 밖의 음식이나 이야기가 있는지 검증해 줘.",
                 "올릴 메뉴도, 이야기도 아닌 음식이나 이야기가 있으면 true", "글에서 그 부분을 글자 그대로",
                 "글", "올릴 메뉴와 이야기")
HOLIDAY_SAYS = _q("holiday_says", "이 글이 그 날짜에 가게가 쉰다고 말하는지 검증해 줘.",
                  "그 날짜에 쉰다고 말한 부분이 있으면 true", "글에서 그 날짜에 쉰다고 말한 부분을 글자 그대로",
                  "글", "날짜")
TIP_GROUNDED = _q("tip_grounded", "이 고칠 점에 근거 리뷰들에 나오지 않는 문제가 있는지 검증해 줘.",
                  "근거 리뷰들에 나오지 않는 문제가 있으면 true", "고칠 점에서 그 부분을 글자 그대로",
                  "고칠 점", "근거 리뷰들")
