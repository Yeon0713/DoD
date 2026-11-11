// 시안에는 있지만 서버에 아직 없는 값들의 프론트 목업 (docs/frontend_plan_v4.md 7-2).
// 서버가 같은 값을 주기 시작하면 이 파일에서 하나씩 지운다. 문구는 Figma 04 시안을 따른다.
import { storage } from "@/lib/storage";
import { activePersona } from "./personas";
import type { NoticeItem, PlanItem, Review, StoreSettings, TodayBatch } from "@/types/contract";

/** 답글 초안. 서버에 draft_text가 생기기 전까지 쓴다. */
const DRAFTS: Record<string, string> = {
  rv_118: "늦은 배달로 불편을 드려 죄송합니다. 다음 주문은 더 빨리, 따뜻하게 보내 드릴게요.",
  rv_131: "국물이 짜서 실망하셨을 텐데 죄송합니다. 간을 다시 살펴 평소 맛으로 보내 드릴게요.",
  rv_105: "오래 기다리시게 해서 죄송합니다. 배달 순서를 다시 점검하고 있어요.",
  rv_111: "한참 기다리시게 해서 죄송합니다. 다음에는 더 빨리 보내 드릴게요.",
  rv_102: "매주 찾아 주셔서 감사합니다. 이번 주에도 따뜻하게 보내 드릴게요.",
  rv_087: "진한 국물 기억해 주셔서 감사합니다. 다음 달에도 맛있게 끓여 둘게요.",
  rv_109: "깔끔하게 봐 주셔서 감사합니다. 다음에도 넉넉하게 담아 드릴게요.",
  rv_112: "점심에 찾아 주셔서 감사합니다. 다음에도 후루룩 맛있게 준비할게요.",
  rv_121: "맛있게 드셔 주셔서 감사합니다. 맵기는 덜 맵게도 해 드릴 수 있어요.",
  rv_126: "요청사항까지 봐 주셔서 감사합니다. 다음에도 꼼꼼히 챙길게요.",
};

export function mockDraft(r: Review | undefined): string {
  if (!r) return "찾아 주셔서 감사합니다. 다음에도 맛있게 준비할게요.";
  const own = activePersona()?.drafts?.[r.review_id];
  if (own) return own;
  if (DRAFTS[r.review_id]) return DRAFTS[r.review_id];
  return r.label?.sentiment === "NEGATIVE"
    ? "불편을 드려 죄송합니다. 말씀해 주신 점을 꼭 고칠게요."
    : "찾아 주셔서 감사합니다. 다음에도 맛있게 준비할게요.";
}

/** 매달 단골 재주문 권유(REORDER_NUDGE) 인사말. 리뷰 답글이 아니라 다시 찾아 달라는 인사다. 서버에 draft_text가 생기기 전까지 쓴다. */
const NUDGES: Record<string, string> = {
  rv_087: "지난달 진한 국물 맛있게 드셔 주셔서 감사해요. 이번 주말에도 따뜻하게 끓여 두고 기다릴게요.",
};

export function mockNudge(r: Review | undefined): string {
  const own = r ? activePersona()?.nudges?.[r.review_id] : undefined;
  if (own) return own;
  if (r && NUDGES[r.review_id]) return NUDGES[r.review_id];
  return "지난번에 찾아 주셔서 감사해요. 이번 주말에도 맛있게 준비해 두고 기다릴게요.";
}

/** 화면에 보일 답글 초안: 서버가 CLOVA X로 쓴 초안(draft_text)이 있으면 그것을, 없으면 위의 기본 문장을 쓴다. */
export function draftFor(p: PlanItem | undefined, r: Review | undefined): string {
  if (p?.draft_text?.trim()) return p.draft_text;
  return p?.task_type === "REORDER_NUDGE" ? mockNudge(r) : mockDraft(r);
}

/** 04-21 "더 짧게", "더 정중하게" */
export function mockRewrite(text: string, style: "short" | "polite"): string {
  const sentences = text.split(/(?<=[.!?요다])\s+/).filter(Boolean);
  if (style === "short") return sentences[0] ?? text;
  if (text.startsWith("소중한")) return text;
  return `소중한 리뷰 남겨 주셔서 진심으로 감사드립니다. ${text.replace(/드릴게요\./g, "드리겠습니다.").replace(/할게요\./g, "하겠습니다.")}`;
}

/** 04-24 점검 목록 */
/** 메뉴 순서 예시. 서버에 메뉴 API가 없어서 업종별 예시를 쓴다 (04-53). */
const MENUS: Record<string, { name: string; tags: ("SEASON" | "GAME" | "EVENT")[] }[]> = {
  국수: [
    { name: "잔치국수", tags: [] },
    { name: "비빔국수", tags: ["EVENT"] },
    { name: "칼국수", tags: ["SEASON"] },
    { name: "김밥", tags: ["GAME", "EVENT"] },
    { name: "만두(5개)", tags: ["GAME"] },
  ],
  곱창: [
    { name: "소곱창 구이", tags: ["GAME"] },
    { name: "막창 구이", tags: ["GAME"] },
    { name: "곱창볶음", tags: ["EVENT"] },
    { name: "곱창전골", tags: ["SEASON"] },
    { name: "볶음밥", tags: [] },
  ],
  // 아래는 개발 화면 매장 시나리오(mocks/personas.ts)의 가게들
  치킨: [
    { name: "후라이드치킨", tags: [] },
    { name: "반반치킨", tags: ["GAME"] },
    { name: "치킨 맥주 세트", tags: ["GAME", "EVENT"] },
    { name: "닭볶음탕", tags: ["SEASON"] },
    { name: "감자튀김", tags: ["GAME"] },
  ],
  닭갈비: [
    { name: "철판 닭갈비", tags: [] },
    { name: "숯불 닭갈비", tags: ["EVENT"] },
    { name: "막국수", tags: ["EVENT"] },
    { name: "닭갈비 전골", tags: ["SEASON"] },
    { name: "볶음밥", tags: [] },
  ],
  백반: [
    { name: "제육볶음 백반", tags: [] },
    { name: "된장찌개 백반", tags: ["SEASON"] },
    { name: "오징어볶음 백반", tags: ["EVENT"] },
    { name: "김치찌개 백반", tags: ["SEASON"] },
    { name: "계란말이", tags: ["GAME"] },
  ],
  국밥: [
    { name: "순대국밥", tags: ["SEASON"] },
    { name: "돼지국밥", tags: [] },
    { name: "모둠순대", tags: ["GAME"] },
    { name: "얼큰국밥", tags: ["SEASON"] },
    { name: "수육 한 접시", tags: ["EVENT"] },
  ],
};

/** 포스터 큰 글자에 쓰는 음식 한마디 ("축구 보며 국수 한 그릇") */
const FOOD: Record<string, string> = { 국수: "국수 한 그릇", 곱창: "곱창 한 판", 치킨: "치킨 한 마리", 닭갈비: "닭갈비 한 판", 백반: "따뜻한 밥 한 상", 국밥: "국밥 한 그릇" };

export function foodPhrase(category: string): string {
  const key = Object.keys(FOOD).find((k) => category.includes(k));
  return key ? FOOD[key] : `${category} 한 그릇`;
}

export function storeMenus(category: string) {
  const key = Object.keys(MENUS).find((k) => category.includes(k)) ?? "국수";
  return MENUS[key];
}

/** 결과 알림 (04-43, 04-44). 서버 notice_items에 REPLY_RESULT, FIX_RESULT가 생기기 전까지 쓴다. */
export interface ResultNotice extends Omit<NoticeItem, "kind"> {
  kind: "REPLY_RESULT" | "FIX_RESULT";
  data: { before: number; after: number; label: string; since?: string };
}

export const RESULT_NOTICES: ResultNotice[] = [
  {
    notice_id: "REPLY_RESULT:2026-11-21",
    kind: "REPLY_RESULT",
    slot_at: "2026-11-23T10:00:00+09:00",
    refs: ["rv_109", "rv_112", "rv_121", "rv_126"],
    text: "토요일에 답글 단 손님 4분 중 2분이 주말에 다시 주문했어요.",
    data: { before: 4, after: 2, label: "답글" },
  },
  {
    notice_id: "FIX_RESULT:risk_004",
    kind: "FIX_RESULT",
    slot_at: "2026-11-25T10:00:00+09:00",
    refs: ["risk_004"],
    text: "11월 18일에 점검한 뒤로 배달이 늦다는 리뷰가 한 번도 없었어요.",
    data: { before: 3, after: 0, label: "DELIVERY_DELAY", since: "2026-11-18" },
  },
];

export const RESULT_BATCHES: TodayBatch[] = RESULT_NOTICES.map((n) => ({
  slot_at: n.slot_at,
  slot: "OPENING",
  entries: [{ plan_id: null, notice_id: n.notice_id, notify_kind: "NOTICE", priority: 4 }],
}));

/** 가게 찾기 목업 (04-2). 서버 GET /api/stores/search가 생기기 전까지 쓴다. */
export const STORE_ADDRESS: Record<string, string> = {
  store_001: "강원 춘천시 효자동",
};

/** 04-16 월요일 미리 보기의 도나 한마디. 지난주 결과(서버 REPLY_RESULT)가 생기면 그 값으로 바꾼다. */
export const LAST_WEEK_LINE = "지난주 답글 단 손님 중\n3분이 다시 왔어요";

/**
 * 답글 시각 규칙. 고정 샘플 모드에서만 고를 수 있다 (/dev).
 * - "design": Figma 04 시안과 처음 데모 주간 정답표(docs/frontend_plan.md 4장)대로.
 *   좋은 리뷰 묶음은 금요일 오후 승인, 토요일 출근 후 올림(04-17, 04-40).
 *   주간 단골(04-11, 04-32)과 월간 단골(04-35, 04-38) 답글을 넣는다.
 * - "server": 지금 서버 규칙 그대로. 좋은 리뷰는 토요일 10시 승인, 11시 자동 올림이고 단골 맞춤 답글은 이번 주에 없다.
 */
export type ReplyRule = "design" | "server";
export const RULE_KEY = "dona.rule";

export function readRule(): ReplyRule {
  return storage.getItem(RULE_KEY) === "server" ? "server" : "design";
}

function at(day: string, hhmm: string) {
  return `${day}T${hhmm}:00+09:00`;
}

function prevDay(day: string) {
  const d = new Date(`${day}T12:00:00+09:00`);
  d.setUTCDate(d.getUTCDate() - 1);
  return new Date(d.getTime() + 9 * 3600e3).toISOString().slice(0, 10);
}

export function applyDesignRule(items: PlanItem[], s: StoreSettings): PlanItem[] {
  const pm = s.slots.AFTERNOON;
  const am = s.slots.OPENING;
  const close = s.slots.CLOSING;
  const changed = items.map((p) => {
    if (p.task_type === "REVISIT_REPLY" && p.revisit_class === "BASIC" && p.execute_at) {
      const day = p.execute_at.slice(0, 10);
      return { ...p, approval_request_at: at(prevDay(day), pm), execute_at: at(day, am), deadline_at: at(day, am), reason_line: "이번 주에 들어온 좋은 리뷰예요. 토요일 출근 후에 답글을 함께 올려요." };
    }
    return p;
  });
  const regulars: PlanItem[] = [
    {
      plan_id: "REVISIT_REPLY:rv_102:2026-11-18",
      task_type: "REVISIT_REPLY",
      revisit_class: "WEEKLY",
      basis: { kind: "REVIEW", ref_id: "rv_102" },
      target_date: "2026-11-18",
      approval_request_at: at("2026-11-17", pm),
      execute_at: at("2026-11-18", pm),
      deadline_at: at("2026-11-17", close),
      reason_line: "매주 수요일 저녁에 주문하는 단골 손님이에요. 주문하는 날 오후에 감사 답글을 올려요.",
      planned_at: "2026-11-17T09:00:00+09:00",
    },
    {
      plan_id: "REVISIT_REPLY:rv_087:2026-11-20",
      task_type: "REVISIT_REPLY",
      revisit_class: "MONTHLY",
      basis: { kind: "REVIEW", ref_id: "rv_087" },
      target_date: "2026-11-20",
      approval_request_at: at("2026-11-19", pm),
      execute_at: at("2026-11-20", pm),
      deadline_at: at("2026-11-19", close),
      reason_line: "한 달에 한 번 주문하는 단골 손님이에요. 다시 주문할 때쯤 감사 답글을 올려요.",
      planned_at: "2026-11-19T09:00:00+09:00",
    },
  ];
  return [...changed, ...regulars];
}

/**
 * 이번 주 날씨 (Figma 05-7 계열). 서버 calendar 응답에 날씨가 생기기 전까지 쓴다.
 * 제안: calendar 응답에 날짜별 weather { sky: SUNNY | PARTLY | CLOUDY | RAIN, high, low } (docs/frontend_mock_and_api_needs.md 3장 Q).
 * 데모 주간 춘천, 수요일부터 추워진다.
 */
export type Sky = "SUNNY" | "PARTLY" | "CLOUDY" | "RAIN";
export const WEATHER: Record<string, { sky: Sky; high: number; low: number }> = {
  "2026-11-16": { sky: "SUNNY", high: 13, low: 2 },
  "2026-11-17": { sky: "PARTLY", high: 11, low: 1 },
  "2026-11-18": { sky: "CLOUDY", high: 5, low: -3 },
  "2026-11-19": { sky: "SUNNY", high: 4, low: -5 },
  "2026-11-20": { sky: "CLOUDY", high: 7, low: -2 },
  "2026-11-21": { sky: "SUNNY", high: 9, low: -1 },
  "2026-11-22": { sky: "PARTLY", high: 10, low: 0 },
  "2026-11-23": { sky: "PARTLY", high: 8, low: -1 },
  "2026-11-24": { sky: "RAIN", high: 7, low: 2 },
  "2026-11-25": { sky: "SUNNY", high: 6, low: -3 },
};
export const SKY_KO: Record<Sky, string> = { SUNNY: "맑음", PARTLY: "구름 조금", CLOUDY: "흐림", RAIN: "비" };
