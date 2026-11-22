"""F8 뜻 알아듣기 규칙. 흔한 말은 LLM 없이 여기서 바로 가른다 (브리핑 단계 1초 안).

1. 띄어쓰기·문장 부호를 지우고 받아쓰기 오타를 고친다 ("부리핑 해조" → "브리핑해줘").
2. 직전 응답 종류(ask_permission, show_detail)에 따라 같은 말이 다른 뜻이 된다. "됐어"는 허락 질문 뒤에는 permission.no,
   자세히 보기에서는 detail.back. "인스타에 올릴까요?"를 물은 뒤(instagram)에는 "응"이 instagram.post, "다음 사진"이 instagram.next_photo.
3. 가게 손님·직원에게 하는 말로 보이면 not_for_donna.
4. 못 가르면 None. 부르는 쪽이 LLM(intent_judge)에 묻고, 그것도 안 되면 heuristic 으로 정한다.
5. 도나가 아쉬운 리뷰 처리를 물은 뒤(ask_action, 2026-11-18): 화면을 안 보고 말로만 맡기므로 잘못 실행하지 않는 쪽으로 가른다.
   - 고치는 말("쿠폰 빼고", "사과만", "카드는 넣지 마")을 먼저 본다. 올리라는 말이 같이 있으면 고친 뒤 바로 올린다(action.approve).
   - 승인은 문장 전체가 승인 말일 때만 ("응, 진행해", "그렇게 해", "올려"). "응 그거 냉장고에 넣어"는 승인이 아니다.
   - "도나야" 없이 "네", "예", "어"만 들리면 손님에게 한 대답일 수 있어 다시 묻는다 (action.unclear).
6. 알바생 일 (2026-11-18, voice/staff_orders.py): 시키기·다 했대?·취소·초대·내보내기·카톡 보내기·누구 있어?·매뉴얼.
   도나가 "보낼까요?"처럼 물은 뒤(ask_staff)의 "응"/"아니"는 staff.yes / staff.no. 시키는 말("…라고 해")을 다른 말보다 먼저 본다.
   - 스토리 이벤트 포스터를 물은 뒤에도 같은 규칙을 쓴다. "다시 그려 줘"는 action.redo, "스토리만"은 할 일을 빼라는 말.
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
# 아쉬운 리뷰의 내용을 묻는 말 ("아쉬운 리뷰 읽어 줘", "아쉬운 리뷰 뭐라고 썼어?"). 아쉬운 리뷰로 옮겨 첫 리뷰를 읽는다
CONTENT_RE = re.compile(r"내용|읽어|뭐라고")
SHOW_RE = re.compile(r"화면에?(보여|띄워|좀|봐)|화면에|자세히")  # "화면 보여 줘"처럼 조사가 빠져도
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
# 예측·의견을 묻는 질문 꼴 ("오늘 바쁠까", "뭐부터 할까", "손님 많니"). "도나야"로 부른 말일 때만 질문으로 본다
QUESTION_FORM_RE = re.compile(r"(까|니|야)$")
# 실행 동사가 든 질문 ("인스타 올릴 수 있어?", "인스타에 올려도 돼?")은 묻는 말로 확정하지 않는다 (판정 에이전트)
ACT_ASK_RE = re.compile(r"인스타|스토리|올리|올려|올릴")
# 앱이 호출어를 떼지 못하고 글자 그대로 보낸 말 ("도나야 오늘 손님 많을까")
WAKE_RE = re.compile(r"^(도나|또나|돈아|토나)야")
# 물건 자리를 묻는 말은 직원끼리 한 말이다 ("매출 장부 어디 뒀니?"). 탭을 열지 않는다
WHERE_RE = re.compile(r"어디(뒀|있|놨)")
NOT_FOR_DONNA_RE = re.compile(
    r"테이블|어서오세요|몇분이세요|손님|치워|포장이세요|포장해|계산|주문하시|자리|드릴까요|맛있게드세요|감사합니다|안녕히|여기요|이모(?!티콘)|삼촌|사장님|불좀|접시|앞치마"
)
# 인스타 (D-14, D-15). INSTA_* 는 "인스타에 올릴까요?"를 물은 뒤에만 본다
INSTA_NEXT_RE = re.compile(r"다음사진|다음장|다른사진|옆사진|사진넘겨|넘겨")
INSTA_LATER_RE = re.compile(r"^(나중|아니|됐어|다음에|내일|싫어|놔둬)|하지마|안올려|올리지마|올리지말|말아")
INSTA_POST_RE = re.compile(r"올려|올리자|^(응|어(?=$|그래|해|좋아)|네|예|그래|좋아|오케이|그렇게해|해줘|부탁해|ㅇㅇ|그러자)")
# 브리핑 밖에서 바로 올리는 말. 다시 묻지 않고 올리므로 문장 끝이 올리라는 말일 때만 본다
# ("인스타에 올리지 마", "인스타 올릴 수 있어?", "올려도 돼?"는 아니다)
POST_ORDER = r"(?<!안)(올려|올리자)(줘|줘요|주세요|줄래|봐|요)?$"
STORY_POST_RE = re.compile(r"스토리.*" + POST_ORDER)
FEED_POST_RE = re.compile(r"인스타.*" + POST_ORDER)
DONNA_CUE_RE = re.compile(r"그거|뭐|저기|도나|알려|말해|어떻게|왜|무슨|언제")

# ask_action (아쉬운 리뷰 → 사과 답글 + 알바생 교정 카드)
DROP_COMP_RE = re.compile(r"(쿠폰|서비스|보상|감자전|사이드|안내)(은|는|도|이|가)?(빼|없이|말고|넣지마|안넣|하지마|됐어)|사과만"
                          r"|(쿠폰|서비스|보상)[가-힣]{0,6}(말|얘기|내용|부분|문장)(은|는|도)?(빼|없이|말고)")  # "서비스 준다는 말은 빼고"
NO_CARD_RE = re.compile(r"(카드|할일|알바생?|교정)(은|는|도|에|에는)?(빼|넣지마|넣지말|안넣|말고|하지마|됐어)|답글만|스토리만")
# ask_tasks (알바생 할 일 묶어 묻기, 2026-11-20): "두 번째는 빼", "1번이랑 3번은 빼고 넣어"
ORDINAL_WORDS = {"첫": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4, "넷": 4}
ORDINAL_RE = re.compile(r"(첫|두|둘|세|셋|네|넷)번?째|([1-4])번째?")
DROP_WORD_RE = re.compile(r"빼|말고|넣지마|넣지말|안넣|제외")
REDO_RE = re.compile(r"다시(그려|그리|만들어|만들)")
# 자유로운 수정 (인사과 6단계): 정해진 고침(edits: 쿠폰·카드·번호 빼기)으로 안 잡히는 "좀 더 …하게", "…는 쓰지 마"
REVISE_RE = re.compile(r"더[가-힣]*게|짧게|길게|부드럽게|정중하게|친근하게|공손하게|쓰지마|쓰지말|이모티콘|느낌표|말투|딱딱")  # 스토리 이벤트 포스터 다시 그리기 (instagram/story_event.py)
POST_VERB_RE = re.compile(r"올려|올리|진행|등록|그대로해|해줘|처리해|넣어|넣자|예약")  # 예약: 칭찬 답글 "이렇게 예약할까요?" (인사과 4-b)
ACTION_CANCEL_RE = re.compile(r"^(아니|안해|안할래|하지마|됐어|취소|올리지마|예약안해|예약하지마|놔둬|그냥둬|나중에|내가(할|쓸|볼|올릴|답할)게)")
APPROVE_RE = re.compile(
    r"^(응|웅|그래|좋아|오케이|ㅇㅇ|네|예)?(그렇게|그대로|바로|빨리)?(진행|올려|올리|넣어|처리|등록|예약)?(해|해줘|줘|요|하자|해요|해주세요|주세요|해라|할게)?$"
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
# 사후 취소 (인사과 5단계, jobs/done_report.py): 지우는 말 + (번호 또는 답글·인스타). 알바생 일 말이 있으면 staff.cancel 로 둔다
UNDO_RE = re.compile(r"취소|지워|지우|내려")
UNDO_TARGET_RE = re.compile(r"답글|인스타|게시물|올린")
STAFF_WORD_RE = re.compile(r"할일|알바|시킨")
# 업무 수첩 (인사과 7단계, voice/notebook.py): "수첩에 뭐 적혀 있어?", "이모티콘 규칙 지워"
NOTEBOOK_RE = re.compile(r"수첩|규칙")
NOTEBOOK_REMOVE_RE = re.compile(r"지워|지우|빼|삭제|없애|취소")
STAFF_LIST_RE = re.compile(r"알바(생)?(들)?(은|는)?(누구|몇명|누가|명단)|누구(누구)?나왔|누가나왔|오늘나온(사람|알바)|출근한(사람|알바)")
STAFF_MANUAL_RE = re.compile(r"매뉴얼")
STAFF_TODAY_RE = re.compile(r"^(응|어|그래|네|예)?(오늘만|오늘하루만?|오늘)(해|해줘|보내|보내줘|요|이요)?$")  # 문장 전체가 대답일 때만
STAFF_DAILY_RE = re.compile(r"^(응|어|그래|네|예)?(매일|앞으로|맨날|항상|계속|매뉴얼)")
# 쉬는 날 (2026-11-20, voice/holidays.py): "다음 주 수요일 쉬어", "26일 쉬는 거 취소해". 날짜를 말해야 한다
HOLIDAY_RE = re.compile(r"쉬어|쉴게|쉴거|쉬자|쉬는날로|휴무(야|할게|로|해|예요|에요)|문(을)?닫아|안열어|영업안해")
HOLIDAY_CANCEL_RE = re.compile(r"(쉬는거|쉬는날|휴무)(는|를|은)?(취소|안쉬|없던걸로|빼)")
HOLIDAY_DATE_RE = re.compile(r"오늘|내일|모레|\d{1,2}일|[월화수목금토일]요일")
STAFF_SEND_RE = re.compile(r"^(응|어|그래|좋아|네|예)?(카톡|카카오톡)?(으로|로)?(보내|보내줘|보내요|공유해|공유해줘)")


@dataclass
class Intent:
    name: str
    owner_said: str
    jump_to: str | None = None
    by: str = "rule"  # rule | llm | heuristic
    edits: dict | None = None  # action.*: {"drop_compensation": bool, "no_card": bool, "drop_index": [몇 번째, ...]}
    slots: dict | None = None  # staff.* 를 LLM 이 가른 때: {"staff_name", "task_title", "task_repeat", "task_kind"}


# 받아쓰기에서 자모 한두 개가 바뀐 명령 낱말을 되돌린다 ("따음" → "다음", "릐뷰" → "리뷰", "첨부터" → "처음부터").
# 낱말과 길이가 같거나 한 글자 다른 구간 중 자모 거리가 가장 가까운 곳 하나만 바꾼다 (낱말이 이미 있으면 그대로).
# 자모 9개 이상인 낱말은 거리 2까지, 나머지는 1까지. 흔한 말이 명령으로 바뀌지 않게 NEAR_PROTECT 는 바꾸지 않는다.
NEAR_WORDS = ("처음부터", "브리핑", "넘어가", "자세히", "뭐라고", "돌아가", "다음", "넘겨", "계속", "다시", "리뷰", "읽어", "뒤로",
              "그만", "멈춰", "매출", "설정", "얘기", "들었")
NEAR_PROTECT = {"하면", "위로", "다리", "그냥", "계산", "이번", "다른", "다섯", "그럼", "그래", "매일", "예약", "하시"}
_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = ["ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅗㅏ", "ㅗㅐ", "ㅗㅣ", "ㅛ", "ㅜ", "ㅜㅓ", "ㅜㅔ", "ㅜㅣ", "ㅠ", "ㅡ",
         "ㅡㅣ", "ㅣ"]
_JONG = ["", "ㄱ", "ㄲ", "ㄱㅅ", "ㄴ", "ㄴㅈ", "ㄴㅎ", "ㄷ", "ㄹ", "ㄹㄱ", "ㄹㅁ", "ㄹㅂ", "ㄹㅅ", "ㄹㅌ", "ㄹㅍ", "ㄹㅎ", "ㅁ", "ㅂ",
         "ㅂㅅ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]


def jamo(text: str) -> str:
    """한글을 자모로 푼다. 겹받침·겹모음도 낱자로 ("읽" → ㅇㅣㄹㄱ). 한글이 아닌 글자는 그대로."""
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out.append(_CHO[code // 588] + _JUNG[(code % 588) // 28] + _JONG[code % 28])
        else:
            out.append(ch)
    return "".join(out)


def _distance(a: str, b: str, limit: int) -> int:
    """편집 거리. limit 를 넘으면 limit + 1."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        best = row[0]
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
            best = min(best, row[j])
        if best > limit:
            return limit + 1
    return row[-1]


def near_words(squashed: str) -> str:
    for word in NEAR_WORDS:
        if word in squashed:
            continue
        target = jamo(word)
        limit = 2 if len(target) >= 9 else 1
        best = None
        for size in (len(word) - 1, len(word), len(word) + 1):
            for start in range(0, len(squashed) - size + 1):
                piece = squashed[start:start + size]
                if size < 2 or piece in NEAR_PROTECT or not all("가" <= ch <= "힣" for ch in piece):
                    continue
                gap = _distance(jamo(piece), target, limit)
                if gap <= limit and (best is None or gap < best[0]):
                    best = (gap, start, size)
        if best:
            _, start, size = best
            squashed = squashed[:start] + word + squashed[start + size:]
    return squashed


def normalize(text: str) -> str:
    squashed = PUNCT_RE.sub("", text)
    for wrong, right in TYPOS.items():
        squashed = squashed.replace(wrong, right)
    return near_words(squashed)


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


def match(text: str, last_type: str | None, addressed: bool = False, instagram: bool = False) -> Intent | None:
    """addressed: "도나야"로 불러서 한 말. 가게 손님·직원에게 한 말(not_for_donna)로 넘기지 않는다.
    instagram: 브리핑에서 "인스타에 올릴까요?"를 묻고 대답을 기다리는 중 (미리보기를 넘기는 중 포함)."""
    n = normalize(text)
    said = tidy(text)
    if not n:
        return Intent("unknown", said)

    def found(name: str, jump_to: str | None = None) -> Intent:
        return Intent(name, said, jump_to)

    if STOP_RE.search(n) or HOME_RE.search(n):
        return found("stop")
    called = is_called(n, addressed)
    if not addressed and NOT_FOR_DONNA_RE.search(n) and not START_RE.search(n):  # "네 손님", "어서 오세요" 가 허락 대답으로 잡히지 않게 먼저 본다
        if called and asks_donna(n, text, called):
            return found("question")  # "도나야 오늘 손님 많을까"는 손님에게 한 말이 아니다
        return found("not_for_donna")
    if last_type in ("ask_action", "ask_tasks"):
        action = match_action(n, said, addressed)
        if action is not None:
            return action
    if instagram:
        if REVISE_RE.search(n):
            return found("instagram.revise")  # 인스타 글 고치기 (인사과 6단계)
        if INSTA_NEXT_RE.search(n):
            return found("instagram.next_photo")
        if INSTA_LATER_RE.search(n):
            return found("instagram.later")
        if INSTA_POST_RE.search(n):
            return found("instagram.post")
    if STORY_POST_RE.search(n):
        return found("instagram.story")
    if FEED_POST_RE.search(n):
        return found("instagram.feed")
    if last_type == "ask_permission":
        if NO_RE.search(n):
            return found("permission.no")
        if YES_RE.search(n) and "아니" not in n:
            return found("permission.yes")
    target = jump_target(n)
    if target == "negative" and CONTENT_RE.search(n):
        return found("detail.read", "negative")
    on_screen = last_type == "show_detail" and target == "reviews"  # 띄운 리뷰를 "손님 리뷰 읽어 줘"라고 부를 때
    if target and not on_screen and (REPEAT_RE.search(n) or READ_RE.search(n)):
        return None  # 대상(리뷰 등)을 말했으면 다시 말하기·지금 화면 읽기로 정하지 않는다 ("리뷰 뭐라고 했어?")
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
    if last_type == "ask_holiday":
        if NO_RE.search(n):
            return found("holiday.no")
        if YES_RE.search(n) or APPROVE_RE.fullmatch(n):
            return found("holiday.yes")
    if HOLIDAY_DATE_RE.search(n) and HOLIDAY_CANCEL_RE.search(n):  # "취소"가 알바생 일 취소로 가기 전에 본다
        return found("store.holiday_cancel")
    if HOLIDAY_DATE_RE.search(n) and HOLIDAY_RE.search(n) and not STAFF_ORDER_RE.search(n):
        return found("store.holiday")
    if NOTEBOOK_RE.search(n) and not STAFF_WORD_RE.search(n):
        return found("notebook.remove" if NOTEBOOK_REMOVE_RE.search(n) else "notebook.read")
    if UNDO_RE.search(n) and (UNDO_TARGET_RE.search(n) or ORDINAL_RE.search(n)) and not STAFF_WORD_RE.search(n):
        return found("report.undo")
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
    if target and (JUMP_TAIL_RE.search(n) or n in ("리뷰", "답글", "좋은리뷰", "아쉬운리뷰", "예약답글")):
        return found("briefing.jump", target)
    if START_RE.search(n):
        return found("briefing.start")
    if asks_donna(n, text, called):
        return found("question")  # 예측·의견 질문은 탭을 열지 않는다 (아래 NAVIGATE 보다 먼저)
    if not called and n.endswith("까"):
        return None  # 부르지 않은 "~(ㄹ)까" 질문은 묻는 말로도 탭으로도 정하지 않고 판정 에이전트에 맡긴다 ("날씨 추운데 문 닫을까?")
    if QUESTION_TOPIC_RE.search(n) and (QUESTION_TAIL_RE.search(n) or text.strip().endswith("?")):
        return found("question")  # "이번 주 비 와?"는 묻는 말이다. 탭을 열지 않는다
    if not called and WHERE_RE.search(n):
        return found("not_for_donna")
    for pattern, tab in NAVIGATE:
        if pattern.search(n):
            return found(f"navigate.{tab}")
    return None


def is_called(n: str, addressed: bool) -> bool:
    """도나를 부른 말: 앱이 호출어를 뗐거나(addressed) 글자 맨 앞에 "도나야"가 남은 말. n 은 normalize 한 글자."""
    return addressed or bool(WAKE_RE.match(n))


def unknown_to_silent(name: str, text: str, addressed: bool) -> str:
    """판정 에이전트가 unknown 을 내면 heuristic 으로 다시 가른다. 부른 말·도나에게 묻는 말("그거 뭐였지 그 저기", 물음표)은
    unknown(못 알아들음, 문서 13장 C5) 그대로, 아니면 not_for_donna (가만히)."""
    return heuristic(text, addressed).name if name == "unknown" else name


def match_staff(n: str) -> str | None:
    """알바생에 관한 말이면 그 뜻 이름. 시키는 말을 먼저 본다 ("예약 취소하라고 해"는 취소가 아니라 시키기)."""
    for pattern, name in ((STAFF_ORDER_RE, "staff.order"), (STAFF_REMOVE_RE, "staff.remove"), (STAFF_INVITE_RE, "staff.invite"),
                          (STAFF_SHARE_RE, "staff.share"), (STAFF_STATUS_RE, "staff.status"), (STAFF_CANCEL_RE, "staff.cancel"),
                          (STAFF_LIST_RE, "staff.list"), (STAFF_MANUAL_RE, "staff.manual")):
        if pattern.search(n):
            return name
    return None


def asks_donna(n: str, text: str, addressed: bool) -> bool:
    """"도나야"로 불러서 한 질문 꼴. 부르지 않은 질문은 직원끼리 한 말일 수 있어 판정 에이전트에 맡긴다
    ("리뷰 이벤트 서비스 드릴까?", "날씨 추운데 문 닫을까?")."""
    if not addressed or ACT_ASK_RE.search(n):
        return False
    return bool(QUESTION_FORM_RE.search(n)) or text.strip().endswith("?")


def edits_in(n: str) -> dict:
    return {"drop_compensation": bool(DROP_COMP_RE.search(n)), "no_card": bool(NO_CARD_RE.search(n)), "drop_index": drop_index(n)}


def drop_index(n: str) -> list[int]:
    """"두번째는빼" → [2]. 빼라는 말이 있을 때만 (몇 번째를 말한 순서대로, 겹치지 않게)."""
    if not DROP_WORD_RE.search(n):
        return []
    found = [ORDINAL_WORDS[m.group(1)] if m.group(1) else int(m.group(2)) for m in ORDINAL_RE.finditer(n)]
    return list(dict.fromkeys(found))


def match_action(n: str, said: str, addressed: bool) -> Intent | None:
    """ask_action 뒤의 대답. 못 가르면 None (다른 규칙으로 넘긴다)."""
    if REDO_RE.search(n):
        return Intent("action.redo", said)
    edits = edits_in(n)
    if edits["drop_compensation"] or edits["no_card"] or edits["drop_index"]:
        return Intent("action.approve" if POST_VERB_RE.search(n) else "action.edit", said, edits=edits)
    if REVISE_RE.search(n):
        return Intent("action.revise", said)
    if ACTION_CANCEL_RE.search(n):
        return Intent("action.cancel", said)
    if n in BARE_YES and not addressed:
        return Intent("action.unclear", said)
    if APPROVE_RE.fullmatch(n) and n:
        return Intent("action.approve", said, edits={"drop_compensation": False, "no_card": False, "drop_index": []})
    if REPEAT_RE.search(n):
        return Intent("action.repeat", said)
    return None


def heuristic(text: str, addressed: bool = False) -> Intent:
    """규칙도 LLM 도 못 가를 때. 도나에게 묻는 말 같으면 unknown(못 알아들음), 아니면 not_for_donna(가만히).
    "도나야"로 부른 말은 언제나 도나에게 한 말이다."""
    n = normalize(text)
    name = "unknown" if addressed or DONNA_CUE_RE.search(n) or text.strip().endswith("?") else "not_for_donna"
    return Intent(name, tidy(text), by="heuristic")
