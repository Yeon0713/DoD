// 매출 대시보드 목업 (Figma 05-70 ~ 05-75, 06-70 ~ 06-75). Next.js 판 app/mock-api/sales-board/[part]/route.ts를 옮겼다.
// 팀 목업 DB(server/db/mock/out의 orders.csv, order_items.csv, menu.csv → src/mocks/data/orders.json)를 now 시각까지만 모은다.
// 앞날 주문은 쓰지 않는다. 이번 주 남은 날은 지난 4주 같은 요일 평균에 이번 주 달력(행사, 경기, 계절) 비율을 곱해 예상한다.
// 실제 서버 API 제안: docs/frontend_mock_and_api_needs.md 3장 R. 응답 모양: src/types/sales.ts
import type { SalesChannels, SalesLive, SalesMenus, SalesMonths, SalesPeriod, SalesTimes, SalesWeeks } from "@/types/sales";
import calendarJson from "../data/samples/calendar.json";
import raw from "../data/orders.json";

type Order = { id: number; t: number; ymd: string; hour: number; wd: number; channel: string; customer: string; amount: number };
type Item = { orderId: number; menuId: number; qty: number; price: number };

const H9 = 9 * 3600e3;
let cache: { orders: Order[]; items: Item[]; menu: Map<number, string>; cal: { date: string; baseline: number; expected: number; tags: string[] }[] } | null = null;

function load() {
  if (cache) return cache;
  const data = raw as unknown as { orders: [number, number, number, string, number][]; items: [number, number, number, number][]; menu: Record<string, string> };
  const orders = data.orders.map(([id, t, ch, customer, amount]) => {
    const s = new Date(t + H9);
    return { id, t, ymd: s.toISOString().slice(0, 10), hour: s.getUTCHours(), wd: (s.getUTCDay() + 6) % 7, channel: ch ? "delivery" : "hall", customer, amount };
  });
  const items = data.items.map(([orderId, menuId, qty, price]) => ({ orderId, menuId, qty, price }));
  const menu = new Map(Object.entries(data.menu).map(([k, v]) => [Number(k), v]));
  const byDate = new Map<string, { date: string; baseline: number; expected: number; tags: string[] }>();
  for (const c of (calendarJson as { cells: { date: string; baseline_sales: number; expected_sales: number; reasons: { tag: string }[] }[] }).cells) {
    const d = byDate.get(c.date) ?? { date: c.date, baseline: 0, expected: 0, tags: [] };
    d.baseline += c.baseline_sales;
    d.expected += c.expected_sales;
    for (const r of c.reasons) if (!d.tags.includes(r.tag)) d.tags.push(r.tag);
    byDate.set(c.date, d);
  }
  cache = { orders, items, menu, cal: [...byDate.values()] };
  return cache;
}

const DAY = 86400e3;
const ymdOf = (t: number) => new Date(t + H9).toISOString().slice(0, 10);
const startOfDay = (ymd: string) => new Date(`${ymd}T00:00:00+09:00`).getTime();
const addDaysYmd = (ymd: string, n: number) => ymdOf(startOfDay(ymd) + n * DAY + 12 * 3600e3);
const sum = (xs: Order[]) => xs.reduce((a, o) => a + o.amount, 0);
const TAG_KO: Record<string, string> = { GAME: "경기", EVENT: "축제", SEASON: "추워져요", WEATHER: "날씨" };
const OPEN_HOURS = Array.from({ length: 12 }, (_, i) => 10 + i); // 10시 ~ 21시 (목업 가게 10:00 ~ 22:00)

function range(period: SalesPeriod, now: number): { from: number; to: number; prevFrom: number; prevTo: number } {
  const today = ymdOf(now);
  const wd = (new Date(now + H9).getUTCDay() + 6) % 7;
  let from = startOfDay(today);
  if (period === "week") from = startOfDay(addDaysYmd(today, -wd));
  if (period === "4w") from = startOfDay(addDaysYmd(today, -27));
  if (period === "month") from = startOfDay(`${today.slice(0, 7)}-01`);
  const span = now - from;
  const prevFrom = period === "month" ? startOfDay(`${ymdOf(from - DAY).slice(0, 7)}-01`) : from - (period === "4w" ? 28 * DAY : period === "week" ? 7 * DAY : DAY);
  return { from, to: now, prevFrom, prevTo: prevFrom + span };
}

function live(now: number): SalesLive {
  const { orders } = load();
  const today = ymdOf(now);
  const t0 = startOfDay(today);
  const sinceMidnight = now - t0;
  const todays = orders.filter((o) => o.t >= t0 && o.t <= now);
  const y0 = t0 - DAY;
  const yesterdaySame = sum(orders.filter((o) => o.t >= y0 && o.t <= y0 + sinceMidnight));
  const prevDays = [1, 2, 3, 4].map((w) => t0 - w * 7 * DAY);
  const usualDay = Math.round(prevDays.reduce((a, d) => a + sum(orders.filter((o) => o.t >= d && o.t < d + DAY)), 0) / 4);
  const usualSame = Math.round(prevDays.reduce((a, d) => a + sum(orders.filter((o) => o.t >= d && o.t <= d + sinceMidnight)), 0) / 4);
  const nowHour = new Date(now + H9).getUTCHours();
  const hourly = OPEN_HOURS.map((h) => {
    const usual = Math.round(prevDays.reduce((a, d) => a + sum(orders.filter((o) => o.t >= d && o.t < d + DAY && o.hour === h)), 0) / 4);
    const amount = sum(todays.filter((o) => o.hour === h));
    return { hour: h, amount, usual, state: (h < nowHour ? "past" : h === nowHour ? "now" : "future") as "past" | "now" | "future" };
  });
  const amount = sum(todays);
  return { now: new Date(now).toISOString(), date: today, amount, orders: todays.length, avg: todays.length ? Math.round(amount / todays.length) : 0, yesterdaySame, usualDay, usualSame, hourly };
}

function weeks(now: number): SalesWeeks {
  const { orders, cal } = load();
  const today = ymdOf(now);
  const wd = (new Date(now + H9).getUTCDay() + 6) % 7;
  const monday = addDaysYmd(today, -wd);
  const dayTotal = (ymd: string, until = Infinity) => sum(orders.filter((o) => o.ymd === ymd && o.t <= until));
  const days = Array.from({ length: 7 }, (_, i) => {
    const date = addDaysYmd(monday, i);
    const lastDate = addDaysYmd(date, -7);
    const last = dayTotal(lastDate);
    const usual = Math.round([1, 2, 3, 4].reduce((a, w) => a + dayTotal(addDaysYmd(date, -7 * w)), 0) / 4);
    const c = cal.find((x) => x.date === date);
    const reasons = (c?.tags ?? []).map((t) => TAG_KO[t] ?? t);
    if (date < today) return { date, amount: dayTotal(date), last, state: "actual" as const, reasons };
    if (date === today) return { date, amount: dayTotal(date, now), last, state: "now" as const, reasons, usual };
    const ratio = c && c.baseline ? c.expected / c.baseline : 1;
    return { date, amount: Math.round(usual * ratio), last, state: "forecast" as const, reasons };
  });
  const span = now - startOfDay(monday);
  const lastMonday = startOfDay(monday) - 7 * DAY;
  const lastSamePeriod = sum(orders.filter((o) => o.t >= lastMonday && o.t <= lastMonday + span));
  const toDate = days.filter((d) => d.state !== "forecast").reduce((a, d) => a + d.amount, 0);
  // 오늘 남은 시간은 평소 같은 요일 비율로 채운다
  const todayRow = days.find((d) => d.state === "now");
  const todayRest = todayRow ? Math.max(0, (todayRow.usual ?? 0) - todayRow.amount) : 0;
  const forecastTotal = days.reduce((a, d) => a + d.amount, 0) + todayRest;
  return { weekStart: monday, days, toDate, lastSamePeriod, lastTotal: days.reduce((a, d) => a + d.last, 0), forecastTotal };
}

function menus(now: number, period: SalesPeriod): SalesMenus {
  const { orders, items, menu } = load();
  const r = range(period, now);
  const ids = (a: number, b: number) => new Set(orders.filter((o) => o.t >= a && o.t <= b).map((o) => o.id));
  const cur = ids(r.from, r.to);
  const prev = ids(r.prevFrom, r.prevTo);
  const agg = new Map<string, { name: string; qty: number; amount: number; prevQty: number; prevAmount: number }>();
  for (const it of items) {
    const inCur = cur.has(it.orderId);
    const inPrev = prev.has(it.orderId);
    if (!inCur && !inPrev) continue;
    const name = menu.get(it.menuId) ?? `메뉴 ${it.menuId}`;
    const a = agg.get(name) ?? { name, qty: 0, amount: 0, prevQty: 0, prevAmount: 0 };
    if (inCur) {
      a.qty += it.qty;
      a.amount += it.qty * it.price;
    } else {
      a.prevQty += it.qty;
      a.prevAmount += it.qty * it.price;
    }
    agg.set(name, a);
  }
  return { period, from: ymdOf(r.from), to: ymdOf(r.to), items: [...agg.values()].filter((a) => a.qty > 0).sort((x, y) => y.amount - x.amount) };
}

const partOf = (h: number): "LUNCH" | "DINNER" | "NIGHT" => (h < 15 ? "LUNCH" : h < 20 ? "DINNER" : "NIGHT");

function times(now: number, period: SalesPeriod): SalesTimes {
  const { orders } = load();
  const r = range(period, now);
  const sel = orders.filter((o) => o.t >= r.from && o.t <= r.to);
  const dayparts = (
    [
      ["LUNCH", "점심", "15시 전"],
      ["DINNER", "저녁", "15시 ~ 20시"],
      ["NIGHT", "밤", "20시 뒤"],
    ] as const
  ).map(([key, label, rangeText]) => ({ key, label, range: rangeText, amount: sum(sel.filter((o) => partOf(o.hour) === key)) }));
  // 요일 × 시간대는 지난 4주 평균 (기간이 오늘이면 하루뿐이라)
  const g0 = startOfDay(ymdOf(now)) - 28 * DAY;
  const g = orders.filter((o) => o.t >= g0 && o.t < startOfDay(ymdOf(now)));
  const grid = [];
  for (let wd = 0; wd < 7; wd++) for (const dp of ["LUNCH", "DINNER", "NIGHT"] as const) grid.push({ weekday: wd, daypart: dp, avg: Math.round(sum(g.filter((o) => o.wd === wd && partOf(o.hour) === dp)) / 4) });
  return { period, from: ymdOf(r.from), to: ymdOf(r.to), dayparts, grid };
}

function channels(now: number, period: SalesPeriod): SalesChannels {
  const { orders } = load();
  const r = range(period, now);
  const sel = orders.filter((o) => o.t >= r.from && o.t <= r.to);
  // 배달앱 나눔은 목업에 없어서 주문 번호로 예시를 만든다 (배민 51%, 쿠팡이츠 29%, 요기요 12%, 네이버 8%)
  const platform = (o: Order) => (o.channel !== "delivery" ? "HALL" : o.id % 100 < 51 ? "BAEMIN" : o.id % 100 < 80 ? "COUPANG" : o.id % 100 < 92 ? "YOGIYO" : "NAVER");
  const label: Record<string, string> = { BAEMIN: "배달의민족", COUPANG: "쿠팡이츠", YOGIYO: "요기요", NAVER: "네이버 주문", HALL: "가게 손님" };
  const chans = ["BAEMIN", "COUPANG", "YOGIYO", "NAVER", "HALL"].map((k) => {
    const xs = sel.filter((o) => platform(o) === k);
    return { key: k, label: label[k], amount: sum(xs), orders: xs.length };
  });
  // 단골: 지금까지 60일 안에 3번 넘게 주문한 손님. 새 손님: 이 기간에 처음 주문한 손님
  const before = orders.filter((o) => o.t <= now && o.customer);
  const firstAt = new Map<string, number>();
  const count60 = new Map<string, number>();
  for (const o of before) {
    if (!firstAt.has(o.customer) || o.t < firstAt.get(o.customer)!) firstAt.set(o.customer, o.t);
    if (o.t >= now - 60 * DAY) count60.set(o.customer, (count60.get(o.customer) ?? 0) + 1);
  }
  const bucket = { regular: new Map<string, number>(), fresh: new Map<string, number>(), other: new Map<string, number>() };
  for (const o of sel.filter((x) => x.customer)) {
    const k = (count60.get(o.customer) ?? 0) >= 3 ? "regular" : firstAt.get(o.customer)! >= r.from ? "fresh" : "other";
    bucket[k].set(o.customer, (bucket[k].get(o.customer) ?? 0) + o.amount);
  }
  const pack = (m: Map<string, number>) => ({ people: m.size, amount: [...m.values()].reduce((a, b) => a + b, 0) });
  const unknown = sel.filter((o) => !o.customer);
  return {
    period,
    from: ymdOf(r.from),
    to: ymdOf(r.to),
    channels: chans,
    platformsSimulated: true,
    customers: { regular: pack(bucket.regular), fresh: pack(bucket.fresh), other: pack(bucket.other), unknownOrders: unknown.length, unknownAmount: sum(unknown) },
  };
}

function months(now: number): SalesMonths {
  const { orders } = load();
  const sel = orders.filter((o) => o.t <= now);
  const by = new Map<string, { amount: number; orders: number; days: Set<string> }>();
  for (const o of sel) {
    const m = o.ymd.slice(0, 7);
    const x = by.get(m) ?? { amount: 0, orders: 0, days: new Set() };
    x.amount += o.amount;
    x.orders += 1;
    x.days.add(o.ymd);
    by.set(m, x);
  }
  const last28 = sel.filter((o) => o.t > now - 28 * DAY);
  const avgDaily = Math.round(sum(last28) / 28);
  const thisMonth = ymdOf(now).slice(0, 7);
  const [y, m] = thisMonth.split("-").map(Number);
  const daysInMonth = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const out = [...by.entries()].sort().map(([month, x]) => {
    const first = [...x.days].sort()[0];
    const partial = month === thisMonth || first.slice(8) !== "01";
    const row: SalesMonths["months"][number] = { month, amount: x.amount, orders: x.orders, days: x.days.size, partial };
    if (month === thisMonth) row.forecast = x.amount + avgDaily * (daysInMonth - Number(ymdOf(now).slice(8)));
    return row;
  });
  return { months: out, avgDaily, avgOrder: last28.length ? Math.round(sum(last28) / last28.length) : 0 };
}

export function salesPart(part: string, now: number, period: SalesPeriod) {
  if (part === "live") return live(now);
  if (part === "weeks") return weeks(now);
  if (part === "menus") return menus(now, period);
  if (part === "times") return times(now, period);
  if (part === "channels") return channels(now, period);
  if (part === "months") return months(now);
  return null;
}
