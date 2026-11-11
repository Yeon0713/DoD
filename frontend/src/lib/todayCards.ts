// 오늘 화면과 잠금 화면 알림(04-23)이 같이 쓰는 카드 목록 만들기.
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
  total: number;
  done: number;
}

export function buildTodayCards(data: HomeData, now: Date, p: Prefs, store: Record<string, CardStatus>, focus?: string | null, drafts: Record<string, string> = {}): TodayCards {
  const queue = buildQueue(data.today, data.plan, now, data.results);
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
  const cards: CardView[] = [];
  for (const q of queue) {
    const c = toCard(q, ctx);
    if (!c) continue;
    cards.push(c);
    slotOf[c.id] = q.slotAt;
  }
  const open = cards.filter((c) => isOpen(store, c.id, now));
  // 검토용: ?card=카드id 를 붙이면 그 카드를 맨 앞으로 꺼낸다 (/dev 화면 바로 가기).
  const fi = focus ? open.findIndex((c) => c.id === focus) : -1;
  if (fi > 0) open.unshift(...open.splice(fi, 1));
  if (open.length === 0 && p.firstDayPending) {
    // 04-4f: 첫날 새 할 일이 없으면 답글 없는 좋은 리뷰부터 권한다.
    const basic = data.plan.plan_items.filter((x) => x.task_type === "REVISIT_REPLY" && x.revisit_class === "BASIC");
    if (basic.length) open.push(firstDayCard(basic[0].plan_id, basic.length));
  }
  return { cards, open, slotOf, total: Math.max(cards.length, open.length), done: cards.length - open.filter((c) => c.id !== "FIRST_DAY").length };
}
