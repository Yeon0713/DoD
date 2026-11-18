"""F8 뜻 알아듣기 규칙. 흔한 말은 LLM 없이 여기서 바로 가른다 (브리핑 단계 1초 안).

1. 띄어쓰기·문장 부호를 지우고 받아쓰기 오타를 고친다 ("부리핑 해조" → "브리핑해줘").
2. 직전 응답 종류(ask_permission, show_detail)에 따라 같은 말이 다른 뜻이 된다. "됐어"는 허락 질문 뒤에는 permission.no,
   자세히 보기에서는 detail.back.
3. 가게 손님·직원에게 하는 말로 보이면 not_for_donna.
4. 못 가르면 None. 부르는 쪽이 LLM(intent_judge)에 묻고, 그것도 안 되면 heuristic 으로 정한다.
5. 도나가 아쉬운 리뷰 처리를 물은 뒤(ask_action, 2026-11-18): 화면을 안 보고 말로만 맡기므로 잘못 실행하지 않는 쪽으로 가른다.
   - 고치는 말("쿠폰 빼고", "사과만", "카드는 넣지 마")을 먼저 본다. 올리라는 말이 같이 있으면 고친 뒤 바로 올린다(action.approve).
   - 승인은 문장 전체가 승인 말일 때만 ("응, 진행해", "그렇게 해", "올려"). "응 그거 냉장고에 넣어"는 승인이 아니다.
   - "도나야" 없이 "네", "예", "어"만 들리면 손님에게 한 대답일 수 있어 다시 묻는다 (action.unclear).
6. 알바생 일 (2026-11-18, voice/staff_orders.py): 시키기·다 했대?·취소·초대·내보내기·카톡 보내기·누구 있어?·매뉴얼.
   도나가 "보낼까요?"처럼 물은 뒤(ask_staff)의 "응"/"아니"는 staff.yes / staff.no. 시키는 말("…라고 해")을 다른 말보다 먼저 본다.
"""

import re
from dataclasses import dataclass

TYPOS = {"부리핑": "브리핑", "브리펑": "브리핑", "브링핑": "브리핑", "뿌리핑": "브리핑", "해조": "해줘", "해죠": "해줘",
         "보여조": "보여줘", "말해조": "말해줘", "읽어조": "읽어줘", "해주세여": "해주세요"}
CANONICAL = {
    "오늘일정브리핑해줘": "오늘 일정 브리핑해 줘", "오늘일정브리핑해주세요": "오늘 일정 브리핑해 주세요", "브리핑해줘": "브리핑해 줘",
    "다시말해줘": "다시 말해 줘", "화면에보여줘": "화면에 보여 줘", "자세히보여줘": "자세히 보여 줘", "읽어줘": "읽어 줘",
    "응그렇게해": "응, 그렇게 해", "아니내가볼게": "아니, 내가 볼게", "처음부터다시": "처음부터 다시", "리뷰보여줘": "리뷰 보여 줘",
}
PUNCT_RE = re.compile(r"[\s.,!?~…'\"]+")

STOP_RE = re.compile(r"^(그만|됐어그만|멈춰|스톱|조용히해|이제됐어그만)")
YES_RE = re.compile(r"^(응|어(?=$|그래|해|좋아)|네|예|그래|좋아|그렇게해|해줘|부탁해|오케이|ㅇㅇ|그러자)")
NO_RE = re.compile(r"^(아니|됐어|싫어|내가볼게|내가할게|하지마|괜찮아|안돼|놔둬)")
BACK_RE = re.compile(r"돌아가|뒤로|닫아|^됐어")
READ_RE = re.compile(r"읽어")
RESTART_RE = re.compile(r"처음부터")
REPEAT_RE = re.compile(r"다시말해|뭐라고|못들었|다시한번|한번더|다시들려|다시얘기|잘못들었")
SHOW_RE = re.compile(r"화면에|자세히")
NEXT_RE = re.compile(r"^(응|어|오케이|그래)?(다음|넘어가|계속|그다음|다음거|다음꺼|다음으로|넘겨)(줘|요|해|해줘|가자|하자)?$")
START_RE = re.compile(r"브리핑|오늘뭐있|오늘뭐해|오늘일정")
JUMP_TAIL_RE = re.compile(r"(어때|어떄|보여줘|보여|알려줘|알려|은|는|좀|얘기해줘|말해줘)$")
JUMPS = [
    (re.compile(r"아쉬운리뷰|안좋은리뷰|나쁜리뷰"), "negative"),
    (re.compile(r"좋은리뷰"), "positive"),
    (re.compile(r"예약(한|해둔|해놓은)?답글|답글예약"), "scheduling"),
    (re.compile(r"리뷰"), "reviews"),
]
QUESTION_TOPIC_RE = re.compile(r"예약|날씨|비와|비오|비소식|행사|경기|축제")
# 다른 탭을 여는 말 (문서 16-1). "홈"은 stop 과 같다
NAVIGATE = [
    (re.compile(r"매출|얼마(나)?팔|많이팔|장사(는|가)?어땠|장사잘"), "sales"),
    (re.compile(r"이번주|달력|일정탭|언제바빠"), "week"),
    (re.compile(r"설정"), "settings"),
]
HOME_RE = re.compile(r"^홈(으로|화면)?(가|가줘|으로가|보여줘)?$")
QUESTION_TAIL_RE = re.compile(r"(있어|있나|있니|와|오나|와요|어때|해|하나|몇팀|몇명|언제)$")
NOT_FOR_DONNA_RE = re.compile(
    r"테이블|어서오세요|몇분이세요|손님|치워|포장이세요|포장해|계산|주문하시|자리|드릴까요|맛있게드세요|감사합니다|안녕히|여기요|이모|삼촌|사장님|불좀|접시|앞치마"
)
DONNA_CUE_RE = re.compile(r"그거|뭐|저기|도나|알려|말해|어떻게|왜|무슨|언제")

# ask_action (아쉬운 리뷰 → 사과 답글 + 알바생 교정 카드)
DROP_COMP_RE = re.compile(r"(쿠폰|서비스|보상|감자전|사이드|안내)(은|는|도|이|가)?(빼|없이|말고|넣지마|안넣|하지마|됐어)|사과만")
NO_CARD_RE = re.compile(r"(카드|할일|알바생?|교정)(은|는|도|에|에는)?(빼|넣지마|안넣|말고|하지마|됐어)|답글만")
POST_VERB_RE = re.compile(r"올려|올리|진행|등록|그대로해|해줘|처리해")
ACTION_CANCEL_RE = re.compile(r"^(아니|안해|안할래|하지마|됐어|취소|올리지마|놔둬|그냥둬|나중에|내가(할|쓸|볼|올릴|답할)게)")
APPROVE_RE = re.compile(
    r"^(응|웅|그래|좋아|오케이|ㅇㅇ|네|예)?(그렇게|그대로|바로|빨리)?(진행|올려|올리|넣어|처리|등록)?(해|해줘|줘|요|하자|해요|해주세요|주세요|해라|할게)?$"
)
BARE_YES = {"네", "예", "어", "네네", "예예", "네에"}

# 알바생 (2026-11-18, voice/staff_orders.py). 띄어쓰기를 지운 말(normalize)에 맞춘다.
#   staff.order   "하린이한테 감자전 반죽에 전분 한 숟갈 더 넣으라고 해" (D-17), "오늘은 장칼국수 주문 받지 말라고 해" (D-20)
#   staff.remove  "정우 초대 끊어 줘", "정우 내보내 줘"        staff.invite  "하린이 초대해 줘" (D-04)
#   staff.share   "카카오톡으로 보내 줘"                       staff.status  "시킨 거 다 했대?" (D-24)
#   staff.cancel  "그거 취소해" (D-33)                         staff.list    "알바생 누구 있어?", "오늘 누구 나왔어?" (D-30)
#   staff.manual  "알바생 매뉴얼 보여 줘" (D-06)
#   staff.daily  "오늘만 할까요, 매일 할까요?"에 "매일" (매뉴얼에 넣는다)
#   staff.yes / staff.no  도나가 "보낼까요?", "카카오톡으로 보낼까요?"처럼 물은 뒤(ask_staff)의 대답
STAFF_ORDER_RE = re.compile(r"(으?라고|말라고)(좀)?(해|전해|말해|얘기해|알려|일러)|라고.*매뉴얼에(넣|추가)")
STAFF_REMOVE_RE = re.compile(r"초대(를|는)?(끊|취소|없애|막아)|내보내|그만뒀|그만둔|잘라")
STAFF_INVITE_RE = re.compile(r"초대(해|하자|할게|좀|코드|해줘|보내)|초대$")
STAFF_SHARE_RE = re.compile(r"(카톡|카카오톡|카카오)(으로|로)?(보내|공유|전해)")
STAFF_STATUS_RE = re.compile(r"(시킨|보낸)(거|것|일)(은|는)?(다)?(했|어떻게)|다했(대|어|나|냐|니|는지)|했대")
STAFF_CANCEL_RE = re.compile(r"취소|없던걸로|지워줘|보내지마")
STAFF_LIST_RE = re.compile(r"알바(생)?(들)?(은|는)?(누구|몇명|누가|명단)|누구(누구)?나왔|누가나왔|오늘나온(사람|알바)|출근한(사람|알바)")
STAFF_MANUAL_RE = re.compile(r"매뉴얼")
STAFF_TODAY_RE = re.compile(r"^(응|어|그래|네|예)?(오늘만|오늘하루만?|오늘)(해|해줘|보내|보내줘|요|이요)?$")  # 문장 전체가 대답일 때만
STAFF_DAILY_RE = re.compile(r"^(응|어|그래|네|예)?(매일|앞으로|맨날|항상|계속|매뉴얼)")
STAFF_SEND_RE = re.compile(r"^(응|어|그래|좋아|네|예)?(카톡|카카오톡)?(으로|로)?(보내|보내줘|보내요|공유해|공유해줘)")


@dataclass
class Intent:
    name: str
    owner_said: str
    jump_to: str | None = None
    by: str = "rule"  # rule | llm | heuristic
    edits: dict | None = None  # action.*: {"drop_compensation": bool, "no_card": bool}
    slots: dict | None = None  # staff.* 를 LLM 이 가른 때: {"staff_name", "task_title", "task_repeat", "task_kind"}


def normalize(text: str) -> str:
    squashed = PUNCT_RE.sub("", text)
    for wrong, right in TYPOS.items():
        squashed = squashed.replace(wrong, right)
    return squashed


def tidy(text: str) -> str:
    """사장님 말풍선에 보일 다듬은 글자 (owner_said)."""
    squashed = normalize(text)
    if squashed in CANONICAL:
        return CANONICAL[squashed]
    fixed = text.strip()
    for wrong, right in TYPOS.items():
        fixed = fixed.replace(wrong, right)
    fixed = re.sub(r"브리핑\s+해", "브리핑해", fixed)
    return fixed


def jump_target(squashed: str) -> str | None:
    return next((target for pattern, target in JUMPS if pattern.search(squashed)), None)


def match(text: str, last_type: str | None, addressed: bool = False) -> Intent | None:
    """addressed: "도나야"로 불러서 한 말. 가게 손님·직원에게 한 말(not_for_donna)로 넘기지 않는다."""
    n = normalize(text)
    said = tidy(text)
    if not n:
        return Intent("unknown", said)

    def found(name: str, jump_to: str | None = None) -> Intent:
        return Intent(name, said, jump_to)

    if STOP_RE.search(n) or HOME_RE.search(n):
        return found("stop")
    if not addressed and NOT_FOR_DONNA_RE.search(n) and not START_RE.search(n):  # "네 손님", "어서 오세요" 가 허락 대답으로 잡히지 않게 먼저 본다
        return found("not_for_donna")
    if last_type == "ask_action":
        action = match_action(n, said, addressed)
        if action is not None:
            return action
    if last_type == "ask_permission":
        if NO_RE.search(n):
            return found("permission.no")
        if YES_RE.search(n) and "아니" not in n:
            return found("permission.yes")
    if last_type == "show_detail":
        if READ_RE.search(n):
            return found("detail.read")
        if BACK_RE.search(n):
            return found("detail.back")
    if last_type == "ask_staff":
        if STAFF_DAILY_RE.search(n) and "아니" not in n:
            return found("staff.daily")  # "오늘만 할까요, 매일 할까요?" 에 "매일"
        if NO_RE.search(n):
            return found("staff.no")
        if STAFF_TODAY_RE.search(n):
            return found("staff.yes")  # "오늘만 할까요, 매일 할까요?" 에 "오늘만"
        if (YES_RE.search(n) or STAFF_SEND_RE.search(n) or STAFF_SHARE_RE.search(n)) and "아니" not in n and not STAFF_ORDER_RE.search(n):
            return found("staff.yes")
    staff = match_staff(n)
    if staff:
        return found(staff)
    if RESTART_RE.search(n):
        return found("briefing.restart")
    if REPEAT_RE.search(n):
        return found("briefing.repeat")
    if SHOW_RE.search(n):
        return found("detail.show")
    if READ_RE.search(n):
        return found("detail.read")
    if BACK_RE.search(n) and last_type in ("show_detail", "answer"):
        return found("detail.back")
    if NEXT_RE.search(n):
        return found("briefing.next")
    target = jump_target(n)
    if target and (JUMP_TAIL_RE.search(n) or n in ("리뷰", "답글", "좋은리뷰", "아쉬운리뷰", "예약답글")):
        return found("briefing.jump", target)
    if START_RE.search(n):
        return found("briefing.start")
    if QUESTION_TOPIC_RE.search(n) and (QUESTION_TAIL_RE.search(n) or text.strip().endswith("?")):
        return found("question")  # "이번 주 비 와?"는 묻는 말이다. 탭을 열지 않는다
    for pattern, tab in NAVIGATE:
        if pattern.search(n):
            return found(f"navigate.{tab}")
    return None


def match_staff(n: str) -> str | None:
    """알바생에 관한 말이면 그 뜻 이름. 시키는 말을 먼저 본다 ("예약 취소하라고 해"는 취소가 아니라 시키기)."""
    for pattern, name in ((STAFF_ORDER_RE, "staff.order"), (STAFF_REMOVE_RE, "staff.remove"), (STAFF_INVITE_RE, "staff.invite"),
                          (STAFF_SHARE_RE, "staff.share"), (STAFF_STATUS_RE, "staff.status"), (STAFF_CANCEL_RE, "staff.cancel"),
                          (STAFF_LIST_RE, "staff.list"), (STAFF_MANUAL_RE, "staff.manual")):
        if pattern.search(n):
            return name
    return None


def edits_in(n: str) -> dict:
    return {"drop_compensation": bool(DROP_COMP_RE.search(n)), "no_card": bool(NO_CARD_RE.search(n))}


def match_action(n: str, said: str, addressed: bool) -> Intent | None:
    """ask_action 뒤의 대답. 못 가르면 None (다른 규칙으로 넘긴다)."""
    edits = edits_in(n)
    if edits["drop_compensation"] or edits["no_card"]:
        return Intent("action.approve" if POST_VERB_RE.search(n) else "action.edit", said, edits=edits)
    if ACTION_CANCEL_RE.search(n):
        return Intent("action.cancel", said)
    if n in BARE_YES and not addressed:
        return Intent("action.unclear", said)
    if APPROVE_RE.fullmatch(n) and n:
        return Intent("action.approve", said, edits={"drop_compensation": False, "no_card": False})
    if REPEAT_RE.search(n):
        return Intent("action.repeat", said)
    return None


def heuristic(text: str, addressed: bool = False) -> Intent:
    """규칙도 LLM 도 못 가를 때. 도나에게 묻는 말 같으면 unknown(못 알아들음), 아니면 not_for_donna(가만히).
    "도나야"로 부른 말은 언제나 도나에게 한 말이다."""
    n = normalize(text)
    name = "unknown" if addressed or DONNA_CUE_RE.search(n) or text.strip().endswith("?") else "not_for_donna"
    return Intent(name, tidy(text), by="heuristic")
