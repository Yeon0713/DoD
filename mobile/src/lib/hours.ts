// 장사 시간과 알림 시간 (Figma 05-2h, 05-2i, 05-3, 05-3t, 05-3e, 05-19h, 05-3 규칙 보드).
// 장사 시간을 받으면 하루 3번 알림을 이 규칙으로 골라 드리고, 사장님이 하나씩 바꿀 수 있다.
import type { Daypart, Slot, StoreSettings, Weekday } from "@/types/contract";

export type Hours = Pick<StoreSettings, "open_time" | "close_time" | "dayparts" | "busy_dayparts" | "closed_weekdays" | "break_time">;
export type PatternKey = "LUNCH_DINNER" | "EVENING_NIGHT" | "ALL_DAY";

/** 05-2h 장사 모양. 고르면 장사 시간, 바쁜 시간대가 채워진다. */
export const PATTERNS: Record<PatternKey, { label: string; sub: string; icon: "sun" | "moon" | "sunrise"; hours: Hours }> = {
  LUNCH_DINNER: {
    label: "점심, 저녁 장사",
    sub: "11:00 ~ 21:00, 브레이크 있음",
    icon: "sun",
    hours: {
      open_time: "11:00",
      close_time: "21:00",
      break_time: { start: "15:00", end: "17:00" },
      dayparts: { LUNCH: { start: "11:30", end: "14:00" }, DINNER: { start: "17:30", end: "20:00" }, NIGHT: { start: "20:00", end: "21:00" } },
      busy_dayparts: ["LUNCH", "DINNER"],
      closed_weekdays: [],
    },
  },
  EVENING_NIGHT: {
    label: "저녁, 밤 장사",
    sub: "17:00 ~ 새벽 2:00",
    icon: "moon",
    hours: {
      open_time: "17:00",
      close_time: "02:00",
      break_time: null,
      dayparts: { LUNCH: { start: "11:00", end: "13:30" }, DINNER: { start: "18:00", end: "20:30" }, NIGHT: { start: "22:00", end: "24:00" } },
      busy_dayparts: ["DINNER", "NIGHT"],
      closed_weekdays: [],
    },
  },
  ALL_DAY: {
    label: "아침부터 저녁까지",
    sub: "08:00 ~ 20:00",
    icon: "sunrise",
    hours: {
      open_time: "08:00",
      close_time: "20:00",
      break_time: null,
      dayparts: { LUNCH: { start: "11:30", end: "13:30" }, DINNER: { start: "17:30", end: "19:30" }, NIGHT: { start: "19:30", end: "20:00" } },
      busy_dayparts: ["LUNCH", "DINNER"],
      closed_weekdays: [],
    },
  },
};

export const WEEKDAYS: { code: Weekday; ko: string }[] = [
  { code: "MON", ko: "월" },
  { code: "TUE", ko: "화" },
  { code: "WED", ko: "수" },
  { code: "THU", ko: "목" },
  { code: "FRI", ko: "금" },
  { code: "SAT", ko: "토" },
  { code: "SUN", ko: "일" },
];

export const toMin = (t: string) => {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
};
export const fromMin = (m: number) => {
  const x = ((m % 1440) + 1440) % 1440;
  return `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;
};
/** 문 여는 시간부터 몇 분 지났는지. 새벽에 닫는 가게도 순서가 맞게 하루를 넘겨 센다. */
export const sinceOpen = (t: string, open: string) => (toMin(t) - toMin(open) + 1440) % 1440;
export const openLength = (h: Pick<Hours, "open_time" | "close_time">) => sinceOpen(h.close_time, h.open_time) || 1440;
/** "02:00" → "새벽 2:00", 그 밖은 그대로 */
export const clockLabel = (t: string) => (toMin(t) < 6 * 60 ? `새벽 ${Number(t.slice(0, 2))}:${t.slice(3)}` : t);
export const hoursLabel = (h: Pick<Hours, "open_time" | "close_time">) => `${h.open_time} ~ ${clockLabel(h.close_time)}`;

/** 바쁜 시간대를 문 연 시각 기준 분으로 (시간순) */
function busyRanges(h: Hours) {
  return h.busy_dayparts
    .map((d) => ({ d, a: sinceOpen(h.dayparts[d].start, h.open_time), b: sinceOpen(h.dayparts[d].end === "24:00" ? "00:00" : h.dayparts[d].end, h.open_time) || 1440 }))
    .filter((r) => r.a < openLength(h))
    .sort((x, y) => x.a - y.a);
}

/** 바쁜 시간 사이 가장 긴 빈 시간 */
function longestGap(h: Hours): { from: number; to: number; after: Daypart | null } | null {
  const rs = busyRanges(h);
  let best: { from: number; to: number; after: Daypart | null } | null = null;
  for (let i = 0; i + 1 < rs.length; i++) {
    const g = { from: rs[i].b, to: rs[i + 1].a, after: rs[i].d };
    if (g.to - g.from > 0 && (!best || g.to - g.from > best.to - best.from)) best = g;
  }
  return best;
}

const floor30 = (m: number) => Math.floor(m / 30) * 30;

export interface SlotPlan {
  time: string;
  label: string;
  reason: string;
}

/** 규칙 (05-3 규칙 보드)
 *  1. 출근 후: 출근 예정 시간 10분 뒤 (그때가 점심 바쁜 시간이면 출근할 때). 출근 시간을 모르면 문 여는 시간 30분 전
 *  2. 한가할 때: 브레이크 타임이 있으면 시작 30분 뒤, 없으면 바쁜 시간 사이 가장 긴 빈 시간의 가운데(30분 단위로 내림)
 *  3. 마감 전: 퇴근 예정 시간 30분 전. 퇴근 시간을 모르면 문 닫는 시간 30분 전
 */
export function suggestSlots(h: Hours & { work_hours?: { start: string; end: string } | null }): Record<Slot, SlotPlan> {
  const open = toMin(h.open_time);
  let afternoon: SlotPlan;
  if (h.break_time) {
    afternoon = { time: fromMin(toMin(h.break_time.start) + 30), label: "브레이크 타임", reason: "브레이크 시작 30분 뒤" };
  } else {
    const g = longestGap(h);
    if (g) {
      const mid = floor30(open + g.from + (g.to - g.from) / 2);
      afternoon = { time: fromMin(mid), label: g.after === "LUNCH" ? "점심 장사 끝나고" : "손님 빠질 때", reason: g.after === "LUNCH" ? "점심 장사 끝난 뒤" : "바쁜 시간 사이" };
    } else afternoon = { time: fromMin(open + 120), label: "장사 중 한가할 때", reason: "문 열고 2시간 뒤" };
  }
  const work = h.work_hours;
  let opening: SlotPlan = { time: fromMin(open - 30), label: "출근 후", reason: "문 열기 30분 전" };
  let closing: SlotPlan = { time: fromMin(toMin(h.close_time) - 30), label: "마감 전", reason: "문 닫기 30분 전" };
  if (work) {
    const start = toMin(work.start);
    const lunch = h.busy_dayparts.includes("LUNCH") ? toMin(h.dayparts.LUNCH.start) : Infinity;
    opening = start + 10 >= lunch && start < lunch ? { time: work.start, label: "출근 후", reason: "출근할 때" } : { time: fromMin(start + 10), label: "출근 후", reason: "출근하고 10분 뒤" };
    closing = { time: fromMin(toMin(work.end) - 30), label: "퇴근 전", reason: "퇴근 30분 전" };
  }
  return { OPENING: opening, AFTERNOON: afternoon, CLOSING: closing };
}

/** 지금 설정된 알림 시각의 이름과 이유. 사장님이 시각을 바꿔도 이름은 장사 모양을 따른다. */
export function slotInfo(s: Hours & { slots: Record<Slot, string>; work_hours?: { start: string; end: string } | null }): Record<Slot, SlotPlan> {
  const sug = suggestSlots(s);
  const out = {} as Record<Slot, SlotPlan>;
  for (const k of ["OPENING", "AFTERNOON", "CLOSING"] as Slot[]) {
    const t = s.slots[k];
    out[k] = { time: t, label: sug[k].label, reason: t === sug[k].time ? sug[k].reason : "사장님이 고른 시간" };
  }
  return out;
}

export function slotLabel(s: Hours & { slots: Record<Slot, string> }, slot: Slot): string {
  return slotInfo(s)[slot].label;
}

/** 지금 알림 시각 대신 고를 수 있는 시각 3개 (05-3t). 추천 시각을 맨 앞에 둔다. */
export function slotChoices(h: Hours & { work_hours?: { start: string; end: string } | null }, slot: Slot): { time: string; recommended: boolean }[] {
  const base = toMin(suggestSlots(h)[slot].time);
  // 마감 전 알림은 문 닫는 시간을 넘길 수 없어서 (서버 검사 SLOT_OUTSIDE_OPEN_HOURS) 30분 일찍도 고를 수 있게 한다.
  const steps = slot === "CLOSING" ? [0, -30, 30] : [0, 30, 60];
  return steps.map((d, i) => ({ time: fromMin(base + d), recommended: i === 0 }));
}

/** 이 가게가 고른 장사 모양 (설정 값이 모양과 같으면) */
export function patternOf(h: Hours): PatternKey | null {
  for (const [k, p] of Object.entries(PATTERNS) as [PatternKey, (typeof PATTERNS)[PatternKey]][]) {
    if (p.hours.open_time === h.open_time && p.hours.close_time === h.close_time && !!p.hours.break_time === !!h.break_time) return k;
  }
  return null;
}

// ---------- 06: 요일별 장사 시간 (06-2c, 06-2e, 06-2i, 06-19h) ----------
// 알림 시각은 하루 3개 하나로 둔다(가장 흔한 장사 시간 기준). 일찍 닫는 날은 마감 전 알림만 그만큼 당긴다.

export type DayHours = { open: string; close: string };
export type WeeklyHours = Record<Weekday, DayHours | null>;

/** Date.getUTCDay() 순서 (0 = 일요일) */
export const DAY_CODES: Weekday[] = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
export const WEEKDAY_KO: Record<Weekday, string> = { MON: "월", TUE: "화", WED: "수", THU: "목", FRI: "금", SAT: "토", SUN: "일" };

/** "2026-11-19" → "THU" (서울 기준) */
export function weekdayOf(ymd: string): Weekday {
  return DAY_CODES[new Date(`${ymd}T12:00:00+09:00`).getUTCDay()];
}

/** 설정에 요일별 시간이 없으면(예전 응답) 하나뿐인 장사 시간과 쉬는 날로 만든다. */
export function weeklyOf(s: Pick<StoreSettings, "open_time" | "close_time" | "closed_weekdays" | "weekly_hours">): WeeklyHours {
  if (s.weekly_hours) return s.weekly_hours;
  return Object.fromEntries(WEEKDAYS.map(({ code }) => [code, s.closed_weekdays.includes(code) ? null : { open: s.open_time, close: s.close_time }])) as WeeklyHours;
}

/** 요일별 시간에서 대표 장사 시간(가장 많은 요일이 쓰는 시간)과 쉬는 날을 뽑는다. 서버 open_time, close_time, closed_weekdays 자리. */
export function summarizeWeekly(w: WeeklyHours): { open_time: string; close_time: string; closed_weekdays: Weekday[] } {
  const count = new Map<string, number>();
  for (const { code } of WEEKDAYS) {
    const d = w[code];
    if (d) count.set(`${d.open}-${d.close}`, (count.get(`${d.open}-${d.close}`) ?? 0) + 1);
  }
  const top = [...count.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "10:00-22:00";
  const [open_time, close_time] = top.split("-");
  return { open_time, close_time, closed_weekdays: WEEKDAYS.filter(({ code }) => !w[code]).map(({ code }) => code) };
}

/** 06-2c, 06-19h 표시: 같은 시간인 이어진 요일을 묶는다. ["월요일 쉬어요", "화 ~ 토 11:00 ~ 21:00", "일 11:00 ~ 20:00"] */
export function weeklyRows(w: WeeklyHours): { days: string; text: string; closed: boolean }[] {
  const rows: { codes: Weekday[]; key: string }[] = [];
  for (const { code } of WEEKDAYS) {
    const d = w[code];
    const key = d ? `${d.open}-${d.close}` : "closed";
    const last = rows[rows.length - 1];
    if (last && last.key === key) last.codes.push(code);
    else rows.push({ codes: [code], key });
  }
  return rows.map(({ codes, key }) => {
    const first = WEEKDAY_KO[codes[0]];
    const lastKo = WEEKDAY_KO[codes[codes.length - 1]];
    const days = codes.length === 1 ? first : codes.length === 2 ? `${first}, ${lastKo}` : `${first} ~ ${lastKo}`;
    if (key === "closed") return { days, text: codes.length === 1 ? `${first}요일 쉬어요` : `${days} 쉬어요`, closed: true };
    const [open, close] = key.split("-");
    return { days, text: `${days} ${open} ~ ${clockLabel(close)}`, closed: false };
  });
}

/** 장사 시간으로 점심, 저녁, 밤 시간대를 짐작한다 (네이버에서 불러오거나 직접 적었을 때). 바쁜 시간은 점심, 저녁. */
export function guessDayparts(open: string, close: string, brk: { start: string; end: string } | null | undefined): Pick<StoreSettings, "dayparts" | "busy_dayparts"> {
  const o = toMin(open);
  const len = sinceOpen(close, open) || 1440;
  const c = o + len;
  if (o >= 15 * 60 || c > 24 * 60 + 60) {
    // 저녁, 밤 장사 (05-3e와 같은 모양)
    return { dayparts: PATTERNS.EVENING_NIGHT.hours.dayparts, busy_dayparts: ["DINNER", "NIGHT"] };
  }
  const lunchEnd = brk ? toMin(brk.start) : Math.min(14 * 60, c - 60);
  const dinnerStart = brk ? toMin(brk.end) + 30 : Math.max(17 * 60 + 30, lunchEnd + 60);
  const nightStart = Math.max(dinnerStart + 60, c - 60);
  return {
    dayparts: {
      LUNCH: { start: fromMin(Math.max(o + 30, 11 * 60)), end: fromMin(lunchEnd) },
      DINNER: { start: fromMin(dinnerStart), end: fromMin(nightStart) },
      NIGHT: { start: fromMin(nightStart), end: c >= 1440 ? "24:00" : fromMin(c) },
    },
    busy_dayparts: ["LUNCH", "DINNER"],
  };
}

/** 그 날(장사 날짜 ymd) 실제로 받는 알림 시각. 일찍(늦게) 닫는 요일은 마감 전 알림만 그만큼 옮긴다. 쉬는 날이면 null. */
export function slotTimeOn(s: StoreSettings, slot: Slot, ymd: string): string | null {
  const day = weeklyOf(s)[weekdayOf(ymd)];
  if (!day) return null;
  if (slot !== "CLOSING") return s.slots[slot];
  const base = sinceOpen(s.close_time, s.open_time) || 1440;
  const mine = sinceOpen(day.close, s.open_time) || 1440;
  return fromMin(toMin(s.slots.CLOSING) + (mine - base));
}

/** 장사 날짜 ymd의 알림 시각 전체("2026-11-19T20:30:00+09:00"). 새벽 마감 가게의 마감 전 알림은 다음 날짜가 된다. 쉬는 날이면 null. */
export function slotAtOn(s: StoreSettings, slot: Slot, ymd: string): string | null {
  const t = slotTimeOn(s, slot, ymd);
  if (!t) return null;
  // 알림은 출근 준비를 위해 문 열기 1시간 전부터 받을 수 있어서 그때부터 센다.
  const from = fromMin(toMin(s.open_time) - 60);
  const overnight = sinceOpen(t, from) > sinceOpen("23:59", from);
  const day = overnight ? new Date(new Date(`${ymd}T12:00:00+09:00`).getTime() + 86400e3 + 9 * 3600e3).toISOString().slice(0, 10) : ymd;
  return `${day}T${t}:00+09:00`;
}
