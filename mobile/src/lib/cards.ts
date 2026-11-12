// 줄 세운 항목(QueueEntry)을 화면 카드 한 장(CardView)으로 바꾼다.
// 카드 모양과 문구는 Figma 06 시안(06-4, 06-10, 06-12, 06-13, 06-14, 06-15, 06-16, 06-17, 06-31, 06-39, 06-41)을 따른다.
import type { IconName } from "@/components/icons/Icon";
import type { CalendarCell, ComplaintType, PlanItem, Review, StoreSettings } from "@/types/contract";
import { LAST_WEEK_LINE, draftFor, storeMenus } from "@/mocks/extras";
import { USE_MOCK } from "./api";
import { COMPLAINT_FOUND, COMPLAINT_ICON, COMPLAINT_REPEAT, COMPLAINT_SHORT, COMPLAINT_TITLE, PLATFORM_KO } from "./labels";
import type { QueueEntry } from "./queue";
import type { PosterProps } from "@/components/poster/PosterCard";
import { dayChange, type DayKind } from "./calendarDay";
import { menuOrderFor } from "./menuOrder";
import { defaultHeadline, readKept } from "./poster";
import { addDays, clockKo, isWeekend, monthDay, relativeDay, weekdayName } from "./time";

export type Tone = "urgent" | "brand" | "calm" | "done";
export type Donna = "b1-0" | "b1-1" | "b1-2" | "b2-0" | "b2-1" | "b3-0" | "b3-1" | "b3-2" | "b4-0" | "b4-1" | "b4-2"
  | "question"
  | "q-think"
  | "q-arms"
  | "q-scratch"
  | "q-clipboard"
  | "q-laptop"
  | "q-shrug";

export type CardBlock =
  | { type: "stars"; rating: number }
  | { type: "quote"; text: string }
  /** 06-4, 06-39: 손님 리뷰 말풍선. 카드에서는 2줄까지 보이고 "더 보기"로 답글 화면(href)에 간다. */
  | { type: "review"; rating: number; meta: string; text: string; photos: string[]; href: string }
  | { type: "iconLine"; icons: IconName[]; text: string }
  | { type: "text"; text: string }
  | { type: "iconRow"; icon: IconName; count: number }
  /** 월~일 일곱 칸 중 단골이 주문하는 요일을 칠한다 (04-11). day는 0=일요일 */
  | { type: "weekStrip"; day: number }
  | { type: "bars"; rows: { label: string; value: string; percent: number; accent?: boolean }[] }
  /** 05-12n: 바뀔 메뉴판 순서를 카드에서 바로 (위 3개). from이 있으면 그 칸에서 올라온 메뉴 */
  | { type: "menuPreview"; header: string; rows: { name: string; from?: number }[] }
  /** 06-31, 06-31n, 06-34: 만들어 둔 포스터를 카드 가운데에 크게 (폭 210) */
  | { type: "poster"; poster: PosterProps };

export type CardAction =
  /** done: 이 길로 가면 카드도 끝난 것으로 친다 (보기만 하면 되는 카드. 예: 이번 주 미리 보기) */
  | { label: string; href: string; done?: boolean }
  | {
      label: string;
      action: "done" | "snooze";
      /** 누른 뒤 위에 잠깐 띄울 띠 */
      toast?: { title: string; sub?: string };
      /** "제가 직접 할게요": 다음부터는 네이버 연결을 권하지 않는다 */
      declineNaver?: boolean;
      /** 05-4: 카드에서 바로 답글 달기. now면 지금 올리고, schedule이면 실행 시각에 올리도록 맡긴다. */
      reply?: { planId: string; text: string; mode: "now" | "schedule"; platform: string; when: string };
      /** 끝내기 전에 올릴 답글들(plan_id). 다 올라가야 카드가 끝난다. */
      publish?: string[];
    };

export interface CardView {
  id: string;
  tone: Tone;
  /** 06 포스터 카드처럼 띠가 없는 카드도 있다. */
  pill?: { icon: IconName; text: string };
  /** 06-4, 06-39: "긴급" 띠를 진하게 칠하고 카드에 2px 빨간 테두리를 두른다. */
  urgent?: boolean;
  /** 06-12: 제목 앞 아이콘 (추워지는 날 온도계) */
  titleIcon?: IconName;
  title: string;
  /** 06-31: 제목 아래 작은 글씨 ("목요일 저녁 축구 경기") */
  sub?: string;
  /** 06-31: 도나 위에 작게 쓰는 한 줄 ("가게 앞에도 붙일 수 있어요!") */
  aboveDonna?: string;
  blocks: CardBlock[];
  donna: { img: Donna; text: string };
  primary: CardAction;
  secondary?: CardAction;
  /** 05-4: 카드 아래에 도나가 써 둔 답글을 바로 보여 준다. 있으면 도나 한마디 대신 쓴다. */
  draft?: { text: string; editHref: string; img: Donna };
}

export interface CardContext {
  now: Date;
  reviews: Review[];
  calendar: CalendarCell[];
  settings: StoreSettings;
  /** 네이버 플레이스를 연결했는지. 서버 설정에 아직 없어서 이 기기 설정을 쓴다. */
  naverConnected: boolean;
  /** 메뉴 순서 알아서 바꾸기 (04-55, 04-58) */
  naverAuto: boolean;
  /** 04-50에서 "제가 직접 할게요"를 골랐는지. 그 뒤로는 04-12처럼 직접 바꾸는 카드만 보여 준다. */
  naverDeclined: boolean;
  /** 사장님이 고쳐 쓴 답글 (plan_id → 글) */
  drafts: Record<string, string>;
}

const LATER: CardAction = { label: "나중에 할게요", action: "snooze" };

// ---------- 달력에서 그 날의 일을 읽는 도우미 ----------

// dayChange, DayKind는 lib/calendarDay.ts로 옮겼다 (cards ↔ menuOrder 서로 부르는 고리를 끊으려고). 쓰던 곳은 그대로 여기서 가져간다.
export { dayChange, type DayKind } from "./calendarDay";

export function eventName(cells: CalendarCell[], refId: string, kind: "GAME" | "EVENT"): string {
  const text = cells.find((c) => c.reasons.some((r) => r.ref_id === refId))?.reason_text ?? "";
  if (kind === "GAME") return text.match(/(축구|야구|농구|배구|e스포츠) 경기/)?.[0] ?? "경기";
  return text.match(/(지역 축제|대학 축제|마라톤|지역 행사)/)?.[0] ?? "지역 행사";
}

export function eventDays(cells: CalendarCell[], refId: string): string[] {
  return [...new Set(cells.filter((c) => c.reasons.some((r) => r.ref_id === refId)).map((c) => c.date))].sort();
}

const DAYPART_KO = { LUNCH: "점심", DINNER: "저녁", NIGHT: "밤" } as const;

function busyDaypart(cells: CalendarCell[], date: string, refId: string): string {
  const c = cells.find((x) => x.date === date && x.signal === "HIGH" && x.reasons.some((r) => r.ref_id === refId));
  return c ? DAYPART_KO[c.daypart] : "";
}

/** 포스터와 메뉴판 카드에 쓰는 "목요일 축구 경기", "주말 지역 축제" 같은 이름과 날짜 줄 */
export function happening(cells: CalendarCell[], p: PlanItem) {
  const kind = p.basis.kind === "GAME" || p.basis.kind === "EVENT" ? p.basis.kind : null;
  const refId = p.basis.ref_id;
  const days = kind ? eventDays(cells, refId) : [p.target_date];
  const first = days[0] ?? p.target_date;
  const name = kind ? eventName(cells, refId, kind) : "";
  const weekend = days.length > 1 && days.every(isWeekend);
  const label = weekend ? `주말 ${name}` : `${weekdayName(first)} ${name}`;
  const dateLine = weekend
    ? `${monthDay(first)}, ${Number(days[days.length - 1].slice(8))}일 ${days.map((d) => weekdayName(d)).join(" ")}`
    : `${monthDay(first)} ${weekdayName(first)} ${busyDaypart(cells, first, refId)}`.trim();
  const shortLine = weekend ? `${monthDay(first)}, ${Number(days[days.length - 1].slice(8))}일 주말` : dateLine;
  return { kind, label, dateLine, shortLine, icon: (kind === "GAME" ? "ball" : "tent") as IconName };
}

// ---------- 카드 종류별 ----------

/** 리뷰 글에서 더 구체적인 말을 찾으면 그것으로 제목을 쓴다. 예: "국물이 짜다는 리뷰가 왔어요" (04-39) */
function complaintTitle(type: ComplaintType, text: string): string {
  if (type === "TASTE") {
    if (/짜|짰|짭/.test(text)) return `${/국물/.test(text) ? "국물이" : "간이"} 짜다는 리뷰예요`;
    if (/싱거/.test(text)) return "간이 싱겁다는 리뷰예요";
  }
  return COMPLAINT_TITLE[type];
}

function seoulHour(iso: string) {
  return new Date(new Date(iso).getTime() + 9 * 3600e3).getUTCHours();
}
function seoulWeekday(iso: string) {
  return new Date(new Date(iso).getTime() + 9 * 3600e3).getUTCDay();
}

function quickReply(q: QueueEntry, p: PlanItem, ctx: CardContext): CardView {
  const r = ctx.reviews.find((x) => x.review_id === p.basis.ref_id);
  const type: ComplaintType = r?.label?.complaint_types[0] ?? "SERVICE";
  const group = r?.label?.complaint_groups[0] ?? "SERVICE";
  const blocks: CardBlock[] = [];
  if (r) {
    // 06-4는 별점만, 06-39처럼 배달앱 리뷰면 "2점, 배달의민족"
    const meta = r.platform === "NAVER" ? `${r.rating}점` : `${r.rating}점, ${PLATFORM_KO[r.platform]}`;
    blocks.push({ type: "review", rating: r.rating, meta, text: r.text, photos: r.photos ?? [], href: `/reply/${encodeURIComponent(p.plan_id)}` });
  }
  return {
    id: q.cardId,
    tone: "urgent",
    urgent: true,
    pill: { icon: COMPLAINT_ICON[group], text: "긴급" },
    title: complaintTitle(type, r?.text ?? ""),
    blocks,
    donna: { img: "b3-2", text: "사과 답글을\n미리 써 뒀어요" },
    ...replyDraft(p, r, ctx),
    secondary: LATER,
  };
}

/** 05-4, 05-11, 05-35, 05-39: 답글 초안을 카드에 보여 주고 주 버튼으로 바로 단다. */
function replyDraft(p: PlanItem, r: Review | undefined, ctx: CardContext): Pick<CardView, "primary" | "draft"> {
  // 빈 글이 저장돼 있으면 도나 초안을 쓴다.
  const text = ctx.drafts[p.plan_id]?.trim() ? ctx.drafts[p.plan_id] : draftFor(p, r);
  const exec = p.execute_at ?? p.approval_request_at;
  // 불만 답글은 늘 지금 올린다. 단골 답글만 실행 시각(주문하는 날)에 올리도록 맡긴다.
  const later = p.revisit_class !== "QUICK" && new Date(exec).getTime() > ctx.now.getTime();
  return {
    draft: { text, editHref: `/reply/${encodeURIComponent(p.plan_id)}/edit`, img: p.revisit_class === "QUICK" ? "b3-2" : "b1-1" },
    primary: {
      label: "이대로 답글 달기",
      action: "done",
      reply: { planId: p.plan_id, text, mode: later ? "schedule" : "now", platform: r ? PLATFORM_KO[r.platform] : "배달앱", when: `${relativeDay(exec, ctx.now)} ${clockKo(exec)}` },
    },
  };
}

function regularReply(q: QueueEntry, p: PlanItem, ctx: CardContext): CardView {
  const monthly = p.revisit_class === "MONTHLY";
  const r = ctx.reviews.find((x) => x.review_id === p.basis.ref_id);
  const wd = r ? weekdayName(r.written_at) : "";
  const part = r && seoulHour(r.written_at) < 15 ? "점심" : "저녁";
  const exec = p.execute_at ?? p.approval_request_at;
  const href = `/reply/${encodeURIComponent(p.plan_id)}`;
  if (q.notifyKind === "EXECUTE_REMINDER") {
    // 04-32 주간 단골, 04-38 월간 단골 실행 알림
    return {
      id: q.cardId,
      tone: "done",
      pill: { icon: "clock", text: "지금 할 시간" },
      title: monthly ? "한 달 단골 손님께\n답글을 올릴 시간이에요" : "단골 손님께\n답글을 올릴 시간이에요",
      blocks: [
        { type: "iconLine", icons: ["heart"], text: monthly ? "한 달에 한 번 오는 단골 손님" : `매주 ${wd} ${part} 단골 손님` },
        { type: "text", text: monthly ? "다음 주문 전에 볼 수 있어요" : `오늘 ${part} 주문 전에 볼 수 있어요` },
      ],
      donna: { img: "b4-1", text: "답글을 미리\n써 뒀어요" },
      primary: { label: "답글 올리기", href },
      secondary: LATER,
    };
  }
  // 04-11 주간 단골, 04-35 월간 단골 승인 요청
  const sentences = (r?.text ?? "").split(/(?<=[.!?])\s+/).filter(Boolean);
  const quote = sentences.find((t) => /한 달|매주|마다/.test(t)) ?? sentences[sentences.length - 1];
  return {
    id: q.cardId,
    tone: "brand",
    pill: { icon: "heart", text: "단골 손님" },
    title: monthly ? "한 달에 한 번\n주문하는 단골이에요" : `매주 ${wd} ${part}에\n주문하는 단골이에요`,
    blocks: monthly
      ? [
          ...(quote ? [{ type: "quote", text: quote } as CardBlock] : []),
          { type: "text", text: `${relativeDay(exec, ctx.now)} ${clockKo(exec)}에 감사 답글을 올려요` },
        ]
      : [
          ...(r ? [{ type: "weekStrip", day: seoulWeekday(r.written_at) } as CardBlock] : []),
          { type: "text", text: `${relativeDay(exec, ctx.now)} 주문 전에 감사 답글을 남겨요` },
        ],
    donna: { img: "b1-1", text: "감사 답글을\n미리 써 뒀어요" },
    ...replyDraft(p, r, ctx),
    secondary: LATER,
  };
}

function basicReplies(q: QueueEntry, ctx: CardContext): CardView {
  const items = q.group ?? [];
  const n = items.length;
  const exec = items[0]?.execute_at;
  const when = exec ? `${relativeDay(exec, ctx.now) === "오늘" ? "오늘" : relativeDay(exec, ctx.now)} ${clockKo(exec)}` : "토요일 오전";
  const execute = q.notifyKind === "EXECUTE_REMINDER";
  return {
    id: q.cardId,
    tone: execute ? "done" : "brand",
    pill: execute ? { icon: "clock", text: "지금 할 시간" } : { icon: "messages", text: `좋은 리뷰 ${n}개` },
    title: execute ? `좋은 리뷰 ${n}개에\n답글을 올릴 시간이에요` : `좋은 리뷰 ${n}개에\n한 번에 답글 달아요`,
    blocks: [
      { type: "iconRow", icon: "message", count: n },
      { type: "text", text: execute ? "주말 주문 전에 손님이 봐요" : `주말 주문 전에 손님이 보게\n${when}에 올려요` },
    ],
    donna: { img: "b1-1", text: execute ? `답글 ${n}개를\n써 뒀어요` : `감사 답글 ${n}개를\n써 뒀어요` },
    primary: execute
      ? {
          label: `${n}개 모두 올리기`,
          action: "done",
          publish: items.map((p) => p.plan_id),
          toast: { title: `답글 ${n}개를 올렸어요`, sub: "배달앱과 네이버에서 볼 수 있어요" },
        }
      : { label: `답글 ${n}개 보기`, href: `/reply/batch/${encodeURIComponent(items[0]?.plan_id ?? "")}` },
    secondary: LATER,
  };
}

function reviewFix(q: QueueEntry, p: PlanItem, ctx: CardContext): CardView {
  const from = addDays(p.target_date, -7);
  const recent = ctx.reviews.filter((r) => r.label?.complaint_types.length && r.written_at.slice(0, 10) > from && r.written_at.slice(0, 10) <= p.target_date);
  const counts = new Map<ComplaintType, number>();
  for (const r of recent) for (const t of r.label!.complaint_types) counts.set(t, (counts.get(t) ?? 0) + 1);
  const [type, count] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0] ?? (["SERVICE", 3] as [ComplaintType, number]);
  const group = recent.find((r) => r.label!.complaint_types.includes(type))?.label?.complaint_groups[0] ?? "SERVICE";
  const by = p.deadline_at ?? `${addDays(p.target_date, 1)}T12:00:00+09:00`;
  return {
    id: q.cardId,
    tone: "urgent",
    pill: { icon: "repeat", text: `같은 불만 ${count}번` },
    title: `${COMPLAINT_REPEAT[type]} 리뷰가\n일주일에 ${count}번 왔어요`,
    blocks: [
      { type: "iconLine", icons: Array.from({ length: Math.min(count, 5) }, () => COMPLAINT_ICON[group]), text: COMPLAINT_SHORT[type] },
      { type: "text", text: COMPLAINT_FOUND[type] },
    ],
    // 06 B: 가르치지 않고 사실만 모아 보여 준다. 판단은 사장님이 한다.
    donna: { img: "b2-0", text: "손님 리뷰를\n모아 뒀어요" },
    primary: { label: "리뷰 보기", href: `/check/${encodeURIComponent(p.plan_id)}?by=${encodeURIComponent(by)}` },
    secondary: LATER,
  };
}

export function menuWhat(change: DayKind | null, cells: CalendarCell[]) {
  const up = "arrowUp" as IconName;
  if (!change) return { title: "메뉴판 순서를\n바꿀 때예요", line: "잘 나가는 메뉴를\n메뉴판 맨 위로", short: "바꿀 시간이에요", icon: "list" as IconName, arrow: up };
  if (change.tag === "SEASON") return { title: "추워지는 날이에요", line: "따뜻한 국물 메뉴를\n메뉴판 맨 위로", short: "바꿀 시간이에요", icon: "soup" as IconName, arrow: up };
  const name = change.tag === "GAME" ? "경기" : "축제";
  if (!change.on) return { title: `${name}가 끝나면\n메뉴판을 원래대로`, line: `${name} 메뉴를 원래 자리로`, short: "원래대로 바꿔요", icon: "list" as IconName, arrow: "arrowDown" as IconName };
  const days = eventDays(cells, change.refId);
  const when = days.length > 1 && days.every(isWeekend) ? "주말엔" : `${weekdayName(days[0])}엔`;
  return {
    title: `${when} ${name} 메뉴를\n맨 위로`,
    line: change.tag === "GAME" ? "경기 보며 먹기 좋은 메뉴를\n메뉴판 맨 위로" : "축제 손님이 찾는 메뉴를\n메뉴판 맨 위로",
    short: `${name} 맞춤으로`,
    icon: "list" as IconName,
    arrow: up,
  };
}

function menuOrder(q: QueueEntry, p: PlanItem, ctx: CardContext): CardView {
  const change = dayChange(ctx.calendar, p.target_date);
  const what = menuWhat(change, ctx.calendar);
  if (q.notifyKind === "EXECUTE_REMINDER" && ctx.naverConnected && ctx.naverAuto) {
    // 04-56: 네이버를 연결하고 "알아서 바꾸기"를 켰으면 도나가 바꾼 뒤 알리기만 한다.
    const exec = p.execute_at ?? p.target_date;
    return {
      id: q.cardId,
      tone: "done",
      pill: { icon: "check", text: "바꿔 뒀어요" },
      // short가 "원래대로 바꿔요"면 "원래대로"만 쓴다 ("원래대로 바꿔요 바꿨어요"가 되지 않게)
      title: `메뉴판을\n${what.short === "바꿀 시간이에요" ? "계절 맞춤으로" : what.short.replace(/ 바꿔요$/, "")} 바꿨어요`,
      blocks: [
        { type: "iconLine", icons: [what.arrow, what.icon], text: what.line.replace("메뉴판 맨 위로", "맨 위로 올렸어요") },
        { type: "text", text: `${weekdayName(exec)} ${clockKo(exec)}에 도나가 바꿨어요` },
      ],
      donna: { img: "b1-1", text: "확인만\n해 주세요" },
      primary: { label: "확인했어요", action: "done" },
      secondary: { label: "원래대로 되돌리기", href: `/menu-order/${encodeURIComponent(p.plan_id)}?step=revert` },
    };
  }
  if (q.notifyKind === "EXECUTE_REMINDER") {
    const shortTitle = what.short === "바꿀 시간이에요" ? "지금 메뉴판을\n바꿀 시간이에요" : `지금 메뉴판을\n${what.short}`;
    return {
      id: q.cardId,
      tone: "done",
      pill: { icon: "clock", text: "지금 할 시간" },
      title: shortTitle,
      blocks: [
        { type: "iconLine", icons: [what.arrow, what.icon], text: what.line },
        {
          type: "text",
          text: ctx.naverConnected ? "네이버는 도나가 바꿔 뒀어요\n배달앱과 가게 메뉴판만 바꿔 주세요" : "네이버와 배달앱 메뉴판에서\n순서를 바꿔 주세요",
        },
      ],
      donna: { img: "b4-1", text: "다 하시면\n눌러 주세요" },
      primary: { label: "다 했어요", action: "done" },
      secondary: LATER,
    };
  }
  const exec = p.execute_at ?? p.target_date;
  const title = change?.tag === "SEASON" && change.on ? `${relativeDay(exec, ctx.now)}부터 추워져요` : what.title;
  // 06-12: 추워지는 날은 제목 앞에 온도계
  const seasonIcon: IconName | undefined = change?.tag === "SEASON" && change.on ? "thermometerDown" : undefined;
  const href = `/menu-order/${encodeURIComponent(p.plan_id)}`;
  const mo = menuOrderFor(p, ctx.calendar, ctx.settings.category);
  const naverHeader = ctx.naverConnected ? "네이버 플레이스 메뉴" : change?.on ? "바꿀 메뉴 순서" : "원래 순서로";
  const preview = (header: string): CardBlock => ({
    type: "menuPreview",
    header,
    rows: mo.order.slice(0, 3).map((m, i) => ({ name: m.name, from: i === 0 && mo.tag && mo.from > 1 ? mo.from : undefined })),
  });
  const when = `${relativeDay(exec, ctx.now)} ${clockKo(exec)}`;
  if (!ctx.naverConnected && ctx.naverDeclined) {
    // 04-12, 04-27, 04-28, 04-36, 04-42: 사장님이 직접 바꾸기로 했으면 바꿀 때를 알려 주기만 한다.
    return {
      id: q.cardId,
      tone: "brand",
      pill: { icon: "list", text: "메뉴판" },
      titleIcon: seasonIcon,
      title,
      blocks: [
        preview(naverHeader),
        { type: "text", text: `${when}에 바꾸면 돼요` },
      ],
      donna: { img: "b2-0", text: "바꿀 때 다시\n알려 드릴게요" },
      primary: { label: "좋아요", action: "done" },
      secondary: LATER,
    };
  }
  if (ctx.naverConnected && ctx.naverAuto) {
    return {
      id: q.cardId,
      tone: "brand",
      pill: { icon: "list", text: "메뉴판" },
      titleIcon: seasonIcon,
      title,
      blocks: [
        preview(naverHeader),
        { type: "text", text: `${when}에 도나가 바꿔 둘게요` },
      ],
      donna: { img: "b2-0", text: "바꾼 뒤에\n알려 드릴게요" },
      primary: { label: "좋아요", action: "done" },
      secondary: { label: "이번엔 안 할래요", action: "done" },
    };
  }
  if (!ctx.naverConnected) {
    // 04-50: 네이버를 연결하지 않았으면 도나에게 맡기는 길을 먼저 보여 준다.
    return {
      id: q.cardId,
      tone: "brand",
      pill: { icon: "list", text: "메뉴판" },
      titleIcon: seasonIcon,
      title,
      blocks: [
        preview(naverHeader),
        { type: "text", text: "네이버 플레이스를 연결하면\n도나가 대신 바꿔 드려요" },
      ],
      donna: { img: "b1-1", text: "제가 바꿔\n드릴까요?" },
      primary: { label: "도나에게 맡기기", href: `/naver/connect?plan=${encodeURIComponent(p.plan_id)}` },
      secondary: { label: "제가 직접 할게요", action: "done", declineNaver: true },
    };
  }
  return {
    id: q.cardId,
    tone: "brand",
    pill: { icon: "list", text: "메뉴판" },
    titleIcon: seasonIcon,
    title,
    blocks: [
      preview(naverHeader),
      { type: "text", text: `${when}에 바꿔 둘게요` },
    ],
    donna: { img: "b2-0", text: "가격과 사진은\n그대로 둬요" },
    primary: { label: "네이버에 바꿔 두기", href: `${href}?apply=1` },
    secondary: LATER,
  };
}

/** 만들어 둔 포스터(없으면 기본 포스터)를 카드 썸네일로 */
function posterOf(p: PlanItem, h: ReturnType<typeof happening>, ctx: CardContext): PosterProps {
  const kept = readKept(ctx.drafts, `poster:${p.plan_id}`);
  const menus = storeMenus(ctx.settings.category).map((m) => m.name);
  return {
    menu: menus[kept?.menuIdx ?? 0],
    dateLine: h.shortLine,
    icon: h.icon,
    headline: kept?.headline ?? defaultHeadline(h, ctx.settings),
    store: kept?.storeLine ?? ctx.settings.name.replace(/\s*\(.*\)\s*/g, "").trim(),
    theme: kept?.theme ?? "dark",
  };
}

/** "목요일 저녁 축구 경기", "이번 주말 지역 축제" (06-31 제목 아래 작은 글씨) */
function posterWhen(p: PlanItem, h: ReturnType<typeof happening>, ctx: CardContext): string {
  const days = h.kind ? eventDays(ctx.calendar, p.basis.ref_id) : [p.target_date];
  const name = h.kind ? eventName(ctx.calendar, p.basis.ref_id, h.kind) : "";
  // 행사나 경기 없이 서버가 매주 만드는 주말 포스터: 요일만 쓰면 무슨 포스터인지 알 수 없다
  if (!h.kind) return "이번 주말 손님맞이";
  if (days.length > 1 && days.every(isWeekend)) return `이번 주말 ${name}`;
  return `${weekdayName(days[0])} ${busyDaypart(ctx.calendar, days[0], p.basis.ref_id)} ${name}`.replace(/\s+/g, " ").trim();
}

function poster(q: QueueEntry, p: PlanItem, ctx: CardContext): CardView {
  const h = happening(ctx.calendar, p);
  const kept = !!readKept(ctx.drafts, `poster:${p.plan_id}`);
  // 실제 서버에서는 이 기기에서 포스터를 만든 적이 있을 때만 "미리 만들어 뒀어요"라고 한다.
  // 승인 요청 날을 놓쳤거나 오늘 가입한 사장님은 만든 적이 없으니 만들기부터 보여 준다.
  // 고정 샘플은 전날 만들어 둔 것으로 보고, 실행 알림이면 바로 올리기를 보여 준다 (발표 시나리오).
  const made = kept || (USE_MOCK && q.notifyKind === "EXECUTE_REMINDER");
  if (made) {
    // 06-31, 06-31n, 06-34: 띠 없이 포스터를 크게. 올리고 싶어지게 포스터가 주인공이다.
    return {
      id: q.cardId,
      tone: q.notifyKind === "EXECUTE_REMINDER" ? "done" : "brand",
      title: "포스터 올릴 시간이에요",
      sub: posterWhen(p, h, ctx),
      blocks: [{ type: "poster", poster: posterOf(p, h, ctx) }],
      aboveDonna: "가게 앞에도 붙일 수 있어요!",
      donna: { img: "b4-1", text: "포스터는 미리 만들어 뒀어요" },
      primary: { label: "인스타에 올리기", href: `/poster/${encodeURIComponent(p.plan_id)}?step=share` },
      secondary: LATER,
    };
  }
  // 06-13, 06-26: 아직 포스터를 안 만들었으면 만들기부터
  return {
    id: q.cardId,
    tone: "brand",
    pill: { icon: "image", text: "인스타 포스터" },
    title: `${h.kind ? h.label : "이번 주말"}\n포스터를 만들어 드릴게요`,
    blocks: [
      { type: "iconLine", icons: [h.icon], text: h.dateLine },
      { type: "text", text: "인스타에 올리고 가게 앞에도 붙여요" },
    ],
    donna: { img: "b3-2", text: "메뉴 사진만\n골라 주세요" },
    primary: { label: "포스터 만들기", href: `/poster/${encodeURIComponent(p.plan_id)}` },
    secondary: LATER,
  };
}

function reorderNudge(q: QueueEntry, p: PlanItem): CardView {
  return {
    id: q.cardId,
    tone: q.notifyKind === "EXECUTE_REMINDER" ? "done" : "brand",
    pill: q.notifyKind === "EXECUTE_REMINDER" ? { icon: "clock", text: "지금 할 시간" } : { icon: "heart", text: "단골 손님" },
    title: "한 달 단골 손님이\n다시 주문할 때예요",
    blocks: [{ type: "text", text: "이번 주말 식사로 우리 가게를\n떠올리게 인사를 보내요" }],
    donna: { img: "b1-1", text: "인사말을\n미리 써 뒀어요" },
    primary: { label: "인사말 보기", href: `/reply/${encodeURIComponent(p.plan_id)}` },
    secondary: LATER,
  };
}

function weeklyPreview(q: QueueEntry, ctx: CardContext): CardView {
  const cells = ctx.calendar;
  const lines: CardBlock[] = [];
  const seasonDay = cells.find((c) => c.reasons.some((r) => r.tag === "SEASON"))?.date;
  if (seasonDay) lines.push({ type: "iconLine", icons: ["thermometerDown"], text: `${weekdayName(seasonDay)}부터 추워져요` });
  const seen = new Set<string>();
  for (const c of cells) {
    for (const r of c.reasons) {
      if ((r.tag !== "GAME" && r.tag !== "EVENT") || seen.has(r.ref_id)) continue;
      seen.add(r.ref_id);
      const days = eventDays(cells, r.ref_id);
      const name = eventName(cells, r.ref_id, r.tag);
      const when = days.length > 1 ? days.map((d) => weekdayName(d)).join(", ") : `${weekdayName(days[0])} ${busyDaypart(cells, days[0], r.ref_id)}`;
      lines.push({ type: "iconLine", icons: [r.tag === "GAME" ? "ball" : "tent"], text: `${when.trim()} ${name}` });
    }
  }
  const busy = lines.length;
  return {
    id: q.cardId,
    tone: "calm",
    pill: { icon: "calendar", text: "이번 주 미리 보기" },
    title: busy ? `이번 주에\n바쁜 때가 ${busy}번 있어요` : "이번 주는\n평소와 같아요",
    blocks: lines,
    // 04-16: 지난주 결과 한 줄. 서버 결과 알림이 생기기 전에는 고정 샘플에서만 보여 준다.
    donna: { img: "b2-1", text: USE_MOCK ? LAST_WEEK_LINE : "이번 주도\n같이 준비해요" },
    primary: { label: "이번 주 보기", href: "/week", done: true },
    secondary: { label: "나중에 볼게요", action: "snooze" },
  };
}

function salesNotice(q: QueueEntry): CardView {
  const text = q.notice?.text ?? "";
  const pct = Number(text.match(/(\d+)%/)?.[1] ?? 0);
  const more = !/적었/.test(text);
  const part = text.match(/(점심|저녁|야간|밤)/)?.[1] ?? "점심";
  return {
    id: q.cardId,
    tone: "calm",
    pill: { icon: "trendUp", text: "알려 드려요" },
    title: `어제 ${part} 매출이\n평소보다 ${more ? "많았어요" : "적었어요"}`,
    blocks: [
      {
        type: "bars",
        rows: [
          { label: "평소", value: "기준", percent: 100 / (1 + pct / 100) },
          { label: `어제 ${part}`, value: `${pct}% ${more ? "많음" : "적음"}`, percent: 100, accent: true },
        ],
      },
      { type: "text", text: "달력에 없던 일이었어요" },
    ],
    donna: { img: "b1-2", text: "다음 달력에\n참고할게요" },
    primary: { label: "확인했어요", action: "done" },
  };
}

function resultCard(q: QueueEntry): CardView {
  const r = q.result!;
  if (r.kind === "REPLY_RESULT") {
    return {
      id: q.cardId,
      tone: "calm",
      pill: { icon: "repeat", text: "답글 효과" },
      title: `답글 단 손님 ${r.data.after}분이\n다시 주문했어요`,
      blocks: [
        {
          type: "bars",
          rows: [
            { label: "토요일에 답글 단 손님", value: `${r.data.before}분`, percent: 100 },
            { label: "주말에 다시 주문", value: `${r.data.after}분`, percent: (r.data.after / r.data.before) * 100, accent: true },
          ],
        },
        { type: "text", text: "답글을 보고 다시 찾아 주셨어요" },
      ],
      donna: { img: "b1-2", text: "이번 토요일에도\n답글을 써 둘게요" },
      primary: { label: "확인했어요", action: "done" },
    };
  }
  const type = r.data.label as ComplaintType;
  return {
    id: q.cardId,
    tone: "done",
    pill: { icon: "check", text: "좋아졌어요" },
    title: `${COMPLAINT_REPEAT[type] ?? "같은 불만"} 리뷰가\n줄었어요`,
    blocks: [
      {
        type: "bars",
        rows: [
          { label: "점검 전 일주일", value: `${r.data.before}번`, percent: 100 },
          { label: "점검 후 일주일", value: `${r.data.after}번`, percent: r.data.before ? (r.data.after / r.data.before) * 100 : 0, accent: true },
        ],
      },
      { type: "text", text: `${r.data.since ? monthDay(r.data.since) : "점검"}에 점검한 뒤로\n한 번도 없었어요` },
    ],
    donna: { img: "b1-2", text: "같은 말이 또 나오면\n바로 알려 드릴게요" },
    primary: { label: "확인했어요", action: "done" },
  };
}

/** 04-4f: 처음 쓰는 날 새 할 일이 없을 때. 답글 없는 좋은 리뷰를 먼저 권한다. */
export function firstDayCard(basicPlanId: string | undefined, count: number): CardView {
  return {
    id: "FIRST_DAY",
    tone: "brand",
    pill: { icon: "messages", text: "첫날" },
    title: `답글 없는 지난 리뷰\n${count}개를 찾았어요`,
    blocks: [
      { type: "iconRow", icon: "message", count },
      { type: "text", text: "첫 답글부터 같이 해 봐요" },
    ],
    donna: { img: "b1-1", text: `감사 답글 ${count}개를\n써 뒀어요` },
    primary: { label: `답글 ${count}개 보기`, href: basicPlanId ? `/reply/batch/${encodeURIComponent(basicPlanId)}` : "/" },
    secondary: { label: "나중에 할게요", action: "done" },
  };
}

export function toCard(q: QueueEntry, ctx: CardContext): CardView | null {
  if (q.result) return resultCard(q);
  if (q.notice) return q.notice.kind === "WEEKLY_PREVIEW" ? weeklyPreview(q, ctx) : salesNotice(q);
  const p = q.plan;
  if (!p) return null;
  switch (p.task_type) {
    case "REVISIT_REPLY":
      if (p.revisit_class === "BASIC") return basicReplies(q, ctx);
      if (p.revisit_class === "QUICK") return quickReply(q, p, ctx);
      return regularReply(q, p, ctx);
    case "REVIEW_FIX":
      return reviewFix(q, p, ctx);
    case "MENU_ORDER":
      return menuOrder(q, p, ctx);
    case "POSTER":
      return poster(q, p, ctx);
    case "REORDER_NUDGE":
      return reorderNudge(q, p);
  }
}

