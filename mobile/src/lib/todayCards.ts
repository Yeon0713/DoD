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
  total: number;
  done: number;
}

/** 알림이 오고 5분 뒤. /dev 바로 가기(10:05, 14:05, 21:35)와 같은 때에 카드를 연 것으로 본다 */
const MOMENT_MS = 5 * 60 * 1000;

/** all: 목업 모아 보기. 데모 한 주의 카드를 모두 넣고, 카드마다 그 카드가 온 때를 지금으로 보고 만든다. 그래야 "내일부터 추워져요" 같은 글이 Figma와 같다. */
export function buildTodayCards(
  data: HomeData,
  now: Date,
  p: Prefs,
  store: Record<string, CardStatus>,
  focus?: string | null,
  drafts: Record<string, string> = {},
  all = false,
): TodayCards {
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
  const cards: CardView[] = [];
  for (const q of queue) {
    const at = all ? new Date(new Date(q.slotAt).getTime() + MOMENT_MS) : now;
    const c = toCard(q, all ? { ...ctx, now: at } : ctx);
    if (!c) continue;
    cards.push(c);
    slotOf[c.id] = q.slotAt;
    momentOf[c.id] = at.toISOString();
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
  return { cards, open, slotOf, momentOf, total: Math.max(cards.length, open.length), done: cards.length - open.filter((c) => c.id !== "FIRST_DAY").length };
}
