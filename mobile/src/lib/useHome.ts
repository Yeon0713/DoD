// 화면들이 같이 쓰는 홈 데이터. 같은 캐시(useHomeData)를 쓴다.
import { useEffect, useMemo, useState } from "react";
import { AppState } from "react-native";
import { USE_MOCK } from "./api";
import { useCardState } from "./cardState";
import { devFlags } from "./dev";
import { drafts, prefs } from "./localStore";
import { nowFrom } from "./time";
import { findPersona, findScene } from "@/mocks/personas";
import { buildTodayCards, type CardScope } from "./todayCards";
import { useHomeData } from "./useHomeData";

/**
 * 실제 서버 모드에서 시계를 따라가게 하는 값. 1분마다, 그리고 앱으로 돌아올 때 하나씩 오른다.
 * 탭 화면은 한 번 뜨면 계속 살아 있어서, 이게 없으면 앱을 켜 둔 채로는 알림 시각이 되어도 새 카드가 나오지 않고
 * 미뤄 둔 카드도 돌아오지 않는다. 고정 샘플 모드는 개발 화면에서 고른 가상 시각만 쓴다.
 */
function useClockTick(enabled: boolean): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => setTick((t) => t + 1), 60_000);
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") setTick((t) => t + 1);
    });
    return () => {
      clearInterval(id);
      sub.remove();
    };
  }, [enabled]);
  return tick;
}

/** 홈 데이터와 지금 시각, 이 기기 설정 */
export function useHome() {
  const q = useHomeData();
  const p = prefs.useValue();
  const f = devFlags.useValue();
  // 개발 화면에서 가상 시각을 바꾸면 다시 계산한다. 모아 보기에서 연 카드가 있으면 그 카드가 온 시각을 지금으로 본다.
  const devNow = f.cardNow ?? f.now;
  const tick = useClockTick(!USE_MOCK);
  const now = useMemo(() => {
    void tick; // 시계가 가면 지금을 다시 읽는다
    return nowFrom(devNow);
  }, [devNow, tick]);
  // 목업 검토: 한 주 모아 보기가 먼저, 아니면 고른 매장 시나리오의 카드만
  const allWeek = USE_MOCK && f.allWeek;
  const persona = USE_MOCK && !allWeek ? findPersona(f.persona) : null;
  const scene = persona ? findScene(persona, f.personaScene) : null;
  const scope = useMemo<CardScope>(() => (allWeek ? { all: true } : scene ? { all: true, only: scene.cards } : {}), [allWeek, scene]);
  return { ...q, now, prefs: p, allWeek, persona, scene, scope };
}

/** 홈, 지금 할 일, 끝낸 일 화면이 쓰는 오늘 카드 목록. 카드 상태, 고쳐 쓴 답글, 개발 화면에서 고른 카드를 함께 반영한다. */
export function useTodayCards() {
  const home = useHome();
  const store = useCardState();
  const savedDrafts = drafts.useValue();
  const focus = devFlags.useValue().card;
  const { data, now, prefs: p, scope } = home;
  const view = useMemo(() => (data ? buildTodayCards(data, now, p, store, focus, savedDrafts, scope) : null), [data, now, p, store, focus, savedDrafts, scope]);
  return { ...home, store, view };
}
