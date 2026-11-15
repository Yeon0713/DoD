"""F8 뜻 알아듣기 규칙. 흔한 말은 LLM 없이 여기서 바로 가른다 (브리핑 단계 1초 안).

1. 띄어쓰기·문장 부호를 지우고 받아쓰기 오타를 고친다 ("부리핑 해조" → "브리핑해줘").
2. 직전 응답 종류(ask_permission, show_detail)에 따라 같은 말이 다른 뜻이 된다. "됐어"는 허락 질문 뒤에는 permission.no,
   자세히 보기에서는 detail.back.
3. 가게 손님·직원에게 하는 말로 보이면 not_for_donna.
4. 못 가르면 None. 부르는 쪽이 LLM(intent_judge)에 묻고, 그것도 안 되면 heuristic 으로 정한다.
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
QUESTION_TAIL_RE = re.compile(r"(있어|있나|있니|와|오나|와요|어때|해|하나|몇팀|몇명|언제)$")
NOT_FOR_DONNA_RE = re.compile(
    r"테이블|어서오세요|몇분이세요|손님|치워|포장이세요|포장해|계산|주문하시|자리|드릴까요|맛있게드세요|감사합니다|안녕히|여기요|이모|삼촌|사장님|불좀|접시|앞치마"
)
DONNA_CUE_RE = re.compile(r"그거|뭐|저기|도나|알려|말해|어떻게|왜|무슨|언제")


@dataclass
class Intent:
    name: str
    owner_said: str
    jump_to: str | None = None
    by: str = "rule"  # rule | llm | heuristic


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


def match(text: str, last_type: str | None) -> Intent | None:
    n = normalize(text)
    said = tidy(text)
    if not n:
        return Intent("unknown", said)

    def found(name: str, jump_to: str | None = None) -> Intent:
        return Intent(name, said, jump_to)

    if STOP_RE.search(n):
        return found("stop")
    if NOT_FOR_DONNA_RE.search(n) and not START_RE.search(n):  # "네 손님", "어서 오세요" 가 허락 대답으로 잡히지 않게 먼저 본다
        return found("not_for_donna")
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
        return found("question")
    return None


def heuristic(text: str) -> Intent:
    """규칙도 LLM 도 못 가를 때. 도나에게 묻는 말 같으면 unknown(못 알아들음), 아니면 not_for_donna(가만히)."""
    n = normalize(text)
    name = "unknown" if DONNA_CUE_RE.search(n) or text.strip().endswith("?") else "not_for_donna"
    return Intent(name, tidy(text), by="heuristic")
