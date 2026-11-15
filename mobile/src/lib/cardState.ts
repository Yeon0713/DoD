// 카드 처리 상태(다 했어요, 나중에). 서버 API(PATCH /api/plan/{id})가 생기기 전까지 이 기기에만 저장한다.
import { createStore } from "./store";
import { stampNow } from "./time";

/** 끝낸 일(07): at = 끝낸 시각, note = 홈 "오늘 끝낸 일"에 쓸 말("답글을 올렸어요"), reply = 올린 답글 */
export type DoneInfo = { note?: string; reply?: string };
export type CardStatus = ({ kind: "done"; at?: string } & DoneInfo) | { kind: "snoozed"; until: string };
type Store = Record<string, CardStatus>;

const state = createStore<Store>("dona.cardState.v1", {});

export function markDone(cardId: string, info: DoneInfo = {}) {
  state.replace({ ...state.read(), [cardId]: { kind: "done", at: stampNow().toISOString(), ...info } });
}

/** 계획 하나를 끝냈다. 그 계획의 승인 요청 카드와 실행 알림 카드를 함께 끝낸다 (답글을 바로 올렸을 때, 포스터를 올렸을 때). */
export function markPlanDone(planId: string, info: DoneInfo = {}) {
  const at = stampNow().toISOString();
  const done = { kind: "done" as const, at, ...info };
  state.replace({ ...state.read(), [`APPROVAL_REQUEST:${planId}`]: done, [`EXECUTE_REMINDER:${planId}`]: done });
}

export function snooze(cardId: string, untilIso: string) {
  state.replace({ ...state.read(), [cardId]: { kind: "snoozed", until: untilIso } });
}

export function resetCardState() {
  state.replace({});
}

/** 테스트 계정별로 보관했다가 되살릴 때 (lib/testAccount.ts) */
export function cardStateSnapshot(): Record<string, CardStatus> {
  return state.read();
}
export function restoreCardState(saved: Record<string, CardStatus>) {
  state.replace(saved);
}

export function useCardState(): Store {
  return state.useValue();
}

/** now 기준으로 이 카드가 아직 할 일인지 */
export function isOpen(store: Store, cardId: string, now: Date): boolean {
  const s = store[cardId];
  if (!s) return true;
  if (s.kind === "done") return false;
  return new Date(s.until).getTime() <= now.getTime();
}
