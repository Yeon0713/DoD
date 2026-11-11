"use client";
// 서브 화면들이 쓰는 공통 데이터. 오늘 화면과 같은 캐시를 쓴다.
import { useMemo, useSyncExternalStore } from "react";
import { prefs } from "./localStore";
import { currentNow } from "./time";
import { useHomeData } from "./useHomeData";

const subscribeNothing = () => () => {};

export function useMounted() {
  return useSyncExternalStore(subscribeNothing, () => true, () => false);
}

export function useHome() {
  const mounted = useMounted();
  const q = useHomeData();
  const p = prefs.use();
  const now = useMemo(() => (mounted ? currentNow() : new Date(0)), [mounted]);
  return { ...q, data: mounted ? q.data : undefined, mounted, now, prefs: p };
}
