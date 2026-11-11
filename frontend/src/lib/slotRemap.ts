// 고정 샘플 모드 전용. 예시 계획(contracts/sample_responses/plan_response.example.json)은 기본 알림 시각
// 10:00(출근 후), 14:00(오후), 21:30(마감 전)으로 계산돼 있다. 사장님이 장사 시간이나 알림 시각을 바꾸면
// 서버는 새 시각으로 다시 계산하므로, 프론트 목업도 같은 이름의 알림 시각으로 옮겨 준다.
// 새벽 알림(예: 01:30)은 다음 날로, 쉬는 날의 알림은 다음 장사하는 날 같은 이름의 시각으로 옮긴다.
import type { NoticeItem, PlanItem, Slot, StoreSettings, TodayBatch, Weekday } from "@/types/contract";
import { fromMin, sinceOpen, toMin } from "./hours";
import { addDays, dateOnly } from "./time";

const SAMPLE: Record<string, Slot> = { "10:00": "OPENING", "14:00": "AFTERNOON", "21:30": "CLOSING" };
const CODES: Weekday[] = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

function weekdayCode(ymd: string): Weekday {
  return CODES[new Date(dateOnly(ymd).getTime() + 9 * 3600e3).getUTCDay()];
}

function move(iso: string | null, s: StoreSettings): string | null {
  if (!iso) return iso;
  const slot = SAMPLE[iso.slice(11, 16)];
  if (!slot) return iso;
  let day = iso.slice(0, 10);
  const t = s.slots[slot];
  // 문 연 뒤 하루를 넘긴 시각(새벽)은 다음 날짜다.
  // 출근 준비 알림은 문 열기 1시간 전부터라서 그때부터 센다.
  const from = fromMin(toMin(s.open_time) - 60);
  if (sinceOpen(t, from) > sinceOpen("23:59", from)) day = addDays(day, 1);
  for (let i = 0; i < 7 && s.closed_weekdays.includes(weekdayCode(day)); i++) day = addDays(day, 1);
  return `${day}T${t}:00+09:00`;
}

export function remapToStoreSlots(plans: PlanItem[], notices: NoticeItem[], s: StoreSettings, batches: TodayBatch[] = []) {
  return {
    plans: plans.map((p) => {
      const approval = move(p.approval_request_at, s)!;
      let exec = move(p.execute_at, s);
      // 쉬는 날 때문에 승인이 실행보다 늦어지면 실행 알림을 하루씩 뒤로 미룬다 (승인 전에 "올릴 시간이에요"가 오지 않게).
      for (let i = 0; exec && i < 7 && new Date(exec).getTime() <= new Date(approval).getTime(); i++) exec = move(`${addDays(exec.slice(0, 10), 1)}${exec.slice(10)}`, s) ?? exec;
      return { ...p, approval_request_at: approval, execute_at: exec, deadline_at: p.deadline_at };
    }),
    notices: notices.map((n) => ({ ...n, slot_at: move(n.slot_at, s)! })),
    batches: batches.map((b) => ({ ...b, slot_at: move(b.slot_at, s)! })),
  };
}
