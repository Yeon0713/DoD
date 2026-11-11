// 고정 샘플 모드에서 쓰는 알림 묶음 만들기. 서버 server/app/planner/priority_and_grouping.py 와 같은 규칙이다.
// 고정 샘플의 today 응답은 화요일 하루뿐이라, plan 응답에서 데모 주간 모든 날의 묶음을 다시 만든다.
import type { NoticeItem, PlanItem, Slot, StoreSettings, TodayBatch, TodayEntry } from "@/types/contract";
import { addDays, hhmm, ymd } from "./time";

function slotOf(iso: string, s: StoreSettings): Slot | null {
  const t = hhmm(iso);
  return (Object.entries(s.slots).find(([, v]) => v === t)?.[0] as Slot | undefined) ?? null;
}

/** 우선순위: 1 불만 답글, 2 반복 불만 개선, 3 다음 날 실행할 일의 승인 요청, 4 그 밖 */
function approvalPriority(p: PlanItem): 1 | 2 | 3 | 4 {
  if (p.task_type === "REVISIT_REPLY" && p.revisit_class === "QUICK") return 1;
  if (p.task_type === "REVIEW_FIX") return 2;
  if (p.execute_at && ymd(new Date(p.execute_at)) === addDays(ymd(new Date(p.approval_request_at)), 1)) return 3;
  return 4;
}

/** 실행 시각이 따로 있고 알림 가능 시각이면 실행 알림을 보낸다. */
function needsExecuteReminder(p: PlanItem, s: StoreSettings) {
  return !!p.execute_at && p.execute_at !== p.approval_request_at && slotOf(p.execute_at, s) !== null;
}

export function groupIntoBatches(plans: PlanItem[], notices: NoticeItem[], s: StoreSettings): TodayBatch[] {
  type Row = { pr: number; deadline: string | null; id: string; entry: TodayEntry };
  const rows = new Map<string, Row[]>();
  const add = (at: string, r: Row) => {
    const key = new Date(at).toISOString();
    rows.set(key, [...(rows.get(key) ?? []), r]);
  };
  for (const p of plans) {
    const pr = approvalPriority(p);
    add(p.approval_request_at, { pr, deadline: p.deadline_at, id: p.plan_id, entry: { plan_id: p.plan_id, notice_id: null, notify_kind: "APPROVAL_REQUEST", priority: pr } });
    if (needsExecuteReminder(p, s)) {
      add(p.execute_at!, { pr: 4, deadline: p.deadline_at, id: p.plan_id, entry: { plan_id: p.plan_id, notice_id: null, notify_kind: "EXECUTE_REMINDER", priority: 4 } });
    }
  }
  for (const n of notices) {
    add(n.slot_at, { pr: 4, deadline: null, id: n.notice_id, entry: { plan_id: null, notice_id: n.notice_id, notify_kind: n.kind === "WEEKLY_PREVIEW" ? "PREVIEW" : "NOTICE", priority: 4 } });
  }
  const toSeoulIso = (utc: string) => {
    const d = new Date(new Date(utc).getTime() + 9 * 3600e3).toISOString().slice(0, 19);
    return `${d}+09:00`;
  };
  return [...rows.keys()].sort().flatMap((key) => {
    const at = toSeoulIso(key);
    const slot = slotOf(at, s);
    if (!slot) return [];
    const sorted = rows.get(key)!.sort(
      (a, b) =>
        a.pr - b.pr ||
        Number(a.deadline === null) - Number(b.deadline === null) ||
        (a.deadline && b.deadline ? new Date(a.deadline).getTime() - new Date(b.deadline).getTime() : 0) ||
        a.id.localeCompare(b.id),
    );
    return [{ slot_at: at, slot, entries: sorted.map((r) => r.entry) }];
  });
}
