"""일정 탭(GET /v1/week), 매출 탭(GET /v1/sales), 도나 알림(GET /v1/notices). 문서 16-2.

일정 탭은 "바쁠 것 같다"는 추측을 보여 주지 않는다. 날짜와 시각이 있는 사실(잡힌 일)과 그날 한 일만 보여 준다.
매출은 포스 매출(fixtures 의 sales)에서 나온다. 알림은 voice/notices.py.
"""

import datetime as dt
import re

from fastapi import APIRouter

from voice import activity, clock, config, hours, hr, notices, repo, speech
from voice.api.errors import store_not_found
from voice.api.home import date_label, time_of
from voice.clock import parse
from voice.context import load
from voice.jobs import briefing

router = APIRouter()

PLAN_LABEL = {"event": "행사", "game": "경기", "group_reservation": "단체 예약", "weather": "비"}


def _josa(word: str, with_final: str, without_final: str) -> str:
    return with_final if speech.has_batchim(word) else without_final


def _plans(view, day: dt.date) -> list[dict]:
    """그날 잡힌 일: 행사, 경기, 단체 예약, 비."""
    found = []
    for kind in ("event", "game"):
        for item in view.data.get(kind, []):
            if parse(item["starts_at"]).date() == day:
                found.append((kind, item["name"], item["name"][:5], parse(item["starts_at"])))
    for r in view.data.get("reservation", []):
        start = parse(r["starts_at"])
        if start.date() == day and r["party_size"] >= config.GROUP_MIN_PEOPLE:
            found.append(("group_reservation", f"단체 손님 {speech.count(r['party_size'], '분')}", f"단체 {r['party_size']}명", start))
    rain = briefing.rain_today(view, day)
    if rain:
        start = dt.datetime(day.year, day.month, day.day, rain["rain_from"], tzinfo=clock.now().tzinfo) if rain.get("rain_from") else None
        found.append(("weather", briefing.rain_text(rain, day), "비", start))
    plans = []
    for n, (kind, text, short, start) in enumerate(sorted(found, key=lambda p: p[3].isoformat() if p[3] else "")):
        plans.append({"id": f"pl_{day.isoformat()}_{n}", "kind": kind, "label": PLAN_LABEL[kind], "text": text, "short": short,
                      "starts_at": clock.iso(start) if start else None, "time_label": speech.clock_label(start) if start else None})
    return plans


def _day_title(plans: list[dict], past: bool) -> str:
    """그날의 큰 한마디. 추측이 아니라 잡힌 일을 그대로 말한다. 휴대폰에서 한 줄."""
    labels = []
    for p in plans:
        if p["kind"] != "weather" and p["label"] not in labels:
            labels.append(p["label"])
    if len(labels) > 1:
        return "일이 여러 가지였어요" if past else "일이 여러 가지 있어요"
    if labels:
        return f"{labels[0]}{_josa(labels[0], '이', '가')} {'있었어요' if past else '있어요'}"
    if plans:
        return "비가 왔어요" if past else "비가 와요"
    return "잡힌 일이 없었어요" if past else "잡힌 일이 없어요"


def _scheduled_items(view, now: dt.datetime) -> list[dict]:
    from voice.jobs import schedule

    scheduled = [r for r in view.reviews() if r.get("reply_status") == "scheduled"]
    rows = schedule.rows(scheduled, view.menus, now, view.store.get("rain_menu"))
    return [{k: row[k] for k in ("id", "day_label", "time_label", "post_at", "reason", "text")} for row in rows]


def _remaining_today(view, now: dt.datetime) -> list[dict]:
    """오늘 아직 남은 것: 못 들은 브리핑, 답을 기다리는 아쉬운 리뷰, 이 시각 뒤의 일정."""
    store_id = view.store_id
    out = []
    if not any(a["text"] == "오늘 일정 브리핑을 들었어요" for a in activity.on(store_id, now.date())):
        out.append({"id": "r_brief", "kind": "briefing", "text": "오늘 일정 브리핑 듣기", "time_label": None})
    neg = [r for r in briefing.awaiting(view) if r.get("sentiment") == "negative"]
    if neg and hr.asks(store_id, "negative_reply") is not None:
        out.append({"id": "r_neg", "kind": "reviews", "text": f"아쉬운 리뷰 {len(neg)}개에 답글 달기", "time_label": None})
    for plan in _plans(view, now.date()):
        if plan["kind"] != "weather" and plan["starts_at"] and parse(plan["starts_at"]) > now:
            out.append({"id": f"r_{plan['id']}", "kind": plan["kind"], "text": plan["text"], "time_label": plan["time_label"]})
    return out


def _done(store_id: str, day: dt.date) -> list[dict]:
    return [{"id": a["id"], "actor": a["actor"], "text": a["text"], "time_label": speech.clock_label(parse(a["at"]))}
            for a in activity.on(store_id, day)]


def _past(store_id: str, today: dt.date) -> list[dict]:
    """지난 일 묶음: 어제 한 일, 지난주에 한 일을 센 것."""
    yesterday = today - dt.timedelta(days=1)
    groups = []
    items = _done(store_id, yesterday)
    if items:
        groups.append({"label": "어제", "date_label": date_label(yesterday), "items": items})
    monday = today - dt.timedelta(days=today.weekday())
    start, end = monday - dt.timedelta(days=7), monday - dt.timedelta(days=1)
    week = activity.between(store_id, start, end)
    posted = sum(int(s) for a in week for s in re.findall(r"답글 (\d+)개를 올렸", a["text"]))
    heard = sum(1 for a in week if a["text"] == "오늘 일정 브리핑을 들었어요")
    summary = []
    if posted:
        summary.append({"id": "w_posted", "actor": "donna", "text": f"답글 {posted}개를 올렸어요"})
    if heard:
        summary.append({"id": "w_heard", "actor": "owner", "text": f"브리핑을 {speech.count(heard, '번')} 들었어요"})
    if summary:
        groups.append({"label": "지난주", "date_label": f"{start.month}월 {start.day}일 ~ {end.day}일", "items": summary})
    return groups


def week(store_id: str) -> dict:
    view = load(store_id)
    now = clock.now()
    today = now.date()
    monday = today - dt.timedelta(days=today.weekday())
    first = today.replace(day=1)
    grid_start = first - dt.timedelta(days=first.weekday())
    weather = {w["date"]: w for w in view.data.get("weather", [])}
    upcoming = _scheduled_items(view, now)
    by_day: dict[str, list[dict]] = {}
    for item in upcoming:
        by_day.setdefault(item["post_at"][:10], []).append(item)

    days = []
    for n in range(42):  # 달력 6주
        day = grid_start + dt.timedelta(days=n)
        past = day < today
        plans = _plans(view, day)
        w = weather.get(day.isoformat())
        scheduled = by_day.get(day.isoformat(), [])
        days.append({
            "date": day.isoformat(), "weekday_label": speech.weekday(day), "day": day.day, "date_label": date_label(day),
            "in_month": day.month == today.month, "is_today": day == today, "is_past": past,
            "marks": (["plan"] if plans else []) + (["reply"] if scheduled else []),
            "title": _day_title(plans, past),
            "weather": {"label": w.get("label") or ("비" if w.get("rain_chance", 0) >= 0.6 else "맑음"),
                        "temp_min": w["temp_min"], "temp_max": w["temp_max"]} if w else None,
            "plans": plans,
            "tip": None,
            "scheduled": scheduled,
            "done": _done(store_id, day) if day <= today else [],
            "remaining": _remaining_today(view, now) if day == today else [],
        })
    week_dates = [(monday + dt.timedelta(days=k)).isoformat() for k in range(7)]
    planned = [d["weekday_label"] for d in days if d["date"] in week_dates and d["plans"] and not d["is_past"]]
    return {
        "week_label": f"{monday.month}월 {monday.day}일 ~ {(monday + dt.timedelta(days=6)).day}일",
        "month_label": f"{today.month}월",
        "today": today.isoformat(),
        "week_dates": week_dates,
        "days": days,
        "say": f"이번 주는 {', '.join(planned)}요일에 일이 잡혀 있어요." if planned else "이번 주는 잡힌 일이 없어요.",
        "scheduled": upcoming,
        "past": _past(store_id, today),
    }


def _won(n: int) -> str:
    """1,284,000 → 128만 원. 사장님이 한눈에 읽는 단위."""
    return f"{round(n / 10000):,}만 원"


def _diff(diff: int) -> dict:
    """견주는 한 줄의 재료. 화면은 화살표 + 숫자(갈색 굵게) + 많아요/적어요 (Figma G-04)."""
    return {"direction": "up" if diff >= 0 else "down", "diff_label": _won(abs(diff)),
            "diff_text": f"{_won(abs(diff))} {'많아요' if diff >= 0 else '적어요'}"}


def _month(daily: dict, today: dt.date, today_amount: int, today_share: float) -> dict:
    """이번 달 지금까지 ↔ 지난달 같은 날 이맘때. 지난달 오늘 몫은 지난주 같은 요일이 이맘때까지 판 비율로 어림한다."""
    first = today.replace(day=1)
    last_first = (first - dt.timedelta(days=1)).replace(day=1)
    this_total = sum(v for k, v in daily.items() if first.isoformat() <= k < today.isoformat()) + today_amount
    last_days = [last_first + dt.timedelta(days=i) for i in range(today.day - 1)]
    last_total = sum(daily.get(d.isoformat(), 0) for d in last_days if d.month == last_first.month)
    try:
        same_day = last_first.replace(day=today.day)
        last_total += round(daily.get(same_day.isoformat(), 0) * today_share)
    except ValueError:  # 지난달에 그 날짜가 없다 (31일 등)
        pass
    return {"label": "이번 달 지금까지", "amount": this_total, "amount_label": _won(this_total),
            "compare_label": "지난달 이맘때보다", "has_last": last_total > 0, **_diff(this_total - last_total)}


def _came_back(item: dict) -> str:
    at = parse(item["came_back_at"])
    how = "배달로 다시 주문했어요" if item.get("channel") == "delivery" else "가게에 다시 오셨어요"
    return f"{at.month}월 {at.day}일 {how}"


def _revisits(store_id: str, now: dt.datetime) -> dict:
    """도나 답글을 받고 다시 온 손님 (Figma G-04 ③). 답글이 올라간 뒤 처음 다시 온 때를 센다.
    '답글 덕분에'라고 하지 않는다. 다시 온 사실만 적는다. 목업 단계라 fixtures 의 revisits 가 곧 포스·리뷰를 이어 본 결과다."""
    monday = dt.datetime.combine(now.date() - dt.timedelta(days=now.weekday()), dt.time(0), tzinfo=now.tzinfo)
    items = sorted((r for r in repo.all_of("revisit", store_id) if parse(r["came_back_at"]) <= now), key=lambda r: r["came_back_at"])
    this_week = [r for r in items if parse(r["came_back_at"]) >= monday]
    last_week = [r for r in items if monday - dt.timedelta(days=7) <= parse(r["came_back_at"]) < monday]
    latest = None
    if items:
        r = items[-1]
        written = parse(r["review"]["written_at"])
        latest = {"came_back_label": _came_back(r), "date_label": f"{parse(r['came_back_at']).month}월 {parse(r['came_back_at']).day}일",
                  "review": {"rating": r["review"]["rating"], "text": r["review"]["text"], "date_label": f"{written.month}월 {written.day}일 리뷰"},
                  "reply": {"text": r["reply"]["text"], "by": r["reply"].get("by", "donna")}}
    return {"label": "도나 답글을 받고 이번 주에 다시 온 손님", "count": len(this_week), "count_label": f"{len(this_week)}명",
            "last_week_label": f"지난주에는 {len(last_week)}명", "latest": latest}


def sales(store_id: str) -> dict:
    store = repo.store(store_id)
    data = repo.get("sales", store_id) or {"daily": {}}
    now = clock.now()
    today = now.date()
    hours_today = hours.on(store, today)
    opened = hours_today is not None and now.time().replace(tzinfo=None) >= time_of(hours_today["open"])
    daily = data.get("daily", {})

    def amount(day: dt.date) -> int:
        if day == today:
            return data.get("today_so_far", 0) if opened else 0
        return daily.get(day.isoformat(), 0) if day < today else 0

    monday = today - dt.timedelta(days=today.weekday())
    week_days = [monday + dt.timedelta(days=i) for i in range(7)]
    this_week = [amount(d) for d in week_days]
    last_week = [daily.get((d - dt.timedelta(days=7)).isoformat(), 0) for d in week_days]
    same = data.get("last_week_same_time", 0) if opened else 0
    last_same_day = daily.get((today - dt.timedelta(days=7)).isoformat(), 0)
    share = (same / last_same_day) if opened and last_same_day else 0.0
    if opened:
        diff = this_week[today.weekday()] - same
        primary = {"label": "오늘 지금까지", "amount": this_week[today.weekday()], "amount_label": _won(this_week[today.weekday()]),
                   "compare_label": f"지난주 {speech.weekday(today)}요일 이맘때", "compare_amount": same, "compare_amount_label": _won(same),
                   "compare_text": f"지난주 이맘때보다 {_won(abs(diff))} {'많아요' if diff >= 0 else '적어요'}", **_diff(diff)}
    else:
        yesterday = today - dt.timedelta(days=1)
        y_amount = daily.get(yesterday.isoformat(), 0)
        before = daily.get((yesterday - dt.timedelta(days=7)).isoformat(), 0)
        diff = y_amount - before
        primary = {"label": "어제", "amount": y_amount, "amount_label": _won(y_amount),
                   "compare_label": f"지난주 {speech.weekday(yesterday)}요일", "compare_amount": before, "compare_amount_label": _won(before),
                   "compare_text": f"지난주 {speech.weekday(yesterday)}요일보다 {_won(abs(diff))} {'많아요' if diff >= 0 else '적어요'}", **_diff(diff)}
    primary["short_text"] = f"지난주보다 {primary['diff_text']}"
    bars = [{"weekday_label": speech.weekday(d), "date": d.isoformat(), "amount": this_week[i],
             "amount_label": _won(this_week[i]) if this_week[i] else None, "last_week_amount": last_week[i],
             "last_week_label": _won(last_week[i]), "is_today": d == today, "is_future": d > today} for i, d in enumerate(week_days)]
    this_total = sum(this_week)
    last_total = sum(last_week[: today.weekday()]) + same
    wdiff = this_total - last_total
    menus_month = data.get("top_menus_month") or []
    return {
        "headline": f"{primary['label']} {primary['amount_label']} 팔았어요" if primary["amount"] else "아직 매출이 없어요",
        "say": f"{primary['label']} {primary['amount_label']} 팔았어요. {primary['compare_text']}." if primary["amount"] else "아직 매출이 없어요.",
        "primary": primary,
        "week": {"bars": bars, "max_amount": max(this_week + last_week + [1]), "total_label": _won(this_total),
                 "label": "이번 주 지금까지", "amount": this_total, "compare_label": "지난주 이맘때보다",
                 "compare_text": f"지난주 이맘때보다 {_won(abs(wdiff))} {'많아요' if wdiff >= 0 else '적어요'}", **_diff(wdiff)},
        "month": _month(daily, today, this_week[today.weekday()], share),
        "revisits": _revisits(store_id, now),
        "top_menus": {"label": "어제 잘 팔린 메뉴", "unit": "개", "items": data.get("top_menus_yesterday", [])},
        "top_menus_month": {"label": "이번 달 가장 많이 나간 메뉴", "unit": "그릇", "items": menus_month} if menus_month else None,
    }


@router.get("/week")
def get_week(store_id: str):
    if repo.store(store_id) is None:
        return store_not_found()
    return week(store_id)


@router.get("/sales")
def get_sales(store_id: str):
    if repo.store(store_id) is None:
        return store_not_found()
    return sales(store_id)


@router.get("/notices")
def get_notices(store_id: str):
    """도나 알림 (voice/notices.py): 영업 중 아쉬운 리뷰, 알바생 확인, 대답 없음 처리, 알바생 가입. 한 번 읽으면 다시 주지 않는다."""
    if repo.store(store_id) is None:
        return store_not_found()
    return {"notices": notices.unseen(store_id)}
