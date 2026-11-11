// 홈, 지금 할 일, 잠금 화면 알림(06-23)이 같이 쓰는 카드 목록 만들기.
import { isOpen, type CardStatus } from "./cardState";
import { firstDayCard, toCard, type CardView } from "./cards";
import type { Prefs } from "./localStore";
import { buildQueue } from "./queue";
import type { HomeData } from "./useHomeData";

export interface TodayCards {
  cards: CardView[];
  open: CardView[];
  /** 카드 id → 그 카드가 온 알림 시각 */
  slotOf: Record<string, string>;
  /** 카드 id → 카드를 만들 때 지금으로 본 시각 (모아 보기에서는 알림 시각 5분 뒤, 아니면 지금) */
  momentOf: Record<string, string>;
  /** 카드 id → 그 카드가 다루는 계획 id들 (좋은 리뷰 묶음은 여러 개). 08 "오늘 함께 한 일"을 셀 때 쓴다 */
  plansOf: Record<string, string[]>;
  total: number;
  done: number;
}

/** 어떤 카드를 보여 줄지 (목업 검토용). all: 데모 한 주 카드를 모두, only: 그중 이 카드들만 (매장 시나리오) */
export interface CardScope {
  all?: boolean;
  only?: readonly string[];
}

/** 알림이 오고 5분 뒤. /dev 바로 가기(10:05, 14:05, 21:35)와 같은 때에 카드를 연 것으로 본다 */
const MOMENT_MS = 5 * 60 * 1000;

/** scope.all: 목업 모아 보기. 데모 한 주의 카드를 넣고, 카드마다 그 카드가 온 때를 지금으로 보고 만든다. 그래야 "내일부터 추워져요" 같은 글이 Figma와 같다. */
export function buildTodayCards(
  data: HomeData,
  now: Date,
  p: Prefs,
  store: Record<string, CardStatus>,
  focus?: string | null,
  drafts: Record<string, string> = {},
  scope: CardScope = {},
): TodayCards {
  const all = !!scope.all;
  const queue = buildQueue(data.today, data.plan, now, data.results, all);
  const ctx = {
    now,
    reviews: data.reviews.reviews,
    calendar: data.calendar.cells,
    settings: data.settings.settings,
    naverConnected: p.naverConnected,
    naverAuto: p.naverAuto,
    naverDeclined: p.naverDeclined,
    drafts,
  };
  const slotOf: Record<string, string> = {};
  const momentOf: Record<string, string> = {};
  const plansOf: Record<string, string[]> = {};
  const cards: CardView[] = [];
  for (const q of queue) {
    const at = all ? new Date(new Date(q.slotAt).getTime() + MOMENT_MS) : now;
    const c = toCard(q, all ? { ...ctx, now: at } : ctx);
    if (!c || (scope.only && !scope.only.includes(c.id))) continue;
    cards.push(c);
    slotOf[c.id] = q.slotAt;
    momentOf[c.id] = at.toISOString();
    plansOf[c.id] = q.group ? q.group.map((p) => p.plan_id) : q.plan ? [q.plan.plan_id] : [];
  }
  // 매장 시나리오는 한 주 이야기 순서(날짜)대로 놓고, 같은 날 안에서는 우선순위대로 둔다.
  if (scope.only) {
    const day = (c: CardView) => slotOf[c.id]?.slice(0, 10) ?? "";
    const rank = new Map(cards.map((c, i) => [c.id, i]));
    cards.sort((a, b) => day(a).localeCompare(day(b)) || rank.get(a.id)! - rank.get(b.id)!);
  }
  const open = cards.filter((c) => isOpen(store, c.id, now));
  // 검토용: /dev에서 고른 카드를 맨 앞으로 꺼낸다.
  const fi = focus ? open.findIndex((c) => c.id === focus) : -1;
  if (fi > 0) open.unshift(...open.splice(fi, 1));
  if (open.length === 0 && p.firstDayPending) {
    // 06-4f: 첫날 새 할 일이 없으면 답글 없는 좋은 리뷰부터 권한다.
    const basic = data.plan.plan_items.filter((x) => x.task_type === "REVISIT_REPLY" && x.revisit_class === "BASIC");
    if (basic.length) open.push(firstDayCard(basic[0].plan_id, basic.length));
  }
  return { cards, open, slotOf, momentOf, plansOf, total: Math.max(cards.length, open.length), done: cards.length - open.filter((c) => c.id !== "FIRST_DAY").length };
}

/** 08 "오늘 함께 한 일"의 네 가지 */
export type DoneKind = "reply" | "check" | "menu" | "poster";
export const DONE_KINDS: DoneKind[] = ["reply", "check", "menu", "poster"];

/** 계획 id 앞부분(task_type)으로 어떤 일인지 정한다. 알림만 확인한 카드(미리 보기, 매출, 결과 알림)는 계획이 없어서 세지 않는다. */
function kindOf(planId: string): DoneKind | null {
  const type = planId.split(":")[0];
  if (type === "REVISIT_REPLY" || type === "REORDER_NUDGE") return "reply";
  if (type === "REVIEW_FIX") return "check";
  if (type === "MENU_ORDER") return "menu";
  if (type === "POSTER") return "poster";
  return null;
}

/**
 * 끝낸 카드로 오늘 함께 한 일을 센다 (Figma 08-0 규칙).
 * 같은 계획의 승인 카드와 실행 카드를 둘 다 끝내도 한 번만 센다. 좋은 리뷰 묶음은 답글 수만큼 센다.
 */
export function countDone(view: TodayCards, doneIds: string[]): Record<DoneKind, number> {
  const plans = new Set(doneIds.flatMap((id) => view.plansOf[id] ?? []));
  const out: Record<DoneKind, number> = { reply: 0, check: 0, menu: 0, poster: 0 };
  for (const id of plans) {
    const k = kindOf(id);
    if (k) out[k] += 1;
  }
  return out;
}
