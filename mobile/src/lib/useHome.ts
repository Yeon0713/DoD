// 화면들이 같이 쓰는 홈 데이터. 같은 캐시(useHomeData)를 쓴다.
import { useMemo } from "react";
import { USE_MOCK } from "./api";
import { useCardState } from "./cardState";
import { devFlags } from "./dev";
import { drafts, prefs } from "./localStore";
import { nowFrom } from "./time";
import { buildTodayCards } from "./todayCards";
import { useHomeData } from "./useHomeData";

/** 홈 데이터와 지금 시각, 이 기기 설정 */
export function useHome() {
  const q = useHomeData();
  const p = prefs.useValue();
  const f = devFlags.useValue();
  // 개발 화면에서 가상 시각을 바꾸면 다시 계산한다. 모아 보기에서 연 카드가 있으면 그 카드가 온 시각을 지금으로 본다.
  const devNow = f.scene ?? f.now;
  const now = useMemo(() => nowFrom(devNow), [devNow]);
  return { ...q, now, prefs: p, allWeek: USE_MOCK && f.allWeek };
}

/** 홈, 지금 할 일, 끝낸 일 화면이 쓰는 오늘 카드 목록. 카드 상태, 고쳐 쓴 답글, 개발 화면에서 고른 카드를 함께 반영한다. */
export function useTodayCards() {
  const home = useHome();
  const store = useCardState();
  const savedDrafts = drafts.useValue();
  const focus = devFlags.useValue().card;
  const { data, now, prefs: p, allWeek } = home;
  const view = useMemo(() => (data ? buildTodayCards(data, now, p, store, focus, savedDrafts, allWeek) : null), [data, now, p, store, focus, savedDrafts, allWeek]);
  return { ...home, store, view };
}
