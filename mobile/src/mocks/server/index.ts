// 앱 안에서 도는 목업 서버. Next.js 판의 /mock-api 길(app/mock-api/*)을 옮겼다.
// 서버와 같은 예시 응답(contracts/sample_responses, npm run sync-mocks로 복사)을 돌려주고,
// PATCH /settings는 서버 검사에 05, 06 시안의 장사 시간 검사(브레이크 타임, 새벽 마감, 쉬는 날, 요일별 시간)를 더해 이 기기에 저장한다.
// 서버에 아직 없는 길(네이버 불러오기, 매출 대시보드)도 여기서 흉내 낸다. 제안 API: docs/frontend_mock_and_api_needs.md
import { fromMin, guessDayparts, sinceOpen, summarizeWeekly, toMin, weeklyOf, type WeeklyHours } from "@/lib/hours";
import { storage } from "@/lib/storage";
import type { Review, StoreSettings, Weekday } from "@/types/contract";
import calendar from "../data/samples/calendar.json";
import plan from "../data/samples/plan.json";
import reviews from "../data/samples/reviews.json";
import { activePersona } from "../personas";
import sales from "../data/samples/sales.json";
import settings from "../data/samples/settings.json";
import today from "../data/samples/today.json";
import ordersData from "../data/orders.json";
import { salesPart } from "./sales";

export type MockResult = { status: number; body: unknown };

const SAMPLES: Record<string, unknown> = { today, plan, calendar, sales, reviews, settings };
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const ok = (body: unknown): MockResult => ({ status: 200, body });
const fail = (status: number, code: string, message: string): MockResult => ({ status, body: { error: { code, message } } });

// ---------- 06 목업 보탬: 리뷰 사진, 주문 시각 ----------
// 사진은 아직 실제 이미지가 없어서 "placeholder:무엇" 모양으로 둔다. 화면은 이것을 빈 사진 칸으로 그린다.
const REVIEW_PATCH: Record<string, Partial<Review>> = {
  rv_131: {
    text: "오늘은 국물이 너무 짰어요. 평소랑 맛이 달라요. 면도 좀 퍼져 있었고요. 자주 시켜 먹던 집이라 더 아쉬워요.",
    photos: ["placeholder:국물", "placeholder:면"],
  },
  // 06-24 "3번 모두 저녁 7시쯤이에요": 리뷰가 달린 주문의 주문 시각
  rv_105: { ordered_at: "2026-11-12T19:05:00+09:00" },
  rv_111: { ordered_at: "2026-11-15T19:10:00+09:00" },
  rv_118: { ordered_at: "2026-11-16T18:50:00+09:00" },
};

function reviewsBody() {
  const body = clone(reviews) as { reviews: Review[] };
  // 개발 화면에서 고른 매장이 있으면 그 가게 손님 글로 바꾼다 (mocks/personas.ts)
  const own = activePersona()?.reviews ?? {};
  body.reviews = body.reviews.map((r) => ({ photos: [], ordered_at: null, ...r, ...REVIEW_PATCH[r.review_id], ...(own[r.review_id] ? { text: own[r.review_id] } : {}) }));
  return body;
}

// ---------- 설정 ----------
type Editable = Partial<Pick<StoreSettings, "slots" | "dayparts" | "busy_dayparts" | "open_time" | "close_time" | "closed_weekdays" | "break_time" | "weekly_hours" | "name" | "category">>;
const SETTINGS_KEY = "dona.mock.settings.v1";
const EDITABLE = ["slots", "dayparts", "busy_dayparts", "open_time", "close_time", "closed_weekdays", "break_time", "weekly_hours", "name", "category"] as const;

function readOverride(): Editable {
  try {
    return JSON.parse(storage.getItem(SETTINGS_KEY) ?? "{}") as Editable;
  } catch {
    return {};
  }
}

function currentSettings(): StoreSettings {
  const base = clone(settings.settings) as StoreSettings;
  const s: StoreSettings = { break_time: null, ...base, ...readOverride() };
  return { ...s, weekly_hours: weeklyOf(s) };
}

export function resetMockSettings() {
  storage.removeItem(SETTINGS_KEY);
}

/** 개발 화면 매장 시나리오: 가게 이름과 업종을 그 매장으로 바꾼다. 장사 시간과 알림 시각은 그대로 둔다 (카드 시각이 같아야 한다). */
export function setMockStore(name: string, category: string) {
  storage.setItem(SETTINGS_KEY, JSON.stringify({ ...readOverride(), name, category }));
}

const HHMM = /^\d\d:\d\d$/;
const DAYS: Weekday[] = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];

function patchSettings(update: Editable): MockResult {
  const cur = currentSettings();
  let next: StoreSettings = { ...cur, ...update };
  if (update.weekly_hours) {
    // 06: 요일별 시간을 받으면 대표 장사 시간과 쉬는 날을 거기서 다시 뽑는다.
    const w = update.weekly_hours as WeeklyHours;
    for (const d of DAYS) {
      const h = w[d];
      if (h && (!HHMM.test(h.open) || !HHMM.test(h.close))) return fail(400, "INVALID_INPUT", "시각은 10:00처럼 적어 주세요.");
      if (h && h.open === h.close) return fail(400, "INVALID_INPUT", "여는 시간과 닫는 시간이 같아요.");
    }
    next = { ...next, ...summarizeWeekly(w) };
  } else if (update.open_time || update.close_time || update.closed_weekdays) {
    // 예전 방식(하나뿐인 장사 시간)으로 고치면 요일별 시간도 그에 맞춘다.
    next = { ...next, weekly_hours: undefined };
    next.weekly_hours = weeklyOf(next);
  }

  const times = [next.open_time, next.close_time, ...Object.values(next.slots), ...(next.break_time ? [next.break_time.start, next.break_time.end] : [])];
  if (times.some((t) => !HHMM.test(t))) return fail(400, "INVALID_INPUT", "시각은 10:00처럼 적어 주세요.");
  if (next.closed_weekdays.some((d) => !DAYS.includes(d))) return fail(400, "INVALID_INPUT", "쉬는 날은 MON ~ SUN으로 보내 주세요.");
  if (next.closed_weekdays.length === 7) return fail(400, "INVALID_INPUT", "쉬는 날이 아닌 날이 하루는 있어야 해요.");
  // 새벽에 닫는 가게도 순서를 맞추려고 '문 열기 1시간 전'부터 분으로 센다.
  const len = sinceOpen(next.close_time, next.open_time) || 1440;
  const from = fromMin(toMin(next.open_time) - 60);
  const pos = (t: string) => sinceOpen(t, from);
  if (next.break_time) {
    const a = sinceOpen(next.break_time.start, next.open_time);
    const b = sinceOpen(next.break_time.end, next.open_time);
    if (!(a < b && b <= len)) return fail(400, "INVALID_BREAK_TIME", "브레이크 타임은 장사 시간 안에서 시작보다 끝이 늦게 정해 주세요.");
  }
  const order = (["OPENING", "AFTERNOON", "CLOSING"] as const).map((sl) => pos(next.slots[sl]));
  if (!(order[0] < order[1] && order[1] < order[2])) return fail(400, "INVALID_INPUT", "출근 후, 한가할 때, 마감 전 순서로 정해 주세요.");
  for (const [slot, t] of Object.entries(next.slots)) {
    if (pos(t) > len + 60) return fail(400, "SLOT_OUTSIDE_OPEN_HOURS", `${slot} 알림 시각 ${t} 이 영업시간(${next.open_time}~${next.close_time}) 밖입니다.`);
    for (const d of next.busy_dayparts) {
      const busy = next.dayparts[d];
      const a = toMin(busy.start);
      const b = busy.end === "24:00" ? 1440 : toMin(busy.end);
      const x = toMin(t);
      const inside = a <= b ? a <= x && x < b : x >= a || x < b;
      if (inside) return fail(400, "SLOT_IN_BUSY_DAYPART", `${slot} 알림 시각 ${t} 이 바쁜 시간대(${d} ${busy.start}~${busy.end})에 걸립니다.`);
    }
  }
  const override = Object.fromEntries(EDITABLE.map((k) => [k, next[k]]));
  storage.setItem(SETTINGS_KEY, JSON.stringify(override));
  return ok({ is_example: true, settings: currentSettings() });
}

// ---------- 06-2n, 06-2c 네이버 플레이스에서 불러오기 (제안: GET /api/naver/place) ----------
function naverPlace(): MockResult {
  const weekly: WeeklyHours = {
    MON: null,
    TUE: { open: "11:00", close: "21:00" },
    WED: { open: "11:00", close: "21:00" },
    THU: { open: "11:00", close: "21:00" },
    FRI: { open: "11:00", close: "21:00" },
    SAT: { open: "11:00", close: "21:00" },
    SUN: { open: "11:00", close: "20:00" },
  };
  const break_time = { start: "15:00", end: "17:00" };
  const sum = summarizeWeekly(weekly);
  const menus = Object.values(ordersData.menu as Record<string, string>);
  return ok({
    is_example: true,
    place: {
      place_id: "naver_place_001",
      name: currentSettings().name,
      weekly_hours: weekly,
      break_time,
      ...guessDayparts(sum.open_time, sum.close_time, break_time),
      menus: menus.map((name, i) => ({ name, photo: i < 9 ? `placeholder:${name}` : null })),
      photo_count: 9,
      review_count: 207,
      rating: 4.6,
    },
  });
}

// ---------- 길 나누기 ----------
export function handleMock(method: "GET" | "PATCH", path: string, query: Record<string, string | undefined>, body?: unknown): MockResult {
  const [head, part] = path.split("/");
  if (method === "PATCH") {
    if (head !== "settings") return fail(405, "METHOD_NOT_ALLOWED", "고칠 수 없는 항목이에요.");
    return patchSettings((body ?? {}) as Editable);
  }
  if (head === "settings") return ok({ is_example: true, settings: currentSettings() });
  if (head === "reviews") return ok(reviewsBody());
  if (head === "naver" && part === "place") return naverPlace();
  if (head === "sales" && part) {
    const now = query.now ? new Date(query.now).getTime() : Date.now();
    if (Number.isNaN(now)) return fail(422, "INVALID_INPUT", "now는 2026-11-17T14:05:00+09:00처럼 보내 주세요.");
    const out = salesPart(part, now, (query.period ?? "week") as never);
    return out ? ok({ is_example: true, ...out }) : fail(404, "NOT_FOUND", "없는 매출 항목이에요.");
  }
  if (SAMPLES[head]) return ok(clone(SAMPLES[head]));
  return fail(404, "NOT_FOUND", "없는 예시예요.");
}
