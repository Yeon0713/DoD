// 카드 처리 상태(다 했어요, 나중에). 서버 API(PATCH /api/plan/{id})가 생기기 전까지 이 기기에만 저장한다.
import { createStore } from "./store";
import { currentNow } from "./time";

/** 끝낸 일(07): at = 끝낸 시각, note = 홈 "오늘 끝낸 일"에 쓸 말("답글을 올렸어요"), reply = 올린 답글 */
export type DoneInfo = { note?: string; reply?: string };
export type CardStatus = ({ kind: "done"; at?: string } & DoneInfo) | { kind: "snoozed"; until: string };
type Store = Record<string, CardStatus>;

const state = createStore<Store>("dona.cardState.v1", {});

export function markDone(cardId: string, info: DoneInfo = {}) {
  state.replace({ ...state.read(), [cardId]: { kind: "done", at: currentNow().toISOString(), ...info } });
}

export function snooze(cardId: string, untilIso: string) {
  state.replace({ ...state.read(), [cardId]: { kind: "snoozed", until: untilIso } });
}

export function resetCardState() {
  state.replace({});
}

export function readCardState(): Store {
  return state.read();
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
