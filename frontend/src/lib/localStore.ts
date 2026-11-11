"use client";
// 이 기기에만 저장하는 값들. 서버 API가 생기면 그쪽으로 옮긴다 (docs/frontend_plan_v4.md 7-2).
import { useSyncExternalStore } from "react";

function createStore<T extends object>(key: string, initial: T) {
  const listeners = new Set<() => void>();
  let cache: T | null = null;

  const read = (): T => {
    if (typeof window === "undefined") return initial;
    if (cache) return cache;
    try {
      cache = { ...initial, ...(JSON.parse(localStorage.getItem(key) ?? "{}") as Partial<T>) };
    } catch {
      cache = initial;
    }
    return cache;
  };
  const write = (patch: Partial<T>) => {
    cache = { ...read(), ...patch };
    localStorage.setItem(key, JSON.stringify(cache));
    listeners.forEach((l) => l());
  };
  const reset = () => {
    cache = initial;
    localStorage.removeItem(key);
    listeners.forEach((l) => l());
  };
  const use = (): T =>
    useSyncExternalStore(
      (cb) => {
        listeners.add(cb);
        return () => listeners.delete(cb);
      },
      read,
      () => initial,
    );
  return { read, write, reset, use };
}

export interface Prefs {
  /** 처음 쓰는 날 흐름(04-1 ~ 04-3b)을 마쳤는지 */
  onboarded: boolean;
  /** 알림 켜기를 미뤘는지 (04-4n 띠) */
  notifyOff: boolean;
  /** 첫날 카드(04-4f)를 아직 안 봤는지 */
  firstDayPending: boolean;
  naverConnected: boolean;
  /** 메뉴 순서 알아서 바꾸기 (04-55, 04-58) */
  naverAuto: boolean;
  /** 04-50에서 "제가 직접 할게요"를 골랐는지 */
  naverDeclined: boolean;
}

export const prefs = createStore<Prefs>("dona.prefs.v1", {
  onboarded: false,
  notifyOff: false,
  firstDayPending: false,
  naverConnected: false,
  naverAuto: false,
  naverDeclined: false,
});

/** 사장님이 고쳐 쓴 답글. planId 또는 리뷰 id → 글 */
export const drafts = createStore<Record<string, string>>("dona.drafts.v1", {});

/** 화면을 옮긴 뒤 위에 잠깐 띄울 띠 (04-5s) */
export function flashToast(title: string, sub?: string) {
  sessionStorage.setItem("dona.toast", JSON.stringify({ title, sub }));
  // 같은 화면에 있는 띠 자리도 바로 알 수 있게 알린다.
  window.dispatchEvent(new Event("dona:toast"));
}

export function peekToast(): { title: string; sub?: string } | null {
  const raw = sessionStorage.getItem("dona.toast");
  return raw ? JSON.parse(raw) : null;
}

export function clearToast() {
  sessionStorage.removeItem("dona.toast");
}
