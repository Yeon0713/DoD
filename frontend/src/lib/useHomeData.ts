"use client";
// 오늘 화면에 필요한 응답 5개를 한 번에 불러온다.
// 마지막으로 받은 값을 이 기기에 저장해 두고, 다시 열 때 먼저 보여 준다 (04-8b "지난 할 일 먼저").
import { useQuery } from "@tanstack/react-query";
import type { CalendarResponse, PlanResponse, ReviewsResponse, SettingsResponse, TodayResponse } from "@/types/contract";
import { applyDesignRule, readRule, RESULT_BATCHES, RESULT_NOTICES, type ResultNotice } from "@/mocks/extras";
import { api, USE_MOCK } from "./api";
import { groupIntoBatches } from "./grouping";
import { remapToStoreSlots } from "./slotRemap";

export interface HomeData {
  today: TodayResponse;
  plan: PlanResponse;
  /** 서버에 아직 없는 결과 알림 (04-43, 04-44). 고정 샘플 모드에서만 채운다. */
  results: ResultNotice[];
  reviews: ReviewsResponse;
  calendar: CalendarResponse;
  settings: SettingsResponse;
}

const KEY = "dona.home.v3";

function readCache(): HomeData | undefined {
  if (typeof window === "undefined") return undefined;
  // 검토용 주소(?offline=1, ?fresh=1)에서는 저장해 둔 값을 쓰지 않는다.
  const q = new URLSearchParams(window.location.search);
  if (q.get("offline") === "1" || q.get("fresh") === "1") return undefined;
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as HomeData) : undefined;
  } catch {
    return undefined;
  }
}

async function load(): Promise<HomeData> {
  const [today, plan, reviews, calendar, settings] = await Promise.all([
    api.today(),
    api.plan(),
    api.reviews(),
    api.calendar(),
    api.settings(),
  ]);
  // 고정 샘플의 today는 화요일 하루뿐이다. 서버와 같은 규칙(lib/grouping.ts)으로 plan 응답에서 데모 주간 모든 날의 묶음을 만든다.
  // 결과 알림은 다음 주 묶음으로 덧붙인다. /dev에서 날짜를 옮겨 하루씩 볼 수 있다.
  const results = USE_MOCK ? RESULT_NOTICES : [];
  if (USE_MOCK) {
    // 예시 계획은 10:00, 14:00, 21:30 기준이라 가게 알림 시각으로 옮긴다 (서버는 이 시각으로 직접 계산한다).
    const moved = remapToStoreSlots(plan.plan_items, plan.notice_items, settings.settings);
    plan.plan_items = moved.plans;
    plan.notice_items = moved.notices;
    if (readRule() === "design") plan.plan_items = applyDesignRule(plan.plan_items, settings.settings);
    const batches = groupIntoBatches(plan.plan_items, plan.notice_items, settings.settings);
    for (const rb of remapToStoreSlots([], [], settings.settings, RESULT_BATCHES).batches) {
      // 같은 알림 시각이 있으면 그 묶음에 붙인다.
      const same = batches.find((b) => new Date(b.slot_at).getTime() === new Date(rb.slot_at).getTime());
      if (same) same.entries = [...same.entries, ...rb.entries];
      else batches.push(rb);
    }
    today.batches = batches.sort((a, b) => new Date(a.slot_at).getTime() - new Date(b.slot_at).getTime());
  }
  const data = { today, plan, reviews, calendar, settings, results };
  try {
    localStorage.setItem(KEY, JSON.stringify(data));
  } catch {
    /* 저장 공간이 없으면 다음에 다시 받는다 */
  }
  return data;
}

export function useHomeData() {
  return useQuery({
    queryKey: ["home"],
    queryFn: load,
    initialData: readCache,
    // 저장해 둔 값은 바로 보여 주고, 뒤에서 새 값을 받는다.
    initialDataUpdatedAt: 0,
    retry: 0,
  });
}
