// 고정 샘플 모드 전용. 예시 계획(contracts/sample_responses/plan_response.example.json)은 기본 알림 시각
// 10:00(출근 후), 14:00(오후), 21:30(마감 전)으로 계산돼 있다. 사장님이 장사 시간이나 알림 시각을 바꾸면
// 서버는 새 시각으로 다시 계산하므로, 프론트 목업도 같은 이름의 알림 시각으로 옮겨 준다.
// 새벽 알림(예: 01:30)은 다음 날로, 쉬는 날의 알림은 다음 장사하는 날 같은 이름의 시각으로 옮긴다.
// 06: 요일별 장사 시간을 따른다. 일찍 닫는 날은 마감 전 알림이 그만큼 당겨진다 (hours.ts slotTimeOn).
import type { NoticeItem, PlanItem, Slot, StoreSettings, TodayBatch } from "@/types/contract";
import { slotAtOn } from "./hours";
import { addDays } from "./time";

const SAMPLE: Record<string, Slot> = { "10:00": "OPENING", "14:00": "AFTERNOON", "21:30": "CLOSING" };

function move(iso: string | null, s: StoreSettings): string | null {
  if (!iso) return iso;
  const slot = SAMPLE[iso.slice(11, 16)];
  if (!slot) return iso;
  let day = iso.slice(0, 10);
  for (let i = 0; i < 7 && !slotAtOn(s, slot, day); i++) day = addDays(day, 1);
  return slotAtOn(s, slot, day) ?? iso;
}

export function remapToStoreSlots(plans: PlanItem[], notices: NoticeItem[], s: StoreSettings, batches: TodayBatch[] = []) {
  return {
    plans: plans.map((p) => {
      const approval = move(p.approval_request_at, s)!;
      let exec = move(p.execute_at, s);
      // 쉬는 날 때문에 승인이 실행보다 늦어지면 실행 알림을 하루씩 뒤로 미룬다 (승인 전에 "올릴 시간이에요"가 오지 않게).
      // 같은 시각이면 승인과 실행이 한 번에 된다(불만 답글).
      const sameAtFirst = p.execute_at === p.approval_request_at;
      for (let i = 0; exec && !sameAtFirst && i < 7 && new Date(exec).getTime() <= new Date(approval).getTime(); i++) {
        const slot = SAMPLE[p.execute_at!.slice(11, 16)];
        let day = addDays(exec.slice(0, 10), 1);
        if (slot) {
          for (let j = 0; j < 7 && !slotAtOn(s, slot, day); j++) day = addDays(day, 1);
          exec = slotAtOn(s, slot, day) ?? exec;
        } else exec = `${day}${exec.slice(10)}`;
      }
      if (sameAtFirst) exec = approval;
      return { ...p, approval_request_at: approval, execute_at: exec, deadline_at: p.deadline_at };
    }),
    notices: notices.map((n) => ({ ...n, slot_at: move(n.slot_at, s)! })),
    batches: batches.map((b) => ({ ...b, slot_at: move(b.slot_at, s)! })),
  };
}
