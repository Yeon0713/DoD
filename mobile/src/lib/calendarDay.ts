// 달력에서 그 날 새로 시작하거나 끝나는 일을 읽는다. 카드(lib/cards.ts)와 메뉴판 순서(lib/menuOrder.ts)가 같이 쓴다.
import type { CalendarCell } from "@/types/contract";
import { addDays } from "./time";

export type DayKind = { tag: "GAME" | "EVENT" | "SEASON"; refId: string; on: boolean };

function tagsOn(cells: CalendarCell[], date: string): Map<string, string> {
  const m = new Map<string, string>();
  for (const c of cells) if (c.date === date) for (const r of c.reasons) m.set(r.tag, r.ref_id);
  return m;
}

/** 그 날 새로 시작하거나(on) 끝나는(off) 일. 메뉴판 카드가 어떤 일 때문인지 정한다. */
export function dayChange(cells: CalendarCell[], date: string): DayKind | null {
  const today = tagsOn(cells, date);
  const before = tagsOn(cells, addDays(date, -1));
  for (const tag of ["GAME", "EVENT", "SEASON"] as const) {
    if (today.has(tag) && !before.has(tag)) return { tag, refId: today.get(tag)!, on: true };
  }
  for (const tag of ["GAME", "EVENT"] as const) {
    if (before.has(tag) && !today.has(tag)) return { tag, refId: before.get(tag)!, on: false };
  }
  return null;
}

