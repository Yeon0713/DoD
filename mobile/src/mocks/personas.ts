// 개발 화면의 "매장 시나리오". 데모 한 주의 할 일 카드 28장을 매장별로 나눠, 매장 하나를 고르면 3~6장만 홈에 보인다.
// 모든 매장은 같은 동네(춘천 대학가)에 있어서 날씨, 축구 경기, 지역 축제 같은 바깥 일정은 같다.
// 같은 한 주라도 업종과 손님이 다르면 도나가 챙기는 일이 달라진다는 것을 보여 준다.
// 카드 id 모양: "알림 종류:계획 id" (lib/queue.ts). 결과 알림은 "NOTICE:알림 id", 좋은 리뷰 묶음은 "BASIC:알림 종류:실행 시각".
import { devFlags } from "@/lib/dev";
import type { Prefs } from "@/lib/localStore";

/** 킬러 기능의 네 흐름 (발표 자료와 같은 번호) */
export type Flow = "revisit" | "menu" | "poster" | "review";
export const FLOW_LABEL: Record<Flow, string> = {
  revisit: "1 재방문 유도",
  menu: "2 메뉴판 최적화",
  poster: "3 홍보 포스터",
  review: "4 부정 리뷰 개선",
};

export interface Scene {
  id: string;
  /** 개발 화면 버튼 글자 ("화요일 오후") */
  label: string;
  /** 이 장면의 지금 (서울 시각). 여러 날에 걸친 장면은 첫 카드가 오는 날로 둔다. 다른 날 카드는 홈에 "목요일 10:00 알림"처럼 날이 붙는다 */
  now: string;
  /** 홈에 보일 카드 id. 위에서부터 할 일 순서와 상관없이 우선순위대로 정렬된다 */
  cards: string[];
  /** 발표하거나 검토할 때 볼 한 줄 설명 */
  note: string;
  /** 이 장면에서 쓸 이 기기 설정 (네이버 연결 상태로 메뉴판 카드 모양이 달라진다) */
  prefs?: Partial<Prefs>;
}

export interface Persona {
  id: string;
  /** 발표에서 보여 줄 메인 시나리오 */
  main?: boolean;
  store: {
    name: string;
    /** 메뉴판, 포스터 메뉴를 고르는 업종 (mocks/extras.ts MENUS) */
    category: string;
    area: string;
    staff: string;
    channels: string;
  };
  /** 사장님과 가게를 한 줄로 */
  who: string;
  /** 도나가 이 가게에서 보는 데이터 */
  data: string[];
  flows: Flow[];
  scenes: Scene[];
  /** 이 가게 리뷰 글 (리뷰 id → 글). 없으면 예시 리뷰 그대로 */
  reviews?: Record<string, string>;
  /** 이 가게 답글 초안 (리뷰 id → 글) */
  drafts?: Record<string, string>;
  /** 이 가게 재주문 권유 인사 (리뷰 id → 글) */
  nudges?: Record<string, string>;
}

/** 데모 한 주 카드 28장의 id */
export const C = {
  weeklyPreview: "PREVIEW:WEEKLY_PREVIEW:2026-11-16",
  gamePoster: "APPROVAL_REQUEST:POSTER:game_031:2026-11-19",
  gamePosterPost: "EXECUTE_REMINDER:POSTER:game_031:2026-11-19",
  lateDelivery: "APPROVAL_REQUEST:REVISIT_REPLY:rv_118:2026-11-17",
  repeatComplaint: "APPROVAL_REQUEST:REVIEW_FIX:risk_004:2026-11-17",
  weeklyRegular: "APPROVAL_REQUEST:REVISIT_REPLY:rv_102:2026-11-18",
  weeklyRegularPost: "EXECUTE_REMINDER:REVISIT_REPLY:rv_102:2026-11-18",
  seasonMenu: "APPROVAL_REQUEST:MENU_ORDER:2026-11-18:2026-11-18",
  seasonMenuDo: "EXECUTE_REMINDER:MENU_ORDER:2026-11-18:2026-11-18",
  salesAnomaly: "NOTICE:SALES_ANOMALY:2026-11-17:LUNCH",
  gameMenu: "APPROVAL_REQUEST:MENU_ORDER:2026-11-19:2026-11-19",
  gameMenuDo: "EXECUTE_REMINDER:MENU_ORDER:2026-11-19:2026-11-19",
  gameMenuEnd: "APPROVAL_REQUEST:MENU_ORDER:2026-11-20:2026-11-20",
  gameMenuEndDo: "EXECUTE_REMINDER:MENU_ORDER:2026-11-20:2026-11-20",
  festivalPoster: "APPROVAL_REQUEST:POSTER:event_012:2026-11-21",
  festivalPosterPost: "EXECUTE_REMINDER:POSTER:event_012:2026-11-21",
  festivalMenu: "APPROVAL_REQUEST:MENU_ORDER:2026-11-21:2026-11-21",
  festivalMenuDo: "EXECUTE_REMINDER:MENU_ORDER:2026-11-21:2026-11-21",
  festivalMenuEnd: "APPROVAL_REQUEST:MENU_ORDER:2026-11-23:2026-11-23",
  festivalMenuEndDo: "EXECUTE_REMINDER:MENU_ORDER:2026-11-23:2026-11-23",
  monthlyRegular: "APPROVAL_REQUEST:REVISIT_REPLY:rv_087:2026-11-20",
  monthlyRegularPost: "EXECUTE_REMINDER:REVISIT_REPLY:rv_087:2026-11-20",
  monthlyNudge: "APPROVAL_REQUEST:REORDER_NUDGE:c_m01:2026-11-21",
  goodReviews: "BASIC:APPROVAL_REQUEST:2026-11-21T10:00:00+09:00",
  goodReviewsPost: "BASIC:EXECUTE_REMINDER:2026-11-21T10:00:00+09:00",
  tasteComplaint: "APPROVAL_REQUEST:REVISIT_REPLY:rv_131:2026-11-20",
  replyResult: "NOTICE:REPLY_RESULT:2026-11-21",
  fixResult: "NOTICE:FIX_RESULT:risk_004",
} as const;

const CONNECTED: Partial<Prefs> = { naverConnected: true, naverAuto: false, naverDeclined: false };
const AUTO: Partial<Prefs> = { naverConnected: true, naverAuto: true, naverDeclined: false };
const DECLINED: Partial<Prefs> = { naverConnected: false, naverAuto: false, naverDeclined: true };
const NAVER_OFF: Partial<Prefs> = { naverConnected: false, naverAuto: false, naverDeclined: false };

export const PERSONAS: Persona[] = [
  {
    id: "noodle",
    main: true,
    store: { name: "춘천 대학가 국수집", category: "국수", area: "강원 춘천시 효자동, 대학교 정문 앞", staff: "사장님 1명, 점심 알바 1명", channels: "홀 40%, 배달의민족 35%, 쿠팡이츠 15%, 요기요 10%" },
    who: "점심엔 학생 손님, 저녁엔 배달이 몰리는 혼자 운영하는 국수집. 리뷰 답글과 메뉴판은 바빠서 늘 미뤄 왔다.",
    data: ["주문 8,368건 (시간대, 요일, 메뉴별 매출)", "배달앱 리뷰와 별점, 주문 시각", "날씨: 수요일부터 추워짐", "스포츠: 목요일 저녁 국가대표 축구", "지역 행사: 주말 지역 축제"],
    flows: ["review", "revisit", "menu", "poster"],
    scenes: [
      {
        id: "find",
        label: "화요일 오후",
        now: "2026-11-17T14:05",
        cards: [C.lateDelivery, C.repeatComplaint, C.weeklyRegular, C.seasonMenu, C.gamePosterPost],
        note: "도나가 찾은 일 5가지. 배달 지연 리뷰가 일주일에 3번(4 부정 리뷰), 수요일 단골(1 재방문), 내일 추위(2 메뉴판), 목요일 축구(3 포스터)",
        prefs: NAVER_OFF,
      },
      {
        id: "act",
        label: "수요일",
        now: "2026-11-18T14:05",
        cards: [C.seasonMenuDo, C.salesAnomaly, C.weeklyRegularPost],
        note: "실행하는 날. 아침에 국물 메뉴를 위로 올리고, 어제 점심 매출이 35% 늘었다는 알림, 단골이 주문하기 전에 답글 올리기",
        prefs: CONNECTED,
      },
      {
        id: "result",
        label: "다음 주",
        now: "2026-11-23T10:05",
        cards: [C.replyResult, C.fixResult],
        note: "해 본 일의 결과. 답글 단 손님 4분 중 2분이 다시 주문했고, 점검한 뒤로 배달 지연 리뷰가 3건에서 0건이 됐어요",
        prefs: CONNECTED,
      },
    ],
  },
  {
    id: "pub",
    store: { name: "효자동 치킨호프", category: "치킨", area: "강원 춘천시 효자동, 대학가 먹자골목", staff: "사장님 부부, 저녁 알바 2명", channels: "홀 55%, 배달의민족 30%, 쿠팡이츠 15%" },
    who: "경기 있는 날 저녁에 손님이 두 배가 되는 치킨호프. 경기 일정은 알지만 메뉴판과 홍보는 늘 당일에 허겁지겁 한다.",
    data: ["저녁, 밤 시간대 매출", "스포츠: 목요일 저녁 국가대표 축구 (매출 21% 증가 예상)", "인기 메뉴: 반반치킨, 맥주 세트"],
    flows: ["poster", "menu"],
    scenes: [
      {
        id: "game",
        label: "경기 주간",
        now: "2026-11-16T14:05",
        cards: [C.gamePoster, C.gamePosterPost, C.gameMenu, C.gameMenuDo, C.gameMenuEnd, C.gameMenuEndDo],
        note: "경기 3일 전 포스터 만들기부터 경기 다음 날 메뉴판 되돌리기까지. 네이버 연결된 가게라 메뉴판 미리 보기가 카드에 보여요",
        prefs: CONNECTED,
      },
    ],
  },
  {
    id: "festival",
    store: { name: "춘천 명동 닭갈비", category: "닭갈비", area: "강원 춘천시 명동, 축제 거리 옆", staff: "사장님 1명, 직원 3명", channels: "홀 80%, 포장 20%" },
    who: "주말 지역 축제 때 관광객이 몰리는 닭갈비집. 네이버 메뉴 순서 바꾸기를 도나에게 맡겨 두었다.",
    data: ["지역 행사: 토요일, 일요일 지역 축제 (매출 30% 증가 예상)", "관광객 많은 주말 매출", "네이버 플레이스 메뉴 순서"],
    flows: ["poster", "menu"],
    scenes: [
      {
        id: "weekend",
        label: "축제 주간",
        now: "2026-11-18T14:05",
        cards: [C.festivalPoster, C.festivalPosterPost, C.festivalMenu, C.festivalMenuDo, C.festivalMenuEnd, C.festivalMenuEndDo],
        note: "축제 포스터와 축제 메뉴. 메뉴 순서를 알아서 바꾸게 맡겨 둔 가게라, 도나가 바꾼 뒤에 알려 줘요",
        prefs: AUTO,
      },
    ],
  },
  {
    id: "regular",
    store: { name: "효자동 가정식 백반", category: "백반", area: "강원 춘천시 효자동, 주택가", staff: "사장님 1명, 주방 이모 1명", channels: "홀 60%, 배달의민족 40%" },
    who: "같은 손님이 매주, 매달 다시 찾는 동네 백반집. 단골 얼굴은 알지만 답글로 인사할 틈이 없다.",
    data: ["손님별 주문 주기 (매주 수요일, 매달 셋째 주)", "좋은 리뷰와 답글 여부", "주말 재주문 비율"],
    flows: ["revisit"],
    scenes: [
      {
        id: "regulars",
        label: "단골 챙기는 주",
        now: "2026-11-18T14:05",
        cards: [C.weeklyRegularPost, C.monthlyRegular, C.monthlyRegularPost, C.goodReviews, C.goodReviewsPost, C.monthlyNudge],
        note: "매주 단골, 매달 단골, 좋은 리뷰 4개에 주말 주문 전에 답글과 인사를 남겨요",
      },
    ],
    reviews: {
      rv_102: "수요일마다 시켜 먹는데 제육볶음이 늘 따뜻하게 와요.",
      rv_087: "된장찌개가 진하고 반찬이 매일 달라요. 한 달에 한 번은 꼭 생각나요.",
      rv_109: "가게가 깔끔하고 밥 양도 넉넉했어요.",
      rv_112: "점심에 든든하게 먹기 딱 좋아요.",
      rv_121: "오징어볶음 맛있어요. 조금 매웠지만 또 먹을래요.",
      rv_126: "요청사항을 꼼꼼히 챙겨 주셔서 좋았어요.",
    },
    drafts: {
      rv_102: "매주 찾아 주셔서 감사합니다. 이번 주 제육볶음도 따뜻하게 보내 드릴게요.",
      rv_087: "진한 된장찌개 기억해 주셔서 감사합니다. 다음 달에도 정성껏 끓여 둘게요.",
      rv_109: "깔끔하게 봐 주셔서 감사합니다. 다음에도 넉넉하게 담아 드릴게요.",
      rv_112: "점심에 찾아 주셔서 감사합니다. 다음에도 든든하게 준비할게요.",
      rv_121: "맛있게 드셔 주셔서 감사합니다. 맵기는 덜 맵게도 해 드릴 수 있어요.",
    },
    nudges: {
      rv_087: "지난달 된장찌개 맛있게 드셔 주셔서 감사해요. 이번 주말에도 따뜻하게 끓여 두고 기다릴게요.",
    },
  },
  {
    id: "delivery",
    store: { name: "배달 전문 순대국밥", category: "국밥", area: "강원 춘천시 석사동, 배달 전문 매장", staff: "사장님 1명, 배달 대행 이용", channels: "배달의민족 60%, 쿠팡이츠 30%, 요기요 10%" },
    who: "홀 없이 배달만 하는 국밥집. 저녁 7시에 주문이 몰리면 배달이 늦고, 별점 하나가 매출을 흔든다.",
    data: ["배달앱 리뷰, 별점, 주문 시각", "불만 종류별 반복 (배달 지연, 맛)", "점검 뒤 같은 불만이 줄었는지"],
    flows: ["review"],
    scenes: [
      {
        id: "complaints",
        label: "불만이 쌓인 주",
        now: "2026-11-17T14:05",
        cards: [C.tasteComplaint, C.lateDelivery, C.repeatComplaint, C.fixResult],
        note: "부정 리뷰를 찾아 바로 사과 답글, 반복되는 배달 지연은 원인(저녁 7시 주문 몰림)을 보여 주고, 일주일 뒤 줄었는지 확인해요",
      },
    ],
    reviews: {
      rv_131: "오늘은 국물이 너무 짰어요. 평소랑 맛이 달라요. 순대도 좀 식어 있었고요. 자주 시켜 먹던 집이라 더 아쉬워요.",
      rv_105: "배달이 40분 넘게 걸려서 국밥이 다 식었어요.",
      rv_118: "배달이 너무 늦어서 다 식어서 왔어요.",
    },
    drafts: {
      rv_131: "국물이 짜서 실망하셨을 텐데 죄송합니다. 간을 다시 살펴 평소 맛으로 보내 드릴게요.",
      rv_118: "늦은 배달로 불편을 드려 죄송합니다. 다음 주문은 더 빨리, 따끈하게 보내 드릴게요.",
    },
  },
  {
    id: "season",
    store: { name: "춘천 곱창집", category: "곱창", area: "강원 춘천시 후평동, 대로변", staff: "사장님 1명, 직원 2명", channels: "홀 70%, 배달의민족 30%" },
    who: "날이 추워지면 전골 주문이 느는 곱창집. 메뉴판 순서는 직접 바꾸겠다고 했다.",
    data: ["날씨: 수요일부터 아침 1도", "요일, 시간대별 매출과 평소 대비 변화", "이번 주 바쁜 때 (경기, 축제)"],
    flows: ["menu"],
    scenes: [
      {
        id: "cold",
        label: "추워지는 주",
        now: "2026-11-16T10:05",
        cards: [C.weeklyPreview, C.seasonMenu, C.seasonMenuDo, C.salesAnomaly],
        note: "월요일 이번 주 미리 보기, 추워지기 전날 전골을 위로 올리자는 제안, 직접 바꾸는 날 알림, 매출 이상 알림",
        prefs: DECLINED,
      },
    ],
  },
];

/** 매장을 고르지 않았을 때 쓰는 메인 시나리오 */
export const MAIN_PERSONA = PERSONAS.find((p) => p.main)!;

export function findPersona(id: string | null | undefined): Persona | null {
  return PERSONAS.find((p) => p.id === id) ?? null;
}

export function findScene(p: Persona, sceneId: string | null | undefined): Scene {
  return p.scenes.find((s) => s.id === sceneId) ?? p.scenes[0];
}

/** 매장 시나리오가 다루는 카드 (빠진 카드가 없는지 개발 화면에서 확인한다) */
export const COVERED: string[] = [...new Set(PERSONAS.flatMap((p) => p.scenes.flatMap((s) => s.cards)))];

/** 지금 고른 매장 (한 주 모아 보기 중이면 없음). 목업 서버와 답글 초안이 이 가게 글을 쓴다. */
export function activePersona(): Persona | null {
  const f = devFlags.read();
  return f.allWeek ? null : findPersona(f.persona);
}
