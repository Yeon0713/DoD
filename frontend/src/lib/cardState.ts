"use client";
// 카드 처리 상태(다 했어요, 나중에). 서버 API(PATCH /api/plan/{id})가 생기기 전까지 이 기기에만 저장한다.
import { useSyncExternalStore } from "react";

export type CardStatus = { kind: "done" } | { kind: "snoozed"; until: string };
type Store = Record<string, CardStatus>;

const KEY = "dona.cardState.v1";
const listeners = new Set<() => void>();
let cache: Store | null = null;
const EMPTY: Store = {};

function read(): Store {
  if (typeof window === "undefined") return EMPTY;
  if (cache) return cache;
  try {
    cache = JSON.parse(localStorage.getItem(KEY) ?? "{}") as Store;
  } catch {
    cache = {};
  }
  return cache;
}

function write(next: Store) {
  cache = next;
  localStorage.setItem(KEY, JSON.stringify(next));
  listeners.forEach((l) => l());
}

export function markDone(cardId: string) {
  write({ ...read(), [cardId]: { kind: "done" } });
}

export function snooze(cardId: string, untilIso: string) {
  write({ ...read(), [cardId]: { kind: "snoozed", until: untilIso } });
}

export function resetCardState() {
  write({});
}

export function useCardState(): Store {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    read,
    () => EMPTY,
  );
}

/** now 기준으로 이 카드가 아직 할 일인지 */
export function isOpen(store: Store, cardId: string, now: Date): boolean {
  const s = store[cardId];
  if (!s) return true;
  if (s.kind === "done") return false;
  return new Date(s.until).getTime() <= now.getTime();
}
