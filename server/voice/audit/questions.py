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
FIX_RELEVANCE = _q("fix_relevance", "이 할 일이 리뷰 불만의 원인을 직접 막는지 검증해 줘.",
                   "할 일에 그 불만의 원인을 직접 막는 행동이 있으면 true", "할 일에서 그 행동을 글자 그대로",
                   "할 일", "리뷰 불만")
# 덧붙인 행동 찾기는 한 번에 물으면 거의 늘 "없음"이라고 답했다 (2026-11-22 측정, 놓침 5~8/8).
# 그래서 ① 코드가 행동을 나누고(inspector.split_actions) ② 행동마다 좁게 묻는다(FIELD_NEED, MANUAL_SAME). 판정은 코드가 한다.
# (행동 나누기를 LLM 에 시키면 "씌우고"를 "씌우다"로 바꿔 옮겨 글자 그대로 검사에 걸렸다)
FIELD_NEED = Question("audit_field_need_judge", str(PROMPTS / "field_need.txt"), "이 행동이 근거 때문에 오늘 필요한 일인지 검증해 줘.",
                      "이 근거가 있어서 오늘 이 행동이 필요하면 true", "true 면 행동을 글자 그대로",
                      subject="행동", context="근거", needs_quote=False)
# 예·아니오만 본다: 참이라면서 근거 쪽 글을 옮겨 와 다시 물으면 거짓으로 바뀌었다 (2026-11-22 측정)
TODAY_NEED = Question("audit_today_need_judge", str(PROMPTS / "today_need.txt"),
                      "이 할 일을 오늘 안 하면 오늘 오는 손님이 바로 겪는 일이 생기는지 검증해 줘.",
                      "오늘 안 하면 오늘 손님이 바로 다치거나 불편하거나 먹을 수 없는 음식을 받으면 true",
                      "할 일에서 오늘 손님이 겪을 일을 막는 부분을 글자 그대로", subject="할 일", context="근거", needs_quote=False)
MANUAL_SAME = Question("audit_manual_same_judge", str(PROMPTS / "manual_same.txt"),
                       "이 행동이 반복해서 넣은 할 일들 중 하나와 같은 일인지 검증해 줘.",
                       "반복된 할 일들 중 하나가 이 행동과 같은 일을 하면 true", "true 면 행동을 글자 그대로",
                       subject="행동", context="반복해서 넣은 할 일들", needs_quote=False)
ANGLE_MENU = _q("angle_menu", "이 이야기에 고른 메뉴가 아닌 다른 음식이 나오는지 검증해 줘.",
                "고르지 않은 다른 메뉴나 음식이 나오면 true", "이야기에서 그 음식을 글자 그대로",
                "이야기", "고른 메뉴")
CAPTION_OFF = _q("caption_off", "이 글에 올릴 메뉴와 이야기 밖의 음식이나 이야기가 있는지 검증해 줘.",
                 "올릴 메뉴도, 이야기도 아닌 음식이나 이야기가 있으면 true", "글에서 그 부분을 글자 그대로",
                 "글", "올릴 메뉴와 이야기")
# 인스타 글의 가게 사정 (답글용 store_claim 질문은 답글을 전제로 해서 "방송에 나온" 같은 주장을 놓쳤다, 2026-11-22 측정)
CAPTION_CLAIM = Question("audit_caption_claim_judge", str(PROMPTS / "caption_claim.txt"),
                         "이 인스타 글에서 가게에 대한 사실을 주장한 부분을 찾아 줘.", "가게에 대한 사실 주장이 있으면 true",
                         "글에서 사실을 주장한 부분을 글자 그대로", subject="글")
HOLIDAY_SAYS = _q("holiday_says", "이 글이 그 날짜에 가게가 쉰다고 말하는지 검증해 줘.",
                  "그 날짜에 쉰다고 말한 부분이 있으면 true", "글에서 그 날짜에 쉰다고 말한 부분을 글자 그대로",
                  "글", "날짜")
TIP_GROUNDED = _q("tip_grounded", "이 고칠 점에 근거 리뷰들에 나오지 않는 문제가 있는지 검증해 줘.",
                  "근거 리뷰들에 나오지 않는 문제가 있으면 true", "고칠 점에서 그 부분을 글자 그대로",
                  "고칠 점", "근거 리뷰들")
