// 개발용 시뮬레이터 (docs/frontend_plan.md F5, 고정 샘플 모드 전용).
// Next.js 판은 주소 뒤 ?now= ?card= 와 localStorage를 썼다. 앱은 개발 스위치(devFlags)와 이 기기 저장소(storage)를 바꾼다.
// 화면 바로 가기, 가상 시각, 실패와 끊김 스위치, 답글 시각 규칙, 이 기기 상태, 데모 주간 알림 타임라인.
import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { SafeAreaView } from "react-native-safe-area-context";
import { back, go, goHome } from "@/components/ui/nav";
import { PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { Toggle } from "@/components/ui/sub";
import { account } from "@/lib/account";
import { USE_MOCK } from "@/lib/api";
import { resetCardState, useCardState } from "@/lib/cardState";
import { devFlags, virtualNow, type DevFlags } from "@/lib/dev";
import { drafts, flashToast, prefs, type Prefs } from "@/lib/localStore";
import { storage } from "@/lib/storage";
import { DEMO_NOW, hhmm, monthDay, weekdayName } from "@/lib/time";
import { buildTodayCards } from "@/lib/todayCards";
import { useHome } from "@/lib/useHome";
import { readRule, RULE_KEY, type ReplyRule } from "@/mocks/extras";
import { MAIN_PERSONA, type Persona, type Scene } from "@/mocks/personas";
import { resetMockSettings, setMockStore } from "@/mocks/server";
import { StoreScenarios } from "./StoreScenarios";
import tokens from "@/theme/tokens.json";
import type { NotifyKind, PlanItem } from "@/types/contract";

const C = tokens.colors;
const HOME_CACHE = "dona.home.v3";

const KIND_KO: Record<NotifyKind, string> = { APPROVAL_REQUEST: "승인 요청", EXECUTE_REMINDER: "실행 알림", PREVIEW: "예고", NOTICE: "알림" };
/** 가상 시각 바로 고르기: 데모 주간 날짜 × 하루 3번 알림 직후 */
const DAYS = ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22", "2026-11-23", "2026-11-25"];
const SLOTS = [
  ["10:05", "출근 후"],
  ["14:05", "오후"],
  ["21:35", "마감 전"],
] as const;
/** 목업 응답 늦추기 (ms). null은 기본 600 */
const DELAYS: (number | null)[] = [null, 0, 3000, 8000, 60000];

const enc = encodeURIComponent;
const NAVER_OFF: Partial<Prefs> = { naverConnected: false, naverAuto: false, naverDeclined: false };
const DECLINED: Partial<Prefs> = { naverConnected: false, naverAuto: false, naverDeclined: true };
const CONNECTED: Partial<Prefs> = { naverConnected: true, naverAuto: false, naverDeclined: false };
const AUTO: Partial<Prefs> = { naverConnected: true, naverAuto: true, naverDeclined: false };
const DEFAULT_PREFS: Partial<Prefs> = { onboarded: true, notifyOff: false, firstDayPending: false, ...NAVER_OFF };

/** 바로 가기와 매장 시나리오는 로그인한 사장님으로 연다 (로그인 안 했으면 네이버로 가입한 것으로 본다). */
function signInForReview() {
  if (!account.read().method) account.write({ method: "naver" });
}

/** 바로 가기 한 줄. card는 오늘 화면에서 맨 앞으로 꺼낼 카드 id, flags는 그때만 켤 개발 스위치 */
type Go = { id: string; label: string; href: string; now?: string; card?: string; flags?: Partial<DevFlags>; prefs?: Partial<Prefs>; toast?: [string, string]; note?: string };

const card = (kind: string, id: string) => `${kind}:${id}`;
const BASIC_AT = "2026-11-21T10:00:00+09:00";
const T = "2026-11-17T14:05";

/** Figma 화면 → 그 화면을 여는 주소와 상태 (Next.js 판과 같은 목록) */
const FIGMA: { group: string; items: Go[] }[] = [
  {
    group: "처음 쓰는 날",
    items: [
      { id: "04-1", label: "왜 도나인가", href: "/start" },
      { id: "04-2", label: "우리 가게 찾기", href: "/start/store" },
      { id: "04-2b", label: "가게를 못 찾았을 때", href: `/start/store?q=${enc("홍길동 치킨")}` },
      { id: "04-3", label: "알림 받을 때 고르기", href: "/start/notify-time" },
      { id: "04-3b", label: "알림 켜 주세요", href: "/start/notify-on" },
      { id: "04-4n", label: "알림이 꺼진 채로 들어왔을 때", href: "/", now: T, prefs: { notifyOff: true } },
      { id: "04-4f", label: "첫날 새 리뷰가 없을 때", href: "/", now: "2026-11-16T09:30", prefs: { firstDayPending: true } },
    ],
  },
  {
    group: "매일: 화요일 오후",
    items: [
      { id: "04-23", label: "잠금 화면에서 시작", href: "/lock", now: T },
      { id: "04-4", label: "오늘 할 일 하나", href: "/", card: card("APPROVAL_REQUEST", "REVISIT_REPLY:rv_118:2026-11-17"), now: T },
      { id: "04-5", label: "답글 보고 올리기", href: `/reply/${enc("REVISIT_REPLY:rv_118:2026-11-17")}`, now: T },
      { id: "04-5s", label: "답글을 올렸어요 띠", href: "/", card: card("APPROVAL_REQUEST", "REVIEW_FIX:risk_004:2026-11-17"), now: T, toast: ["답글을 올렸어요", "배달의민족에서 볼 수 있어요"] },
      { id: "04-5f", label: "답글을 못 올렸을 때", href: `/reply/${enc("REVISIT_REPLY:rv_118:2026-11-17")}?view=failed`, now: T },
      { id: "04-10", label: "위험 신호 (같은 불만 반복)", href: "/", card: card("APPROVAL_REQUEST", "REVIEW_FIX:risk_004:2026-11-17"), now: T },
      { id: "04-11", label: "주간 단골 답글", href: "/", card: card("APPROVAL_REQUEST", "REVISIT_REPLY:rv_102:2026-11-18"), now: T, note: "시안 규칙" },
      { id: "04-12", label: "메뉴판 계절 전환 (직접)", href: "/", card: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-18:2026-11-18"), now: T, prefs: DECLINED },
      { id: "04-6", label: "다 했어요", href: "/", now: "2026-11-24T15:00" },
    ],
  },
  {
    group: "매일: 옆길",
    items: [
      { id: "04-22", label: "나중에 다시 알림 시트", href: "/task?sheet=later", now: T },
      { id: "04-21", label: "답글 고쳐 쓰기", href: `/reply/${enc("REVISIT_REPLY:rv_118:2026-11-17")}/edit`, now: T },
      { id: "04-24", label: "배달 지연 점검", href: `/check/${enc("REVIEW_FIX:risk_004:2026-11-17")}`, now: T },
      { id: "04-11r", label: "주간 단골 답글 보기", href: `/reply/${enc("REVISIT_REPLY:rv_102:2026-11-18")}`, now: T, note: "시안 규칙" },
    ],
  },
  {
    group: "홈 불러오기와 문제가 생겼을 때",
    items: [
      { id: "04-8", label: "처음 (0.3초부터)", href: "/", flags: { fresh: true, delay: 60000 }, now: T, note: "열고 바로" },
      { id: "04-8c", label: "3초가 넘을 때", href: "/", flags: { fresh: true, delay: 60000 }, now: T, note: "3초 기다리기" },
      { id: "04-8d", label: "10초가 넘을 때", href: "/", flags: { fresh: true, delay: 60000 }, now: T, note: "10초 기다리기" },
      { id: "04-8b", label: "다시 열 때 (지난 할 일 먼저)", href: "/", flags: { delay: 8000 }, now: T },
      { id: "04-9", label: "인터넷이 끊겼을 때", href: "/", flags: { offline: true }, now: T },
    ],
  },
  {
    group: "05 시안: 새로 바뀐 화면",
    items: [
      { id: "05-4", label: "카드에서 바로 답글 달기", href: "/", card: card("APPROVAL_REQUEST", "REVISIT_REPLY:rv_118:2026-11-17"), now: T },
      { id: "05-12n", label: "메뉴판 카드 (네이버 미리 보기)", href: "/", card: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-18:2026-11-18"), now: T, prefs: CONNECTED },
      { id: "05-55s", label: "내일 바꿔 둘게요", href: `/menu-order/${enc("MENU_ORDER:2026-11-18:2026-11-18")}?apply=1`, now: T, prefs: CONNECTED },
      { id: "05-31n", label: "포스터 카드 (포스터 미리 보기)", href: "/", card: card("EXECUTE_REMINDER", "POSTER:game_031:2026-11-19"), now: T },
      { id: "05-2h", label: "언제 장사하세요?", href: "/start/hours" },
      { id: "05-2i", label: "장사 시간 확인", href: "/start/hours/confirm?p=LUNCH_DINNER" },
      { id: "05-3", label: "장사 시간에 맞춘 알림 시간", href: "/start/notify-time" },
      { id: "05-19h", label: "설정 장사 시간", href: "/settings/hours" },
    ],
  },
  {
    group: "매출",
    items: [
      { id: "06-70", label: "매출 첫 화면", href: "/sales", now: T },
      { id: "06-71", label: "이번 주와 지난주", href: "/sales/week", now: T },
      { id: "06-72", label: "메뉴별", href: "/sales/menu", now: T },
      { id: "06-73", label: "시간대와 요일", href: "/sales/time", now: T },
      { id: "06-74", label: "배달앱과 단골", href: "/sales/channel", now: T },
      { id: "06-75", label: "달별 흐름", href: "/sales/month", now: T },
    ],
  },
  {
    group: "설정",
    items: [
      { id: "04-19", label: "모아 보기", href: "/settings" },
      { id: "04-19b", label: "알림 받는 시간 바꾸기", href: "/settings/notify-time" },
      { id: "04-20", label: "바쁜 장사 시간", href: "/settings/busy" },
    ],
  },
  {
    group: "다른 요일의 할 일 카드",
    items: [
      { id: "04-16", label: "월요일 이번 주 미리 보기", href: "/", card: card("PREVIEW", "WEEKLY_PREVIEW:2026-11-16"), now: "2026-11-16T10:05" },
      { id: "04-13", label: "경기 포스터 만들기", href: "/", card: card("APPROVAL_REQUEST", "POSTER:game_031:2026-11-19"), now: "2026-11-16T14:05" },
      { id: "04-14", label: "실행 알림 메뉴판 계절", href: "/", card: card("EXECUTE_REMINDER", "MENU_ORDER:2026-11-18:2026-11-18"), now: "2026-11-18T10:05", prefs: DECLINED },
      { id: "04-15", label: "매출 이상 알림", href: "/", card: card("NOTICE", "SALES_ANOMALY:2026-11-17:LUNCH"), now: "2026-11-18T10:05" },
      { id: "04-17", label: "좋은 리뷰 답글 묶음", href: "/", card: card("BASIC:APPROVAL_REQUEST", BASIC_AT), now: "2026-11-20T14:05", note: "시안 규칙" },
      { id: "04-25", label: "좋은 리뷰 답글 4개", href: `/reply/batch/${enc("REVISIT_REPLY:rv_109:2026-11-21")}`, now: "2026-11-20T14:05" },
      { id: "04-25b", label: "좋은 리뷰 답글 하나씩", href: `/reply/batch/${enc("REVISIT_REPLY:rv_109:2026-11-21")}?one=0`, now: "2026-11-20T14:05" },
    ],
  },
  {
    group: "이번 주",
    items: [
      { id: "06-7", label: "이번 주 (오늘 화요일)", href: "/week", now: T },
      { id: "06-7-월", label: "월요일을 눌렀을 때", href: "/week?day=2026-11-16", now: T },
      { id: "06-7-수", label: "수요일 (추워지는 날)", href: "/week?day=2026-11-18", now: T },
      { id: "06-7-목", label: "목요일", href: "/week?day=2026-11-19", now: T },
      { id: "06-7-금", label: "금요일", href: "/week?day=2026-11-20", now: T },
      { id: "06-7-토", label: "토요일", href: "/week?day=2026-11-21", now: T },
      { id: "06-7-일", label: "일요일", href: "/week?day=2026-11-22", now: T },
      { id: "06-7L", label: "불러오는 중", href: "/week", flags: { fresh: true, delay: 60000 }, now: T },
      { id: "06-7E", label: "인터넷이 끊겼을 때", href: "/week", flags: { offline: true }, now: T },
    ],
  },
  {
    group: "이번 주: 같이 하면 좋은 일",
    items: [
      { id: "06-18", label: "목요일 저녁 자세히", href: "/week/game_031", now: T },
      { id: "04-28", label: "메뉴판 경기", href: "/", card: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-19:2026-11-19"), now: "2026-11-18T14:05", prefs: DECLINED },
      { id: "04-26", label: "축제 포스터 만들기", href: "/", card: card("APPROVAL_REQUEST", "POSTER:event_012:2026-11-21"), now: "2026-11-18T14:05" },
      { id: "06-18b", label: "주말 축제 자세히", href: "/week/event_012", now: T },
      { id: "04-27", label: "메뉴판 축제", href: "/", card: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-21:2026-11-21"), now: "2026-11-20T14:05", prefs: DECLINED },
    ],
  },
  {
    group: "데모 주간 나머지 알림",
    items: [
      { id: "04-31", label: "화 오전 경기 포스터 올리기", href: "/", card: card("EXECUTE_REMINDER", "POSTER:game_031:2026-11-19"), now: "2026-11-17T10:05" },
      { id: "04-32", label: "수 오후 주간 단골 답글", href: "/", card: card("EXECUTE_REMINDER", "REVISIT_REPLY:rv_102:2026-11-18"), now: "2026-11-18T14:05", note: "시안 규칙" },
      { id: "04-33", label: "목 오전 메뉴판 경기", href: "/", card: card("EXECUTE_REMINDER", "MENU_ORDER:2026-11-19:2026-11-19"), now: "2026-11-19T10:05", prefs: CONNECTED },
      { id: "04-34", label: "목 오전 축제 포스터 올리기", href: "/", card: card("EXECUTE_REMINDER", "POSTER:event_012:2026-11-21"), now: "2026-11-19T10:05" },
      { id: "04-35", label: "목 오후 월간 단골 답글", href: "/", card: card("APPROVAL_REQUEST", "REVISIT_REPLY:rv_087:2026-11-20"), now: "2026-11-19T14:05", note: "시안 규칙" },
      { id: "04-35r", label: "월간 단골 답글 보기", href: `/reply/${enc("REVISIT_REPLY:rv_087:2026-11-20")}`, now: "2026-11-19T14:05", note: "시안 규칙" },
      { id: "04-36", label: "목 오후 메뉴판 경기 끝", href: "/", card: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-20:2026-11-20"), now: "2026-11-19T14:05", prefs: DECLINED },
      { id: "04-37", label: "금 오전 메뉴판 원래대로", href: "/", card: card("EXECUTE_REMINDER", "MENU_ORDER:2026-11-20:2026-11-20"), now: "2026-11-20T10:05", prefs: CONNECTED },
      { id: "04-38", label: "금 오후 월간 단골 답글", href: "/", card: card("EXECUTE_REMINDER", "REVISIT_REPLY:rv_087:2026-11-20"), now: "2026-11-20T14:05", note: "시안 규칙" },
      { id: "04-39", label: "금 밤 빠른 응대 맛 불만", href: "/", card: card("APPROVAL_REQUEST", "REVISIT_REPLY:rv_131:2026-11-20"), now: "2026-11-20T21:35" },
      { id: "04-39r", label: "맛 불만 사과 답글", href: `/reply/${enc("REVISIT_REPLY:rv_131:2026-11-20")}`, now: "2026-11-20T21:35" },
      { id: "04-40", label: "토 오전 좋은 리뷰 4개 올리기", href: "/", card: card("BASIC:EXECUTE_REMINDER", BASIC_AT), now: "2026-11-21T10:05", note: "시안 규칙" },
      { id: "04-41", label: "토 오전 메뉴판 축제", href: "/", card: card("EXECUTE_REMINDER", "MENU_ORDER:2026-11-21:2026-11-21"), now: "2026-11-21T10:05", prefs: CONNECTED },
      { id: "04-42", label: "일 오후 메뉴판 축제 끝", href: "/", card: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-23:2026-11-23"), now: "2026-11-22T14:05", prefs: DECLINED },
    ],
  },
  {
    group: "네이버 플레이스",
    items: [
      { id: "04-50", label: "메뉴판 카드 (연결 전)", href: "/", card: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-18:2026-11-18"), now: T, prefs: NAVER_OFF },
      { id: "04-51", label: "연결 안내", href: `/naver/connect?plan=${enc("MENU_ORDER:2026-11-18:2026-11-18")}`, prefs: NAVER_OFF },
      { id: "04-52", label: "연결됐어요", href: `/naver/connect?plan=${enc("MENU_ORDER:2026-11-18:2026-11-18")}&view=done`, prefs: CONNECTED },
      { id: "04-53", label: "바꿀 순서 미리 보기", href: `/menu-order/${enc("MENU_ORDER:2026-11-18:2026-11-18")}`, now: T, prefs: CONNECTED },
      { id: "04-54", label: "바꾸는 중", href: `/menu-order/${enc("MENU_ORDER:2026-11-18:2026-11-18")}?view=applying`, prefs: CONNECTED },
      { id: "04-55", label: "바꿨어요", href: `/menu-order/${enc("MENU_ORDER:2026-11-18:2026-11-18")}?view=done`, prefs: CONNECTED },
      { id: "04-56", label: "알아서 바꾼 뒤 알림", href: "/", card: card("EXECUTE_REMINDER", "MENU_ORDER:2026-11-21:2026-11-21"), now: "2026-11-21T10:05", prefs: AUTO },
      { id: "04-57", label: "원래대로 되돌렸어요", href: `/menu-order/${enc("MENU_ORDER:2026-11-18:2026-11-18")}?view=reverted`, prefs: CONNECTED },
      { id: "04-58", label: "설정 네이버 플레이스", href: "/settings/naver", prefs: CONNECTED },
    ],
  },
  {
    group: "인스타 홍보 포스터",
    items: [
      { id: "04-61", label: "메뉴 사진 고르기", href: `/poster/${enc("POSTER:game_031:2026-11-19")}`, now: "2026-11-16T14:05" },
      { id: "04-62", label: "포스터 만드는 중", href: `/poster/${enc("POSTER:game_031:2026-11-19")}?step=making` },
      { id: "04-63", label: "포스터 미리 보기", href: `/poster/${enc("POSTER:game_031:2026-11-19")}?step=preview` },
      { id: "04-64", label: "포스터 글자 고치기", href: `/poster/${enc("POSTER:game_031:2026-11-19")}?step=edit` },
      { id: "04-65", label: "올릴 곳 고르기", href: `/poster/${enc("POSTER:game_031:2026-11-19")}?step=share` },
      { id: "04-66", label: "인스타그램으로 보냈어요", href: `/poster/${enc("POSTER:game_031:2026-11-19")}?step=sent` },
    ],
  },
  {
    group: "해 본 일의 결과",
    items: [
      { id: "04-43", label: "다음 주 월 답글 뒤 다시 주문", href: "/", card: card("NOTICE", "REPLY_RESULT:2026-11-21"), now: "2026-11-23T10:05" },
      { id: "04-44", label: "다음 주 수 불만이 줄었어요", href: "/", card: card("NOTICE", "FIX_RESULT:risk_004"), now: "2026-11-25T10:05" },
    ],
  },
];

/** 계획 항목 → 그 일을 하는 화면 주소 */
function planHref(p: PlanItem): string | null {
  const id = enc(p.plan_id);
  if (p.task_type === "POSTER") return `/poster/${id}`;
  if (p.task_type === "MENU_ORDER") return `/menu-order/${id}`;
  if (p.task_type === "REVISIT_REPLY") return p.revisit_class === "BASIC" ? `/reply/batch/${id}` : `/reply/${id}`;
  if (p.task_type === "REVIEW_FIX") return `/check/${id}`;
  return null;
}

/** testID에 쓸 값: 공백만 빼고 그대로 둔다 (카드 id의 ":"는 그대로) */
const tid = (s: string) => s.replace(/\s+/g, "_");

function Section({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <View className="gap-2">
      <Text className="text-title text-ink" accessibilityRole="header">
        {title}
      </Text>
      {sub ? <Text className="text-small text-ink-2">{sub}</Text> : null}
      {children}
    </View>
  );
}

function SmallButton({ testID, label, on, onPress, flex = true }: { testID: string; label: string; on?: boolean; onPress: () => void; flex?: boolean }) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ selected: !!on }}
      onPress={onPress}
      className={`h-10 items-center justify-center rounded-lg border px-2 active:bg-brand-soft ${flex ? "flex-1" : ""} ${on ? "border-brand bg-brand-soft" : "border-line bg-surface"}`}
    >
      <Text className={`text-small ${on ? "font-bold text-brand" : "text-ink"}`} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

function Row({ testID, children, onPress }: { testID: string; children: ReactNode; onPress: () => void }) {
  return (
    <Pressable testID={testID} accessibilityRole="button" onPress={onPress} className="min-h-10 flex-row items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 active:bg-brand-soft">
      {children}
    </Pressable>
  );
}

function SwitchRow({ label, checked, onChange, testID }: { label: string; checked: boolean; onChange: (v: boolean) => void; testID: string }) {
  return (
    <View className="flex-row items-center justify-between gap-3">
      <Text className="flex-1 text-body text-ink">{label}</Text>
      <Toggle testID={testID} label={label} checked={checked} onChange={onChange} />
    </View>
  );
}

export function DevScreen() {
  const qc = useQueryClient();
  const { data, now, prefs: p } = useHome();
  const flags = devFlags.useValue();
  const savedDrafts = drafts.useValue();
  const [rule, setRule] = useState<ReplyRule>(() => readRule());

  /** 홈과 매출을 처음부터 다시 받게 한다 (저장해 둔 홈 데이터도 지운다) */
  const reload = () => {
    storage.removeItem(HOME_CACHE);
    qc.removeQueries({ queryKey: ["home"] });
    qc.removeQueries({ queryKey: ["sales"] });
  };
  const setFlags = (patch: Partial<DevFlags>, refresh = false) => {
    devFlags.write(patch);
    if (refresh) reload();
  };

  const open = (g: Go) => {
    const before = devFlags.read();
    // 바로 가기는 Figma 화면 한 장의 때를 그대로 만든다. 시각을 정하는 바로 가기는 매장 시나리오와 한 주 모아 보기를 끄고,
    // 메인 가게(국수집) 데이터로 그 시각까지 온 카드만 보여 준다.
    const patch: Partial<DevFlags> = { card: g.card ?? null, offline: false, fresh: false, delay: null, cardNow: null, ...g.flags };
    if (g.now) {
      Object.assign(patch, { ...virtualNow(g.now), persona: null, personaScene: null, allWeek: false });
      if (before.persona !== MAIN_PERSONA.id || before.allWeek) {
        setMockStore(MAIN_PERSONA.store.name, MAIN_PERSONA.store.category);
        reload();
      }
    }
    devFlags.write(patch);
    prefs.write({ ...DEFAULT_PREFS, ...g.prefs });
    signInForReview();
    resetCardState();
    // 끊김, 늦추기를 켜거나 끌 때는 홈과 매출을 처음부터 다시 받는다.
    if (g.flags || before.offline || before.fresh || before.delay !== null) reload();
    if (g.toast) flashToast(g.toast[0], g.toast[1]);
    go(g.href);
  };

  /** 매장 시나리오 고르기: 그 가게 이름과 업종, 그 장면의 시각과 설정으로 홈을 새로 연다. */
  const pickStore = (per: Persona, sc: Scene) => {
    devFlags.write({ persona: per.id, personaScene: sc.id, allWeek: false, ...virtualNow(sc.now), card: null, cardNow: null, offline: false, fresh: false, delay: null });
    prefs.write({ ...DEFAULT_PREFS, ...sc.prefs });
    signInForReview();
    resetCardState();
    setMockStore(per.store.name, per.store.category);
    reload();
    flashToast(per.store.name, `${sc.label}, 할 일 ${sc.cards.length}개`);
    goHome();
  };

  const resetAll = () => {
    storage.clearAll();
    resetCardState();
    resetMockSettings();
    prefs.reset();
    drafts.reset();
    devFlags.reset();
    account.reset();
    setRule(readRule());
    qc.removeQueries();
    flashToast("처음 상태로 돌렸어요", "처음 쓰는 날부터 다시 볼 수 있어요");
  };

  // 지금 가상 시각까지 온 카드 (오늘 화면과 같은 규칙). 카드 기록은 보지 않는다.
  const cards = data ? buildTodayCards(data, now, p, {}, null, savedDrafts) : null;
  // 데모 한 주 카드 전부. 매장 시나리오가 빠뜨린 카드가 있는지 본다.
  const week = data ? buildTodayCards(data, now, p, {}, null, savedDrafts, { all: true }) : null;
  const cardState = useCardState();

  // 데모 주간 타임라인: 오늘 화면이 쓰는 알림 묶음 그대로 보여 준다.
  const plans = new Map(data?.plan.plan_items.map((x) => [x.plan_id, x]) ?? []);
  const timeline = (data?.today.batches ?? []).map((b) => ({
    at: b.slot_at,
    items: b.entries.map((e) => {
      const it = e.plan_id ? plans.get(e.plan_id) : undefined;
      const name = it ? `${it.task_type}${it.revisit_class ? ` ${it.revisit_class}` : ""} ${it.basis.ref_id}` : e.notice_id;
      return `[${KIND_KO[e.notify_kind]}] ${name} (${e.priority})`;
    }),
  }));

  return (
    <SafeAreaView edges={["top", "bottom"]} style={{ flex: 1, backgroundColor: C.paper }}>
      <ScrollView testID="dev-scroll" contentContainerStyle={{ paddingHorizontal: 20, paddingVertical: 16, gap: 24 }}>
        <View className="gap-1">
          <View className="flex-row items-center justify-between">
            <Text className="text-display text-ink">개발용 시뮬레이터</Text>
            <Pressable testID="dev-close" accessibilityRole="button" accessibilityLabel="닫기" onPress={() => back("/")} hitSlop={10}>
              <Text className="text-label font-bold text-brand">닫기</Text>
            </Pressable>
          </View>
          <Text className="text-small text-ink-2" testID="dev-status">
            {USE_MOCK ? "고정 샘플 모드" : "실제 서버 모드 (가상 시각은 고정 샘플에서만 써요)"}, 지금 {monthDay(now)} {weekdayName(now)} {hhmm(now.toISOString())}
            {flags.card ? `\n맨 앞 카드: ${flags.card}` : ""}
          </Text>
        </View>

        <Section title="매장 시나리오" sub="같은 동네(춘천 대학가), 같은 한 주라도 가게마다 할 일이 달라요. 매장과 장면을 누르면 그 가게 할 일 3~6개로 홈을 열어요.">
          <StoreScenarios personaId={flags.persona} sceneId={flags.personaScene} allWeek={flags.allWeek} week={week} onPick={pickStore} />
        </Section>

        <Section title="화면 열기" sub="지금 상태 그대로 열어요">
          <View className="flex-row flex-wrap gap-1.5">
            {(
              [
                ["home", "홈", "/"],
                ["week", "이번 주", "/week"],
                ["sales", "매출", "/sales"],
                ["settings", "설정", "/settings"],
                ["start", "처음 쓰는 날", "/start"],
                ["lock", "잠금 화면", "/lock"],
              ] as const
            ).map(([k, label, href]) => (
              <SmallButton key={k} testID={`dev-link-${k}`} label={label} onPress={() => go(href)} flex={false} />
            ))}
          </View>
          {data && (
            <View className="gap-1">
              <Text className="text-label font-bold text-ink-2">이번 주 할 일 화면</Text>
              {data.plan.plan_items.map((it) => {
                const href = planHref(it);
                if (!href) return null;
                return (
                  <Row key={it.plan_id} testID={`dev-plan-${tid(it.plan_id)}`} onPress={() => go(href)}>
                    <Text className="flex-1 text-small text-ink" numberOfLines={1}>
                      {it.plan_id}
                    </Text>
                    <Text className="text-small text-ink-3">{href.split("/")[1]}</Text>
                  </Row>
                );
              })}
            </View>
          )}
        </Section>

        <Section title="가상 시각" sub="오늘 화면과 매출이 이 시각으로 다시 계산돼요">
          <View className="gap-1.5">
            {DAYS.map((d) => (
              <View key={d} className="flex-row items-center gap-1.5">
                <Text className="w-24 text-small text-ink-2">
                  {monthDay(d)} {weekdayName(d)[0]}
                </Text>
                {SLOTS.map(([t, label]) => (
                  <SmallButton key={t} testID={`dev-now-${d}T${t}`} label={label} on={flags.now === `${d}T${t}`} onPress={() => setFlags(virtualNow(`${d}T${t}`))} />
                ))}
              </View>
            ))}
          </View>
          <SecondaryButton testID="dev-now-default" outline onPress={() => setFlags(virtualNow(null))}>
            {`기본으로 (${monthDay(DEMO_NOW)} 오후 2시 5분)`}
          </SecondaryButton>
        </Section>

        <Section title="문제 상황">
          <SwitchRow
            testID="dev-all-week"
            label="데모 한 주 할 일 28개 모두 홈에 모아 보기"
            checked={flags.allWeek}
            onChange={(v) => {
              // 모아 보기는 메인 가게(국수집) 데이터로 본다
              if (v) setMockStore(MAIN_PERSONA.store.name, MAIN_PERSONA.store.category);
              setFlags({ allWeek: v, cardNow: null }, true);
            }}
          />
          <SwitchRow testID="dev-fail" label="올리기, 바꾸기 실패시키기" checked={flags.fail} onChange={(v) => setFlags({ fail: v })} />
          <SwitchRow testID="dev-offline" label="인터넷 끊김" checked={flags.offline} onChange={(v) => setFlags({ offline: v }, true)} />
          <SwitchRow testID="dev-fresh" label="저장해 둔 홈 데이터 쓰지 않기" checked={flags.fresh} onChange={(v) => setFlags({ fresh: v }, true)} />
          <Text className="text-label text-ink-2">불러오기 늦추기</Text>
          <View className="flex-row gap-1.5">
            {DELAYS.map((d) => (
              <SmallButton key={String(d)} testID={`dev-delay-${d ?? "default"}`} label={d === null ? "기본" : d >= 1000 ? `${d / 1000}초` : `${d}ms`} on={flags.delay === d} onPress={() => setFlags({ delay: d }, true)} />
            ))}
          </View>
        </Section>

        <Section title="답글 시각 규칙" sub="시안 규칙: 좋은 리뷰는 금요일 오후 승인, 토요일 출근 후 올림. 주간, 월간 단골 답글을 넣어요. 서버 규칙: 토요일 10시 승인, 11시 자동 올림.">
          <View className="flex-row gap-2">
            {(
              [
                ["design", "시안 규칙"],
                ["server", "지금 서버 규칙"],
              ] as const
            ).map(([k, label]) => (
              <SmallButton
                key={k}
                testID={`dev-rule-${k}`}
                label={label}
                on={rule === k}
                onPress={() => {
                  storage.setItem(RULE_KEY, k);
                  setRule(k);
                  storage.removeItem(HOME_CACHE);
                  qc.invalidateQueries({ queryKey: ["home"] });
                }}
              />
            ))}
          </View>
        </Section>

        <Section title="이 기기 상태">
          <View className="flex-row flex-wrap gap-1.5">
            {(
              [
                ["default", "기본 (연결 전)", DEFAULT_PREFS],
                ["declined", "직접 바꾸기", { ...DEFAULT_PREFS, ...DECLINED }],
                ["connected", "네이버 연결", { ...DEFAULT_PREFS, ...CONNECTED }],
                ["auto", "알아서 바꾸기", { ...DEFAULT_PREFS, ...AUTO }],
              ] as const
            ).map(([k, label, v]) => (
              <SmallButton key={k} testID={`dev-prefs-${k}`} label={label} onPress={() => prefs.write(v)} flex={false} />
            ))}
          </View>
          <SwitchRow testID="dev-pref-naver" label="네이버 연결됨" checked={p.naverConnected} onChange={(v) => prefs.write({ naverConnected: v, naverAuto: v && p.naverAuto })} />
          <SwitchRow testID="dev-pref-auto" label="메뉴 순서 알아서 바꾸기" checked={p.naverAuto} onChange={(v) => prefs.write({ naverAuto: v, naverConnected: v || p.naverConnected })} />
          <SwitchRow testID="dev-pref-declined" label="네이버 대신 직접 바꾸기로 함" checked={p.naverDeclined} onChange={(v) => prefs.write({ naverDeclined: v })} />
          <SwitchRow testID="dev-pref-onboarded" label="처음 쓰는 날 마침" checked={p.onboarded} onChange={(v) => prefs.write({ onboarded: v })} />
          <SwitchRow testID="dev-pref-notify-off" label="알림 꺼 둠" checked={p.notifyOff} onChange={(v) => prefs.write({ notifyOff: v })} />
          <SwitchRow testID="dev-pref-first-day" label="첫날 카드 아직 안 봄" checked={p.firstDayPending} onChange={(v) => prefs.write({ firstDayPending: v })} />
          <PrimaryButton
            testID="dev-clear-cards"
            onPress={() => {
              resetCardState();
              drafts.reset();
              devFlags.write({ card: null });
              reload();
              flashToast("카드 기록을 지웠어요");
            }}
          >
            카드 기록 지우기
          </PrimaryButton>
          <SecondaryButton testID="dev-reset" outline onPress={resetAll}>
            처음부터 다시 (모두 지우기)
          </SecondaryButton>
        </Section>

        <Section title="지금 시각의 카드" sub="누르면 그 카드를 오늘 화면 맨 앞에 두고 열어요. 카드 기록은 지워져요.">
          {!cards ? (
            <Text className="text-small text-ink-3">홈 데이터를 불러오는 중이에요</Text>
          ) : cards.cards.length === 0 ? (
            <Text className="text-small text-ink-3">이 시각까지 온 카드가 없어요</Text>
          ) : (
            cards.cards.map((c) => (
              <Row
                key={c.id}
                testID={`dev-card-${tid(c.id)}`}
                onPress={() => {
                  devFlags.write({ card: c.id });
                  resetCardState();
                  go("/");
                }}
              >
                <View className="flex-1">
                  <Text className="text-small font-bold text-ink" numberOfLines={2}>
                    {c.title.replace(/\n/g, " ")}
                  </Text>
                  <Text className="text-small text-ink-3" numberOfLines={1}>
                    {c.id}
                  </Text>
                </View>
                {cardState[c.id] ? <Text className="text-small text-ink-3">{cardState[c.id].kind === "done" ? "끝냄" : "미룸"}</Text> : null}
              </Row>
            ))
          )}
        </Section>

        <Section title="Figma 화면 바로 가기" sub="누르면 그 화면에 맞는 시각과 상태로 열어요. 카드 기록은 지워져요.">
          {FIGMA.map((g) => (
            <View key={g.group} className="gap-1">
              <Text className="text-label font-bold text-ink-2">{g.group}</Text>
              {g.items.map((it) => (
                <Row key={it.id} testID={`dev-go-${it.id}`} onPress={() => open(it)}>
                  <Text className="w-16 text-small font-bold text-brand">{it.id}</Text>
                  <Text className="flex-1 text-small text-ink">{it.label}</Text>
                  {it.note ? <Text className="text-small text-ink-3">{it.note}</Text> : null}
                </Row>
              ))}
            </View>
          ))}
        </Section>

        <Section title="데모 주간 알림 타임라인" sub="오늘 화면이 쓰는 알림 묶음 그대로예요. 괄호 안은 우선순위.">
          {timeline.map((t) => (
            <View key={t.at} className="rounded-xl border border-line bg-surface px-3 py-2">
              <Text className="text-label font-bold text-ink">
                {monthDay(t.at)} {weekdayName(t.at)} {hhmm(t.at)}
              </Text>
              {t.items.map((x, i) => (
                <Text key={i} className="text-small text-ink-2">
                  {x}
                </Text>
              ))}
            </View>
          ))}
        </Section>
      </ScrollView>
    </SafeAreaView>
  );
}
