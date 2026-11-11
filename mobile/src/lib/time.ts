// 시각은 모두 서울 기준이다. 서버 시각 문자열은 "2026-11-17T14:00:00+09:00" 모양이다.
import { USE_MOCK } from "./api";
import { devFlags } from "./dev";

/** 고정 샘플은 데모 주간 화요일 오후 알림 직후를 기준으로 그린다. 개발 화면(/dev)에서 바꿀 수 있다. */
export const DEMO_NOW = "2026-11-17T14:05:00+09:00";

function parseNow(q: string): Date {
  return new Date(/[+-]\d\d:\d\d$|Z$/.test(q) ? q : `${q}:00+09:00`);
}

/** 개발 화면에서 고른 가상 시각(q)으로 지금을 정한다. 훅에서 q를 의존값으로 넘기려고 따로 둔다. */
export function nowFrom(q: string | null): Date {
  if (!USE_MOCK) return new Date();
  return q ? parseNow(q) : new Date(DEMO_NOW);
}

export function currentNow(): Date {
  const f = devFlags.read();
  return nowFrom(f.scene ?? f.now);
}

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

/** "2026-11-19" → 서울 기준 그 날의 정오 Date (요일 계산용) */
export function dateOnly(ymd: string): Date {
  return new Date(`${ymd}T12:00:00+09:00`);
}

function seoulParts(d: Date) {
  const s = new Date(d.getTime() + 9 * 3600 * 1000);
  return { y: s.getUTCFullYear(), m: s.getUTCMonth() + 1, d: s.getUTCDate(), wd: s.getUTCDay(), h: s.getUTCHours(), min: s.getUTCMinutes() };
}

export function ymd(d: Date): string {
  const p = seoulParts(d);
  return `${p.y}-${String(p.m).padStart(2, "0")}-${String(p.d).padStart(2, "0")}`;
}

export function addDays(ymdStr: string, n: number): string {
  return ymd(new Date(dateOnly(ymdStr).getTime() + n * 86400000));
}

export function weekdayName(d: Date | string): string {
  const date = typeof d === "string" ? dateOnly(d.slice(0, 10)) : d;
  return `${WEEKDAYS[seoulParts(date).wd]}요일`;
}

export function monthDay(d: Date | string): string {
  const date = typeof d === "string" ? dateOnly(d.slice(0, 10)) : d;
  const p = seoulParts(date);
  return `${p.m}월 ${p.d}일`;
}

export function isWeekend(d: string): boolean {
  const wd = seoulParts(dateOnly(d)).wd;
  return wd === 0 || wd === 6;
}

/** "오전 10시", "오후 2시", "오후 9시 30분" */
export function clockKo(iso: string): string {
  const p = seoulParts(new Date(iso));
  const ampm = p.h < 12 ? "오전" : "오후";
  const h = p.h % 12 === 0 ? 12 : p.h % 12;
  return `${ampm} ${h}시${p.min ? ` ${p.min}분` : ""}`;
}

/** now 기준으로 "오늘", "내일", "토요일" */
export function relativeDay(iso: string, now: Date): string {
  const target = iso.slice(0, 10);
  const today = ymd(now);
  if (target === today) return "오늘";
  if (target === addDays(today, 1)) return "내일";
  return weekdayName(target);
}

/** "HH:MM" */
export function hhmm(iso: string): string {
  const p = seoulParts(new Date(iso));
  return `${String(p.h).padStart(2, "0")}:${String(p.min).padStart(2, "0")}`;
}
