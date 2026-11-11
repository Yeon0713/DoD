// 이 기기에만 저장하는 값들. 서버 API가 생기면 그쪽으로 옮긴다 (docs/frontend_plan_v4.md 7-2).
import { useSyncExternalStore } from "react";
import { session } from "./storage";
import { createStore } from "./store";

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

export type Toast = { title: string; sub?: string; id: number };
const toastListeners = new Set<() => void>();
let toastSeq = 0;

/** 화면을 옮긴 뒤 위에 잠깐 띄울 띠 (05-5s). 앱 맨 위의 띠 자리(ToastHost)가 보여 준다. */
export function flashToast(title: string, sub?: string) {
  session.set("dona.toast", JSON.stringify({ title, sub, id: ++toastSeq }));
  toastListeners.forEach((l) => l());
}

export function clearToast() {
  session.delete("dona.toast");
  toastListeners.forEach((l) => l());
}

let toastCache: { raw: string | undefined; value: Toast | null } = { raw: undefined, value: null };
export function useToast(): Toast | null {
  return useSyncExternalStore(
    (cb) => {
      toastListeners.add(cb);
      return () => {
        toastListeners.delete(cb);
      };
    },
    () => {
      const raw = session.get("dona.toast");
      if (raw !== toastCache.raw) toastCache = { raw, value: raw ? (JSON.parse(raw) as Toast) : null };
      return toastCache.value;
    },
  );
}
