"""개발자 대시보드 시연 탭: Figma 'DONNA 1차 완성본'의 UC01~UC16 을 가게별 시연 단계로 만든다.

단계 하나 = Figma 화면 하나. 단계마다
  at      서버 시계를 둘 시각 (시연 주간 안. demo_week_scan 이 찾은, 그 할 일이 홈에 막 도착한 때)
  open    앱 입구(/demo-jump)에 넘길 값: 열 화면, 맨 앞으로 꺼낼 카드, 네이버 연결 상태, 로그인 상태 등
  available, reason   그 가게 데이터에 그 장면이 없으면 False 와 까닭
을 담는다. 대시보드는 단계를 누르면 서버 시계를 at 으로 옮기고(POST demo_go), 휴대폰 틀에 앱을 연다.
"""

import datetime as dt
from collections.abc import Callable
from urllib.parse import quote

from app.core.seoul_time import at_time
from app.data_pipeline import read_store_db
from app.modules.dev_tools.demo_week_scan import DEMO_DAYS, DEMO_WEEK_START, SeenEntry, SeenSlot, WeekScan, scan_week
from app.planner.notification_time_helpers import KOREAN_WEEKDAYS

# Figma 유즈케이스 제목과 한 줄 설명 (Figma 09 페이지의 UC 제목)
UC_TITLES = {
    "UC01": ("네이버로 가입하기", "첫 화면에서 네이버로 시작해 가게를 확인하고, 알림 시간을 고르고, 알림을 켜요."),
    "UC02": ("휴대폰 번호로 가입하기", "번호와 숫자 6개로 가입하고, 가게를 찾아 네이버에서 불러오거나 장사 시간을 직접 적어요."),
    "UC03": ("앱을 열 때", "알림을 누르거나 로그인하면 도나가 살펴보고 홈을 열어요."),
    "UC04": ("리뷰에 사과 답글 달기", "부정 리뷰에 도나가 써 둔 사과 답글을 보고 올려요."),
    "UC05": ("같은 불만 점검하고 결과 보기", "같은 불만이 3번 오면 원인과 다른 가게 방법을 보고, 일주일 뒤 줄었는지 확인해요."),
    "UC06": ("단골 손님 답글 맡기기와 올리기", "단골에게 감사 인사를 맡기면 다시 주문할 때쯤 올라가요. 지금 규칙에서는 매달 단골 재주문 인사예요."),
    "UC07": ("좋은 리뷰에 한 번에 답글", "좋은 리뷰 답글을 묶어 맡기고, 토요일에 올려요."),
    "UC08": ("메뉴판 바꾸기 맡기기", "날씨, 경기, 축제에 맞춰 메뉴 순서를 정해 두면 그 시간에 바꿔요."),
    "UC09": ("메뉴판 바꿀 시간 알림", "맡겨 둔 시간이 되면 배달앱과 가게 메뉴판을 바꾸라고 알려요."),
    "UC10": ("네이버 연결하고 메뉴 순서 바꾸기", "네이버 플레이스를 연결하면 도나가 대신 바꾸고, 바꾼 뒤에 알리고, 되돌릴 수 있어요."),
    "UC11": ("홍보 포스터 만들기", "경기나 축제에 맞춰 메뉴 사진만 고르면 포스터를 만들어 둬요."),
    "UC12": ("홍보 포스터 올리기", "만들어 둔 포스터를 올릴 시간에 인스타그램으로 보내요."),
    "UC13": ("이번 주 미리 보기", "월요일 아침 이번 주 바쁜 때를 알려 주고, 이번 주 탭에서 요일별로 자세히 봐요."),
    "UC14": ("매출 보기", "매출 이상을 알려 주고, 매출 탭에서 오늘과 이번 주, 자세히 보기 다섯 가지를 봐요."),
    "UC15": ("다 봤어요", "카드를 다 보면 처리한 수를 보여 줘요. 미뤄 둔 것만 남았을 때도 있어요."),
    "UC16": ("설정과 계정", "장사 시간, 알림 시간, 바쁜 시간, 계정과 네이버 연결을 바꿔요."),
}

MOCK_ONLY = "불러오기 늦추기와 끊김 흉내는 앱 목업 모드(EXPO_PUBLIC_USE_MOCK=true)의 개발 화면(/dev)에서만 돼요"
NO_RESULT = "결과 알림(다음 주에 다시 온 손님, 불만이 줄었는지)은 아직 서버가 만들지 않아요"
EXAMPLE_PHONE = "01012345678"  # 예시 번호 (진짜 번호 아님)
EXAMPLE_MISSING_STORE = "홍길동 치킨"  # 예시: 검색에 안 나오는 가게 이름


def _day(t: dt.date) -> str:
    """요일 한 글자: 월, 화, ..."""
    return KOREAN_WEEKDAYS[t.weekday()][0]


def _when(t: dt.datetime) -> str:
    return f"{t.month}/{t.day}({_day(t)}) {t:%H:%M}"


def _step(uc: str, figma: str, title: str, to: str, at: dt.datetime | None, **open_values) -> dict:
    return {
        "uc": uc,
        "figma": figma,
        "title": title,
        "at": at.isoformat() if at else None,
        "at_label": _when(at) if at else None,
        "open": {"to": to, **open_values},
        "available": True,
        "reason": None,
    }


def _missing(uc: str, figma: str, title: str, reason: str) -> dict:
    return {"uc": uc, "figma": figma, "title": title, "at": None, "at_label": None, "open": None, "available": False, "reason": reason}


def _card_id(entry: SeenEntry) -> str:
    """앱이 카드에 붙이는 id (mobile/src/lib/queue.ts 와 같은 모양)."""
    if entry.notice:
        return f"{entry.notify_kind}:{entry.notice.notice_id}"
    plan = entry.plan
    if plan.task_type == "REVISIT_REPLY" and plan.revisit_class == "BASIC":
        return f"BASIC:{entry.notify_kind}:{plan.execute_at.isoformat()}"
    return f"{entry.notify_kind}:{plan.plan_id}"


def _enc(plan_id: str) -> str:
    return quote(plan_id, safe="")


class _Finder:
    """시연 주간 훑기 결과에서 조건에 맞는 할 일을 도착 순서대로 꺼낸다."""

    def __init__(self, scan: WeekScan):
        self.found = [(slot, entry) for slot in scan.slots for entry in slot.entries]

    def all(self, test: Callable[[SeenEntry], bool]) -> list[tuple[SeenSlot, SeenEntry]]:
        return [(slot, entry) for slot, entry in self.found if test(entry)]

    def first(self, test: Callable[[SeenEntry], bool]) -> tuple[SeenSlot, SeenEntry] | None:
        hits = self.all(test)
        return hits[0] if hits else None


def _is(task: str, kind: str, revisit_class: str | None = None) -> Callable[[SeenEntry], bool]:
    return lambda e: (
        e.plan is not None
        and e.plan.task_type == task
        and e.notify_kind == kind
        and (revisit_class is None or e.plan.revisit_class == revisit_class)
    )


def _notice(kind: str) -> Callable[[SeenEntry], bool]:
    return lambda e: e.notice is not None and e.notice.kind == kind


def build_steps(store_id: str) -> dict:
    store = read_store_db.read_store(store_id)
    scan = scan_week(store_id)
    find = _Finder(scan)
    week_end = DEMO_WEEK_START + dt.timedelta(days=DEMO_DAYS - 1)
    no_plan = scan.unavailable

    def gone(what: str) -> str:
        if no_plan:
            return f"계획을 못 만들었어요: {no_plan}"
        return f"시연 기간({DEMO_WEEK_START:%m/%d} ~ {week_end:%m/%d})에 {what}이 없어요"

    # 가게와 상관없는 화면을 열 때의 시각: 첫 불만 답글이 온 때, 없으면 시연 첫 주 화요일 오후
    quick = find.first(_is("REVISIT_REPLY", "APPROVAL_REQUEST", "QUICK"))
    base_at = quick[0].moment if quick else at_time(DEMO_WEEK_START + dt.timedelta(days=1), "14:05")
    if scan.slots and not quick:
        afternoon = [s for s in scan.slots if s.slot == "AFTERNOON"]
        base_at = (afternoon or scan.slots)[0].moment

    steps: list[dict] = []
    add = steps.append

    # UC01 네이버로 가입하기 (로그인 안 한 사장님)
    add(_step("UC01", "09-s1", "처음 · 왜 도나인가", "/start", base_at, signed="out"))
    # 서버에 네이버 키가 없으면 서버가 그리는 임시 네이버 로그인 화면으로 간다 (앱 데모 테스트 모드를 켜서 연다).
    # 진짜 키를 넣으면 nid.naver.com 으로 가는데, 그 화면은 휴대폰 틀 안에서 열리지 않을 수 있다.
    add(_step("UC01", "09-s2", "네이버로 시작하기 · 네이버 화면", "/start/naver-login", base_at, signed="out", naver_demo=True,
              note="서버 임시 네이버 로그인"))
    add(_step("UC01", "09-s3", "네이버로 가입했어요 · 우리 가게 확인", "/start/naver-store", base_at, signed="naver_new"))
    add(_step("UC01", "09-3", "처음 · 알림 받을 때 고르기", "/start/notify-time", base_at, signed="naver_new"))
    add(_step("UC01", "09-3b", "처음 · 알림 켜 주세요", "/start/notify-on", base_at, signed="naver_new"))
    add(_step("UC01", "09-4n", "처음 · 알림이 꺼진 채로 들어왔을 때", "/", base_at, notify_off=True))

    # UC02 휴대폰 번호로 가입하기
    add(_step("UC02", "09-s4", "휴대폰 번호로 시작하기 · 번호 적기", "/start/phone", base_at, signed="out"))
    add(_step("UC02", "09-s5", "휴대폰 번호로 시작하기 · 숫자 6개", f"/start/code?phone={EXAMPLE_PHONE}", base_at, signed="out", note="번호는 예시"))
    add(_step("UC02", "09-2", "처음 · 우리 가게 찾기", "/start/store", base_at, signed="phone_new"))
    add(_step("UC02", "09-2b", "처음 · 가게를 못 찾았을 때", f"/start/store?q={quote(EXAMPLE_MISSING_STORE)}", base_at, signed="phone_new", note="가게 이름은 예시"))
    add(_step("UC02", "09-2n", "처음 · 네이버 플레이스 연결 (불러오기)", "/start/naver", base_at, signed="phone_new"))
    add(_step("UC02", "09-2c", "처음 · 네이버에서 불러왔어요 (확인)", "/start/naver-confirm", base_at, signed="phone_new"))
    add(_step("UC02", "09-2i", "처음 · 장사 시간 직접 적기", "/start/hours", base_at, signed="phone_new"))

    # UC03 앱을 열 때
    add(_step("UC03", "09-23", "알림 · 잠금 화면에서 시작", "/lock", base_at))
    add(_step("UC03", "09-h0", "홈 · 처음 열 때 (도나가 살펴보는 중)", "/", base_at))
    add(_step("UC03", "09-s6", "다시 왔을 때 · 로그인", "/login", base_at, signed="returning"))
    for figma, title in [("09-8c", "홈 불러오기 · 3초가 넘을 때"), ("09-8d", "홈 불러오기 · 10초가 넘을 때"), ("09-9", "상태 · 인터넷이 끊겼을 때")]:
        add(_missing("UC03", figma, title, MOCK_ONLY))

    # UC04 리뷰에 사과 답글 달기 (불만 리뷰 빠른 응대)
    quick_all = find.all(_is("REVISIT_REPLY", "APPROVAL_REQUEST", "QUICK"))
    if not quick_all:
        add(_missing("UC04", "09-h1", "홈 · 불만 리뷰 사과 답글", gone("불만 리뷰")))
    for n, (slot, entry) in enumerate(quick_all[:2]):
        pid, card, at = entry.plan.plan_id, _card_id(entry), slot.moment
        reply = f"/reply/{_enc(pid)}"
        tag = f"{_when(at)} " if n else ""
        if n == 0:
            add(_step("UC04", "09-h1", "홈 · 불만 리뷰 사과 답글 카드", "/", at, card=card))
            add(_step("UC04", "09-4", "매일 · 오늘 할 일 하나", f"/task?id={_enc(card)}", at, card=card))
            add(_step("UC04", "09-5", "매일 · 답글 보고 올리기", reply, at, card=card))
            add(_step("UC04", "09-21", "매일 · 답글 고쳐 쓰기", f"{reply}/edit", at, card=card))
            add(_step("UC04", "09-22", "매일 · 나중에 다시 알림 (아래 시트)", f"/task?id={_enc(card)}&sheet=later", at, card=card))
            add(_step("UC04", "09-5s", "올린 뒤 · 답글을 올렸어요 띠", "/", at, done=card, toast="답글을 올렸어요|배달앱에서 볼 수 있어요"))
            add(_step("UC04", "09-5f", "올린 뒤 · 답글을 못 올렸을 때", f"{reply}?view=failed", at, card=card))
        else:
            add(_step("UC04", "09-h39", f"홈 · {tag}두 번째 불만 리뷰", "/", at, card=card))
            add(_step("UC04", "09-39r", f"{tag}사과 답글 보기", reply, at, card=card))

    # UC05 같은 불만 점검
    fix = find.first(_is("REVIEW_FIX", "APPROVAL_REQUEST"))
    if fix:
        slot, entry = fix
        add(_step("UC05", "09-h2", "홈 · 같은 불만 반복 카드", "/", slot.moment, card=_card_id(entry)))
        add(_step("UC05", "09-24", "매일 · 점검 목록", f"/check/{_enc(entry.plan.plan_id)}", slot.moment, card=_card_id(entry)))
    else:
        add(_missing("UC05", "09-h2", "홈 · 같은 불만 반복 카드", gone("같은 불만이 3번 온 일")))
    add(_missing("UC05", "09-h44", "홈 · 다음 주 불만이 줄었어요", NO_RESULT))

    # UC06 단골 (지금 규칙: 매달 단골 재주문 인사)
    nudge = find.first(_is("REORDER_NUDGE", "APPROVAL_REQUEST"))
    if nudge:
        slot, entry = nudge
        add(_step("UC06", "09-h35", "홈 · 매달 단골 재주문 인사", "/", slot.moment, card=_card_id(entry)))
        add(_step("UC06", "09-35r", "단골 인사 보기", f"/reply/{_enc(entry.plan.plan_id)}", slot.moment, card=_card_id(entry)))
    else:
        add(_missing("UC06", "09-h35", "홈 · 매달 단골 재주문 인사", gone("단골 재주문 인사")))

    # UC07 좋은 리뷰 묶음 답글
    basic = find.first(_is("REVISIT_REPLY", "APPROVAL_REQUEST", "BASIC"))
    if basic:
        slot, entry = basic
        batch = f"/reply/batch/{_enc(entry.plan.plan_id)}"
        add(_step("UC07", "09-h17", "홈 · 좋은 리뷰 답글 묶음", "/", slot.moment, card=_card_id(entry)))
        add(_step("UC07", "09-25", "매일 · 좋은 리뷰 답글 한 번에", batch, slot.moment, card=_card_id(entry)))
        add(_step("UC07", "09-25b", "좋은 리뷰 답글 하나씩", f"{batch}?one=0", slot.moment, card=_card_id(entry)))
    else:
        add(_missing("UC07", "09-h17", "홈 · 좋은 리뷰 답글 묶음", gone("좋은 리뷰")))
    basic_run = find.first(_is("REVISIT_REPLY", "EXECUTE_REMINDER", "BASIC"))
    if basic_run:
        slot, entry = basic_run
        add(_step("UC07", "09-h40", "홈 · 좋은 리뷰 답글 올릴 시간", "/", slot.moment, card=_card_id(entry)))
    add(_missing("UC07", "09-h43", "홈 · 다음 주 답글 효과", NO_RESULT))

    # UC08 메뉴판 바꾸기 맡기기, UC09 바꿀 시간 알림, UC10 네이버 연결
    menu_asks = find.all(_is("MENU_ORDER", "APPROVAL_REQUEST"))
    menu_runs = find.all(_is("MENU_ORDER", "EXECUTE_REMINDER"))
    if menu_asks:
        slot, entry = menu_asks[0]
        card, menu = _card_id(entry), f"/menu-order/{_enc(entry.plan.plan_id)}"
        add(_step("UC08", "09-h12", f"홈 · 메뉴판 카드 (직접 바꾸기) · {entry.plan.reason_line}", "/", slot.moment, card=card, naver="declined"))
        add(_step("UC08", "09-12n", "메뉴판 카드 (네이버 미리 보기, 연결된 뒤)", "/", slot.moment, card=card, naver="connected"))
        add(_step("UC08", "09-55s", "네이버 · 내일 바꿔 둘게요 (전날 승인)", f"{menu}?apply=1", slot.moment, card=card, naver="connected"))
        for slot, entry in menu_asks[1:3]:
            add(_step("UC08", "09-h28", f"홈 · {_when(slot.moment)} 다른 메뉴판 · {entry.plan.reason_line}", "/", slot.moment, card=_card_id(entry), naver="declined"))

        slot, entry = menu_asks[0]
        add(_step("UC10", "09-h50", "홈 · 메뉴판 카드 (네이버 연결 전)", "/", slot.moment, card=card, naver="off"))
        add(_step("UC10", "09-51", "네이버 · 연결 안내", f"/naver/connect?plan={_enc(entry.plan.plan_id)}", slot.moment, card=card, naver="off"))
        add(_step("UC10", "09-52", "네이버 · 연결됐어요", f"/naver/connect?plan={_enc(entry.plan.plan_id)}&view=done", slot.moment, card=card, naver="connected"))
        add(_step("UC10", "09-53", "네이버 · 바꿀 순서 미리 보기", menu, slot.moment, card=card, naver="connected"))
        add(_step("UC10", "09-54", "네이버 · 바꾸는 중", f"{menu}?view=applying", slot.moment, card=card, naver="connected"))
        add(_step("UC10", "09-55", "네이버 · 바꿨어요", f"{menu}?view=done", slot.moment, card=card, naver="connected"))
        add(_step("UC10", "09-57", "네이버 · 원래대로 되돌렸어요", f"{menu}?view=reverted", slot.moment, card=card, naver="connected"))
    else:
        add(_missing("UC08", "09-h12", "홈 · 메뉴판 카드", gone("메뉴판 바꾸기")))
        add(_missing("UC10", "09-h50", "홈 · 메뉴판 카드 (네이버 연결 전)", gone("메뉴판 바꾸기")))
    if menu_runs:
        for slot, entry in menu_runs[:3]:
            add(_step("UC09", "09-h14", f"홈 · {_when(slot.moment)} 메뉴판 바꿀 시간", "/", slot.moment, card=_card_id(entry), naver="declined"))
        slot, entry = menu_runs[0]
        add(_step("UC10", "09-h56", "홈 · 메뉴판 바꿔 뒀어요 (알아서 바꾸기)", "/", slot.moment, card=_card_id(entry), naver="auto"))
    else:
        add(_missing("UC09", "09-h14", "홈 · 메뉴판 바꿀 시간", gone("메뉴판 실행 알림")))
    add(_step("UC10", "09-58", "설정 · 네이버 플레이스", "/settings/naver", base_at, naver="connected"))

    # UC11 포스터 만들기, UC12 포스터 올리기
    poster_ask = find.first(_is("POSTER", "APPROVAL_REQUEST"))
    if poster_ask:
        slot, entry = poster_ask
        poster = f"/poster/{_enc(entry.plan.plan_id)}"
        add(_step("UC11", "09-h13", f"홈 · 포스터 만들기 · {entry.plan.reason_line}", "/", slot.moment, card=_card_id(entry)))
        add(_step("UC11", "09-61", "인스타 · 메뉴 사진 고르기", poster, slot.moment, card=_card_id(entry)))
        add(_step("UC11", "09-62", "인스타 · 포스터 만드는 중", f"{poster}?step=making", slot.moment, card=_card_id(entry)))
        add(_step("UC11", "09-63", "인스타 · 포스터 미리 보기", f"{poster}?step=preview", slot.moment, card=_card_id(entry)))
        add(_step("UC11", "09-64", "인스타 · 포스터 글자 고치기", f"{poster}?step=edit", slot.moment, card=_card_id(entry)))
    else:
        add(_missing("UC11", "09-h13", "홈 · 포스터 만들기", gone("포스터")))
    poster_run = find.first(_is("POSTER", "EXECUTE_REMINDER"))
    if poster_run:
        slot, entry = poster_run
        poster = f"/poster/{_enc(entry.plan.plan_id)}"
        add(_step("UC12", "09-h31", "홈 · 포스터 올리기", "/", slot.moment, card=_card_id(entry)))
        add(_step("UC12", "09-65", "인스타 · 올릴 곳 고르기", f"{poster}?step=share", slot.moment, card=_card_id(entry)))
        add(_step("UC12", "09-66", "인스타 · 인스타그램으로 보냈어요", f"{poster}?step=sent", slot.moment, card=_card_id(entry)))
    else:
        add(_missing("UC12", "09-h31", "홈 · 포스터 올리기", gone("포스터 올리기 알림")))

    # UC13 이번 주 미리 보기
    preview = find.first(_notice("WEEKLY_PREVIEW"))
    week_at = preview[0].moment if preview else base_at
    if preview:
        add(_step("UC13", "09-h16", "홈 · 월요일 이번 주 미리 보기", "/", week_at, card=_card_id(preview[1])))
    else:
        add(_missing("UC13", "09-h16", "홈 · 이번 주 미리 보기", gone("주간 예고")))
    add(_step("UC13", "09-7", "이번 주 탭", "/week", week_at))
    monday = week_at.date() - dt.timedelta(days=week_at.weekday())
    for offset in range(7):
        day = monday + dt.timedelta(days=offset)
        add(_step("UC13", f"09-7-{_day(day)}", f"이번 주 · {_day(day)}요일을 눌렀을 때", f"/week?day={day.isoformat()}", week_at))
    add(_missing("UC13", "09-7L", "이번 주 · 불러오는 중", MOCK_ONLY))

    # UC14 매출
    anomaly = find.first(_notice("SALES_ANOMALY"))
    if anomaly:
        add(_step("UC14", "09-h15", "홈 · 매출 이상 알림", "/", anomaly[0].moment, card=_card_id(anomaly[1])))
    else:
        add(_missing("UC14", "09-h15", "홈 · 매출 이상 알림", gone("매출 이상")))
    for figma, title, to in [
        ("09-70", "매출 · 오늘 실시간과 이번 주", "/sales"),
        ("09-71", "매출 · 이번 주와 지난주 자세히", "/sales/week"),
        ("09-72", "매출 · 메뉴별", "/sales/menu"),
        ("09-73", "매출 · 시간대와 요일", "/sales/time"),
        ("09-74", "매출 · 배달앱과 단골", "/sales/channel"),
        ("09-75", "매출 · 달별 흐름", "/sales/month"),
    ]:
        add(_step("UC14", figma, title, to, base_at))

    # UC15 다 봤어요: 할 일이 온 때에 모두 끝낸 것으로 / 하나만 미뤄 둔 것으로 / 할 일이 없는 날
    busiest = max(scan.slots, key=lambda s: len(s.entries), default=None)
    if busiest:
        add(_step("UC15", "09-h6", f"홈 · 다 봤을 때 ({_when(busiest.moment)})", "/", busiest.moment, done="all"))
        add(_step("UC15", "09-h7", "홈 · 미뤄 둔 것만 남았을 때", "/", busiest.moment, done="snooze"))
    else:
        add(_missing("UC15", "09-h6", "홈 · 다 봤을 때", gone("할 일")))
    busy_days = {s.slot_at.date() for s in scan.slots}
    quiet = next((DEMO_WEEK_START + dt.timedelta(days=i) for i in range(DEMO_DAYS) if DEMO_WEEK_START + dt.timedelta(days=i) not in busy_days), None)
    if quiet and not no_plan:
        add(_step("UC15", "09-6", f"매일 · 할 일 없는 날 ({_when(at_time(quiet, '14:05'))})", "/", at_time(quiet, "14:05")))
    else:
        add(_missing("UC15", "09-6", "매일 · 할 일 없는 날", gone("할 일 없는 날")))

    # UC16 설정과 계정
    add(_step("UC16", "09-19", "설정 · 모아 보기", "/settings", base_at))
    add(_step("UC16", "09-19h", "설정 · 장사 시간", "/settings/hours", base_at))
    add(_step("UC16", "09-19b", "설정 · 알림 받는 시간 바꾸기", "/settings/notify-time", base_at))
    add(_step("UC16", "09-20", "설정 · 바쁜 장사 시간", "/settings/busy", base_at))
    add(_step("UC16", "09-s7", "설정 · 계정 (네이버 연결 전)", "/settings/account", base_at, naver="off", signed="phone"))
    add(_step("UC16", "09-s8", "설정 · 계정 (네이버 연결됨)", "/settings/account", base_at, naver="connected"))

    order = list(UC_TITLES)
    steps.sort(key=lambda s: order.index(s["uc"]))  # 같은 UC 안에서는 넣은 순서 그대로
    return {
        "store": {"store_id": store_id, "name": store["name"]},
        "demo_week": {"first": DEMO_WEEK_START.isoformat(), "last": week_end.isoformat()},
        "unavailable": no_plan,
        "ucs": [{"uc": uc, "title": t, "summary": s} for uc, (t, s) in UC_TITLES.items()],
        "steps": steps,
    }
