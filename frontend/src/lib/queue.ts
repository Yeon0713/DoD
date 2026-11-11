// 오늘 화면의 카드 줄 세우기. today 묶음을 plan 응답과 id로 붙이고 우선순위 순서로 정렬한다.
// 같은 실행 시각의 기본 답글(BASIC)은 카드 1장으로 묶는다 (docs/frontend_plan_v4.md 6장).
import type { ResultNotice } from "@/mocks/extras";
import type { NoticeItem, NotifyKind, PlanItem, PlanResponse, TodayResponse } from "@/types/contract";
import { ymd } from "./time";

export interface QueueEntry {
  /** 카드 처리 상태를 저장할 때 쓰는 id. 알림 종류가 다르면 같은 일이라도 다른 카드다. */
  cardId: string;
  notifyKind: NotifyKind;
  priority: number;
  slotAt: string;
  plan?: PlanItem;
  /** 기본 답글 묶음일 때 묶인 항목들 */
  group?: PlanItem[];
  notice?: NoticeItem;
  result?: ResultNotice;
}

export function buildQueue(today: TodayResponse, plan: PlanResponse, now: Date, results: ResultNotice[] = []): QueueEntry[] {
  const plans = new Map(plan.plan_items.map((p) => [p.plan_id, p]));
  const notices = new Map(plan.notice_items.map((n) => [n.notice_id, n]));
  const resultMap = new Map(results.map((r) => [r.notice_id, r]));
  const todayYmd = ymd(now);
  const out: QueueEntry[] = [];
  const basicGroups = new Map<string, QueueEntry>();

  for (const batch of today.batches) {
    // 오늘 날짜의 알림 중 이미 도착한 것만 보여 준다.
    if (batch.slot_at.slice(0, 10) !== todayYmd || new Date(batch.slot_at).getTime() > now.getTime()) continue;
    for (const e of batch.entries) {
      const p = e.plan_id ? plans.get(e.plan_id) : undefined;
      const n = e.notice_id ? notices.get(e.notice_id) : undefined;
      const r = e.notice_id ? resultMap.get(e.notice_id) : undefined;
      if (r) {
        out.push({ cardId: `${e.notify_kind}:${r.notice_id}`, notifyKind: e.notify_kind, priority: e.priority, slotAt: batch.slot_at, result: r });
        continue;
      }
      if (!p && !n) continue;
      const base = { notifyKind: e.notify_kind, priority: e.priority, slotAt: batch.slot_at };

      if (p && p.task_type === "REVISIT_REPLY" && p.revisit_class === "BASIC") {
        const key = `${e.notify_kind}:${p.execute_at}`;
        const g = basicGroups.get(key);
        if (g) {
          g.group!.push(p);
          continue;
        }
        const entry: QueueEntry = { ...base, cardId: `BASIC:${key}`, plan: p, group: [p] };
        basicGroups.set(key, entry);
        out.push(entry);
        continue;
      }
      out.push({ ...base, cardId: `${e.notify_kind}:${p ? p.plan_id : n!.notice_id}`, plan: p, notice: n });
    }
  }

  const deadline = (q: QueueEntry) => new Date(q.plan?.deadline_at ?? q.plan?.execute_at ?? q.slotAt).getTime();
  return out.sort((a, b) => a.priority - b.priority || deadline(a) - deadline(b));
}

/** now 다음에 오는 알림 시각. 오늘 화면이 비었을 때 "다음 알림은 마감 전 21:30" */
export function nextSlot(slots: Record<string, string>, now: Date): { slot: string; time: string; tomorrow: boolean } {
  const seoul = new Date(now.getTime() + 9 * 3600 * 1000);
  const mins = seoul.getUTCHours() * 60 + seoul.getUTCMinutes();
  const order = (Object.entries(slots) as [string, string][]).sort((a, b) => a[1].localeCompare(b[1]));
  for (const [slot, t] of order) {
    const [h, m] = t.split(":").map(Number);
    if (h * 60 + m > mins) return { slot, time: t, tomorrow: false };
  }
  return { slot: order[0][0], time: order[0][1], tomorrow: true };
}
