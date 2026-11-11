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
 *  1. 출근 후: 문 여는 시간 30분 전
 *  2. 한가할 때: 브레이크 타임이 있으면 시작 30분 뒤, 없으면 바쁜 시간 사이 가장 긴 빈 시간의 가운데(30분 단위로 내림)
 *  3. 마감 전: 문 닫는 시간 30분 전
 */
export function suggestSlots(h: Hours): Record<Slot, SlotPlan> {
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
  return {
    OPENING: { time: fromMin(open - 30), label: "출근 후", reason: "문 열기 30분 전" },
    AFTERNOON: afternoon,
    CLOSING: { time: fromMin(toMin(h.close_time) - 30), label: "마감 전", reason: "문 닫기 30분 전" },
  };
}

/** 지금 설정된 알림 시각의 이름과 이유. 사장님이 시각을 바꿔도 이름은 장사 모양을 따른다. */
export function slotInfo(s: Hours & { slots: Record<Slot, string> }): Record<Slot, SlotPlan> {
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
export function slotChoices(h: Hours, slot: Slot): { time: string; recommended: boolean }[] {
  const base = toMin(suggestSlots(h)[slot].time);
  return [0, 30, 60].map((d, i) => ({ time: fromMin(base + d), recommended: i === 0 }));
}

/** 이 가게가 고른 장사 모양 (설정 값이 모양과 같으면) */
export function patternOf(h: Hours): PatternKey | null {
  for (const [k, p] of Object.entries(PATTERNS) as [PatternKey, (typeof PATTERNS)[PatternKey]][]) {
    if (p.hours.open_time === h.open_time && p.hours.close_time === h.close_time && !!p.hours.break_time === !!h.break_time) return k;
  }
  return null;
}
