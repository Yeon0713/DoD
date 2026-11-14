// 지난 기록: 날짜마다 도나와 함께 한 일(답글, 점검, 메뉴판, 포스터) 수. 홈 오른쪽 아래 "지난 기록"이 쓴다.
// 끝낸 카드는 카드 상태(cardState, 끝낸 시각 at)에 있다. 카드 하나가 어느 계획을 묶었는지(좋은 리뷰 묶음은 여러 개)는
// 그날 홈이 알고 있으므로, 홈이 끝낸 카드의 계획 id 를 여기 적어 둔다. 적어 둔 것이 없으면 카드 id 에서 계획 id 를 읽는다.
import type { CardStatus } from "./cardState";
import { createStore } from "./store";
import { ymd } from "./time";
import { DONE_KINDS, kindOf, type DoneKind } from "./todayCards";

const donePlans = createStore<Record<string, string[]>>("dona.donePlans.v1", {});

/** 홈: 끝낸 카드가 묶은 계획 id 를 적어 둔다 (이미 같으면 쓰지 않는다) */
export function rememberDonePlans(entries: [string, string[]][]) {
  const saved = donePlans.read();
  const changed = entries.filter(([id, plans]) => plans.length && saved[id]?.join() !== plans.join());
  if (changed.length) donePlans.write(Object.fromEntries(changed));
}

/** "APPROVAL_REQUEST:REVIEW_FIX:risk_001:2026-10-07" → "REVIEW_FIX:risk_001:2026-10-07" */
function planOfCard(cardId: string): string | null {
  const [kind, ...rest] = cardId.split(":");
  if (kind === "BASIC") return rest.length > 1 ? rest.slice(1).join(":") : null;
  return rest.length ? rest.join(":") : null;
}

export type DayRecord = { date: string; counts: Record<DoneKind, number> };

/** 날짜마다 함께 한 일 수 (최근 날짜부터). 같은 계획의 승인과 실행은 한 번만 센다. */
export function doneByDate(cards: Record<string, CardStatus>, plans = donePlans.read()): DayRecord[] {
  const byDate = new Map<string, Set<string>>();
  for (const [id, s] of Object.entries(cards)) {
    if (s.kind !== "done" || !s.at) continue;
    const ids = plans[id] ?? [planOfCard(id)].filter((p): p is string => !!p);
    const day = ymd(new Date(s.at));
    const set = byDate.get(day) ?? new Set<string>();
    ids.forEach((p) => set.add(p));
    byDate.set(day, set);
  }
  const days: DayRecord[] = [];
  for (const [date, set] of byDate) {
    const counts = Object.fromEntries(DONE_KINDS.map((k) => [k, 0])) as Record<DoneKind, number>;
    for (const p of set) {
      const k = kindOf(p);
      if (k) counts[k] += 1;
    }
    if (DONE_KINDS.some((k) => counts[k] > 0)) days.push({ date, counts });
  }
  return days.sort((a, b) => b.date.localeCompare(a.date));
}

export function useDonePlans() {
  return donePlans.useValue();
}
