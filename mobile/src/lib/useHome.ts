// 서브 화면들이 쓰는 공통 데이터. 오늘 화면과 같은 캐시를 쓴다.
import { useMemo } from "react";
import { USE_MOCK } from "./api";
import { devFlags } from "./dev";
import { prefs } from "./localStore";
import { nowFrom } from "./time";
import { useHomeData } from "./useHomeData";

/** 앱은 서버 렌더링이 없어서 늘 true. Next.js 판 화면 코드와 모양을 맞추려고 남겨 둔다. */
export function useMounted() {
  return true;
}

export function useHome() {
  const q = useHomeData();
  const p = prefs.useValue();
  const f = devFlags.useValue();
  // 개발 화면에서 가상 시각을 바꾸면 다시 계산한다. 모아 보기에서 연 카드가 있으면 그 카드가 온 시각을 지금으로 본다.
  const devNow = f.scene ?? f.now;
  const now = useMemo(() => nowFrom(devNow), [devNow]);
  return { ...q, mounted: true, now, prefs: p, allWeek: USE_MOCK && f.allWeek };
}
