"use client";
// 개발용 시뮬레이터 (docs/frontend_plan.md F5, 고정 샘플 모드 전용).
// Figma 04 화면 바로 가기, 가상 시각, 답글 시각 규칙, 이 기기 상태, 데모 주간 알림 타임라인.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { Toggle } from "@/components/ui/sub";
import { USE_MOCK } from "@/lib/api";
import { resetCardState } from "@/lib/cardState";
import { drafts, flashToast, prefs, type Prefs } from "@/lib/localStore";
import { DEMO_NOW, NOW_KEY, hhmm, monthDay, weekdayName } from "@/lib/time";
import { useHome } from "@/lib/useHome";
import { readRule, RULE_KEY, type ReplyRule } from "@/mocks/extras";
import type { NotifyKind } from "@/types/contract";

const KIND_KO: Record<NotifyKind, string> = { APPROVAL_REQUEST: "승인 요청", EXECUTE_REMINDER: "실행 알림", PREVIEW: "예고", NOTICE: "알림" };
const DAYS = ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22", "2026-11-23", "2026-11-25"];
const SLOTS = [
  ["10:05", "출근 후"],
  ["14:05", "오후"],
  ["21:35", "마감 전"],
] as const;

const enc = encodeURIComponent;
const NAVER_OFF: Partial<Prefs> = { naverConnected: false, naverAuto: false, naverDeclined: false };
const DECLINED: Partial<Prefs> = { naverConnected: false, naverAuto: false, naverDeclined: true };
const CONNECTED: Partial<Prefs> = { naverConnected: true, naverAuto: false, naverDeclined: false };
const AUTO: Partial<Prefs> = { naverConnected: true, naverAuto: true, naverDeclined: false };

type Go = { id: string; label: string; href: string; now?: string; prefs?: Partial<Prefs>; toast?: [string, string]; note?: string };

const card = (kind: string, id: string) => `/?card=${enc(`${kind}:${id}`)}`;
const BASIC_AT = "2026-11-21T10:00:00+09:00";

/** Figma 04 섹션의 모든 화면 → 그 화면을 여는 주소와 상태 */
const FIGMA: { group: string; items: Go[] }[] = [
  {
    group: "처음 쓰는 날",
    items: [
      { id: "04-1", label: "왜 도나인가", href: "/start" },
      { id: "04-2", label: "우리 가게 찾기", href: "/start/store" },
      { id: "04-2b", label: "가게를 못 찾았을 때", href: `/start/store?q=${enc("홍길동 치킨")}` },
      { id: "04-3", label: "알림 받을 때 고르기", href: "/start/notify-time" },
      { id: "04-3b", label: "알림 켜 주세요", href: "/start/notify-on" },
      { id: "04-4n", label: "알림이 꺼진 채로 들어왔을 때", href: "/", now: "2026-11-17T14:05", prefs: { notifyOff: true } },
      { id: "04-4f", label: "첫날 새 리뷰가 없을 때", href: "/", now: "2026-11-16T09:30", prefs: { firstDayPending: true } },
    ],
  },
  {
    group: "매일: 화요일 오후",
    items: [
      { id: "04-23", label: "잠금 화면에서 시작", href: "/lock", now: "2026-11-17T14:05" },
      { id: "04-4", label: "오늘 할 일 하나", href: card("APPROVAL_REQUEST", "REVISIT_REPLY:rv_118:2026-11-17"), now: "2026-11-17T14:05" },
      { id: "04-5", label: "답글 보고 올리기", href: `/reply/${enc("REVISIT_REPLY:rv_118:2026-11-17")}`, now: "2026-11-17T14:05" },
      { id: "04-5s", label: "답글을 올렸어요 띠", href: card("APPROVAL_REQUEST", "REVIEW_FIX:risk_004:2026-11-17"), now: "2026-11-17T14:05", toast: ["답글을 올렸어요", "배달의민족에서 볼 수 있어요"] },
      { id: "04-5f", label: "답글을 못 올렸을 때", href: `/reply/${enc("REVISIT_REPLY:rv_118:2026-11-17")}?view=failed`, now: "2026-11-17T14:05" },
      { id: "04-10", label: "위험 신호 (같은 불만 반복)", href: card("APPROVAL_REQUEST", "REVIEW_FIX:risk_004:2026-11-17"), now: "2026-11-17T14:05" },
      { id: "04-11", label: "주간 단골 답글", href: card("APPROVAL_REQUEST", "REVISIT_REPLY:rv_102:2026-11-18"), now: "2026-11-17T14:05", note: "시안 규칙" },
      { id: "04-12", label: "메뉴판 계절 전환 (직접)", href: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-18:2026-11-18"), now: "2026-11-17T14:05", prefs: DECLINED },
      { id: "04-6", label: "다 했어요", href: "/", now: "2026-11-24T15:00" },
    ],
  },
  {
    group: "매일: 옆길",
    items: [
      { id: "04-22", label: "나중에 다시 알림 시트", href: "/?sheet=later", now: "2026-11-17T14:05" },
      { id: "04-21", label: "답글 고쳐 쓰기", href: `/reply/${enc("REVISIT_REPLY:rv_118:2026-11-17")}/edit`, now: "2026-11-17T14:05" },
      { id: "04-24", label: "배달 지연 점검 목록", href: `/check/${enc("REVIEW_FIX:risk_004:2026-11-17")}`, now: "2026-11-17T14:05" },
      { id: "04-11r", label: "주간 단골 답글 보기", href: `/reply/${enc("REVISIT_REPLY:rv_102:2026-11-18")}`, now: "2026-11-17T14:05", note: "시안 규칙" },
    ],
  },
  {
    group: "홈 불러오기와 문제가 생겼을 때",
    items: [
      { id: "04-8", label: "처음 (0.3초부터)", href: "/?fresh=1&delay=60000", now: "2026-11-17T14:05", note: "열고 바로" },
      { id: "04-8c", label: "3초가 넘을 때", href: "/?fresh=1&delay=60000", now: "2026-11-17T14:05", note: "3초 기다리기" },
      { id: "04-8d", label: "10초가 넘을 때", href: "/?fresh=1&delay=60000", now: "2026-11-17T14:05", note: "10초 기다리기" },
      { id: "04-8b", label: "다시 열 때 (지난 할 일 먼저)", href: "/?delay=8000", now: "2026-11-17T14:05" },
      { id: "04-9", label: "인터넷이 끊겼을 때", href: "/?offline=1", now: "2026-11-17T14:05" },
    ],
  },
  {
    group: "05 시안: 새로 바뀐 화면",
    items: [
      { id: "05-4", label: "카드에서 바로 답글 달기", href: card("APPROVAL_REQUEST", "REVISIT_REPLY:rv_118:2026-11-17"), now: "2026-11-17T14:05" },
      { id: "05-12n", label: "메뉴판 카드 (네이버 미리 보기)", href: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-18:2026-11-18"), now: "2026-11-17T14:05", prefs: CONNECTED },
      { id: "05-55s", label: "내일 바꿔 둘게요", href: `/menu-order/${enc("MENU_ORDER:2026-11-18:2026-11-18")}?apply=1`, now: "2026-11-17T14:05", prefs: CONNECTED },
      { id: "05-31n", label: "포스터 카드 (포스터 미리 보기)", href: card("EXECUTE_REMINDER", "POSTER:game_031:2026-11-19"), now: "2026-11-17T14:05" },
      { id: "05-7-수", label: "이번 주 날씨와 기온", href: "/week?day=2026-11-18", now: "2026-11-17T14:05" },
      { id: "05-2h", label: "언제 장사하세요?", href: "/start/hours" },
      { id: "05-2i", label: "장사 시간 확인", href: "/start/hours/confirm?p=LUNCH_DINNER" },
      { id: "05-3", label: "장사 시간에 맞춘 알림 시간", href: "/start/notify-time" },
      { id: "05-19h", label: "설정 장사 시간", href: "/settings/hours" },
      { id: "05-70", label: "매출 첫 화면", href: "/sales", now: "2026-11-17T14:05" },
      { id: "05-71", label: "이번 주와 지난주", href: "/sales/week", now: "2026-11-17T14:05" },
      { id: "05-72", label: "메뉴별", href: "/sales/menu", now: "2026-11-17T14:05" },
      { id: "05-73", label: "시간대와 요일", href: "/sales/time", now: "2026-11-17T14:05" },
      { id: "05-74", label: "배달앱과 단골", href: "/sales/channel", now: "2026-11-17T14:05" },
      { id: "05-75", label: "달별 흐름", href: "/sales/month", now: "2026-11-17T14:05" },
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
      { id: "04-16", label: "월요일 이번 주 미리 보기", href: card("PREVIEW", "WEEKLY_PREVIEW:2026-11-16"), now: "2026-11-16T10:05" },
      { id: "04-13", label: "경기 포스터 만들기", href: card("APPROVAL_REQUEST", "POSTER:game_031:2026-11-19"), now: "2026-11-16T14:05" },
      { id: "04-14", label: "실행 알림 메뉴판 계절", href: card("EXECUTE_REMINDER", "MENU_ORDER:2026-11-18:2026-11-18"), now: "2026-11-18T10:05", prefs: DECLINED },
      { id: "04-15", label: "매출 이상 알림", href: card("NOTICE", "SALES_ANOMALY:2026-11-17:LUNCH"), now: "2026-11-18T10:05" },
      { id: "04-17", label: "좋은 리뷰 답글 묶음", href: card("BASIC:APPROVAL_REQUEST", BASIC_AT), now: "2026-11-20T14:05", note: "시안 규칙" },
      { id: "04-25", label: "좋은 리뷰 답글 4개", href: `/reply/batch/${enc("REVISIT_REPLY:rv_109:2026-11-21")}`, now: "2026-11-20T14:05" },
      { id: "04-25b", label: "좋은 리뷰 답글 하나씩", href: `/reply/batch/${enc("REVISIT_REPLY:rv_109:2026-11-21")}?one=0`, now: "2026-11-20T14:05" },
    ],
  },
  {
    group: "이번 주",
    items: [
      { id: "04-7", label: "이번 주 (오늘 화요일)", href: "/week", now: "2026-11-17T14:05" },
      { id: "04-7-월", label: "월요일을 눌렀을 때", href: "/week?day=2026-11-16", now: "2026-11-17T14:05" },
      { id: "04-7-수", label: "수요일", href: "/week?day=2026-11-18", now: "2026-11-17T14:05" },
      { id: "04-7-목", label: "목요일", href: "/week?day=2026-11-19", now: "2026-11-17T14:05" },
      { id: "04-7-금", label: "금요일", href: "/week?day=2026-11-20", now: "2026-11-17T14:05" },
      { id: "04-7-토", label: "토요일", href: "/week?day=2026-11-21", now: "2026-11-17T14:05" },
      { id: "04-7-일", label: "일요일", href: "/week?day=2026-11-22", now: "2026-11-17T14:05" },
      { id: "04-7L", label: "불러오는 중", href: "/week?fresh=1&delay=60000", now: "2026-11-17T14:05" },
      { id: "04-7E", label: "인터넷이 끊겼을 때", href: "/week?offline=1", now: "2026-11-17T14:05" },
    ],
  },
  {
    group: "이번 주: 같이 하면 좋은 일",
    items: [
      { id: "04-18", label: "목요일 저녁 자세히", href: "/week/game_031", now: "2026-11-17T14:05" },
      { id: "04-28", label: "메뉴판 경기", href: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-19:2026-11-19"), now: "2026-11-18T14:05", prefs: DECLINED },
      { id: "04-26", label: "축제 포스터 만들기", href: card("APPROVAL_REQUEST", "POSTER:event_012:2026-11-21"), now: "2026-11-18T14:05" },
      { id: "04-18b", label: "주말 축제 자세히", href: "/week/event_012", now: "2026-11-17T14:05" },
      { id: "04-27", label: "메뉴판 축제", href: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-21:2026-11-21"), now: "2026-11-20T14:05", prefs: DECLINED },
    ],
  },
  {
    group: "데모 주간 나머지 알림",
    items: [
      { id: "04-31", label: "화 오전 경기 포스터 올리기", href: card("EXECUTE_REMINDER", "POSTER:game_031:2026-11-19"), now: "2026-11-17T10:05" },
      { id: "04-32", label: "수 오후 주간 단골 답글", href: card("EXECUTE_REMINDER", "REVISIT_REPLY:rv_102:2026-11-18"), now: "2026-11-18T14:05", note: "시안 규칙" },
      { id: "04-33", label: "목 오전 메뉴판 경기", href: card("EXECUTE_REMINDER", "MENU_ORDER:2026-11-19:2026-11-19"), now: "2026-11-19T10:05", prefs: CONNECTED },
      { id: "04-34", label: "목 오전 축제 포스터 올리기", href: card("EXECUTE_REMINDER", "POSTER:event_012:2026-11-21"), now: "2026-11-19T10:05" },
      { id: "04-35", label: "목 오후 월간 단골 답글", href: card("APPROVAL_REQUEST", "REVISIT_REPLY:rv_087:2026-11-20"), now: "2026-11-19T14:05", note: "시안 규칙" },
      { id: "04-35r", label: "월간 단골 답글 보기", href: `/reply/${enc("REVISIT_REPLY:rv_087:2026-11-20")}`, now: "2026-11-19T14:05", note: "시안 규칙" },
      { id: "04-36", label: "목 오후 메뉴판 경기 끝", href: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-20:2026-11-20"), now: "2026-11-19T14:05", prefs: DECLINED },
      { id: "04-37", label: "금 오전 메뉴판 원래대로", href: card("EXECUTE_REMINDER", "MENU_ORDER:2026-11-20:2026-11-20"), now: "2026-11-20T10:05", prefs: CONNECTED },
      { id: "04-38", label: "금 오후 월간 단골 답글", href: card("EXECUTE_REMINDER", "REVISIT_REPLY:rv_087:2026-11-20"), now: "2026-11-20T14:05", note: "시안 규칙" },
      { id: "04-39", label: "금 밤 빠른 응대 맛 불만", href: card("APPROVAL_REQUEST", "REVISIT_REPLY:rv_131:2026-11-20"), now: "2026-11-20T21:35" },
      { id: "04-39r", label: "맛 불만 사과 답글", href: `/reply/${enc("REVISIT_REPLY:rv_131:2026-11-20")}`, now: "2026-11-20T21:35" },
      { id: "04-40", label: "토 오전 좋은 리뷰 4개 올리기", href: card("BASIC:EXECUTE_REMINDER", BASIC_AT), now: "2026-11-21T10:05", note: "시안 규칙" },
      { id: "04-41", label: "토 오전 메뉴판 축제", href: card("EXECUTE_REMINDER", "MENU_ORDER:2026-11-21:2026-11-21"), now: "2026-11-21T10:05", prefs: CONNECTED },
      { id: "04-42", label: "일 오후 메뉴판 축제 끝", href: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-23:2026-11-23"), now: "2026-11-22T14:05", prefs: DECLINED },
    ],
  },
  {
    group: "네이버 플레이스",
    items: [
      { id: "04-50", label: "메뉴판 카드 (연결 전)", href: card("APPROVAL_REQUEST", "MENU_ORDER:2026-11-18:2026-11-18"), now: "2026-11-17T14:05", prefs: NAVER_OFF },
      { id: "04-51", label: "연결 안내", href: `/naver/connect?plan=${enc("MENU_ORDER:2026-11-18:2026-11-18")}`, prefs: NAVER_OFF },
      { id: "04-52", label: "연결됐어요", href: `/naver/connect?plan=${enc("MENU_ORDER:2026-11-18:2026-11-18")}&view=done`, prefs: CONNECTED },
      { id: "04-53", label: "바꿀 순서 미리 보기", href: `/menu-order/${enc("MENU_ORDER:2026-11-18:2026-11-18")}`, now: "2026-11-17T14:05", prefs: CONNECTED },
      { id: "04-54", label: "바꾸는 중", href: `/menu-order/${enc("MENU_ORDER:2026-11-18:2026-11-18")}?view=applying`, prefs: CONNECTED },
      { id: "04-55", label: "바꿨어요", href: `/menu-order/${enc("MENU_ORDER:2026-11-18:2026-11-18")}?view=done`, prefs: CONNECTED },
      { id: "04-56", label: "알아서 바꾼 뒤 알림", href: card("EXECUTE_REMINDER", "MENU_ORDER:2026-11-21:2026-11-21"), now: "2026-11-21T10:05", prefs: AUTO },
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
      { id: "04-43", label: "다음 주 월 답글 뒤 다시 주문", href: card("NOTICE", "REPLY_RESULT:2026-11-21"), now: "2026-11-23T10:05" },
      { id: "04-44", label: "다음 주 수 불만이 줄었어요", href: card("NOTICE", "FIX_RESULT:risk_004"), now: "2026-11-25T10:05" },
    ],
  },
];

/** 화면이 아닌 Figma 프레임 */
const BOARDS = ["04-0 원칙 보드", "04-8 규칙 (홈 불러오기 규칙 보드)", "04-7A, 04-7B, 04-7C (이번 주 시안 고르기, C를 04-7로 구현)", "04-60 자리 (포스터는 카드에서 시작한다는 안내)"];

const DEFAULT_PREFS: Partial<Prefs> = { onboarded: true, notifyOff: false, firstDayPending: false, ...NAVER_OFF };

/** 가상 시각과 캐시를 처음부터 다시 읽게 하려고 페이지를 새로 연다. */
function hardGo(path: string) {
  window.location.assign(new URL(path, window.location.origin).toString());
}

function open(g: Go) {
  if (g.now) localStorage.setItem(NOW_KEY, g.now);
  prefs.write({ ...DEFAULT_PREFS, ...g.prefs });
  resetCardState();
  if (g.toast) flashToast(g.toast[0], g.toast[1]);
  hardGo(g.href);
}

export function DevScreen() {
  const qc = useQueryClient();
  const { data, now, mounted, prefs: p } = useHome();
  const [delay, setDelay] = useState(() => (typeof window === "undefined" ? "600" : localStorage.getItem("dona.delay") ?? "600"));
  const [rule, setRule] = useState<ReplyRule>(() => readRule());

  const setNow = (iso: string | null) => {
    if (iso) localStorage.setItem(NOW_KEY, iso);
    else localStorage.removeItem(NOW_KEY);
    hardGo("/");
  };
  const clearCache = () => {
    qc.removeQueries({ queryKey: ["home"] });
    localStorage.removeItem("dona.home.v3");
  };

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
    <main className="flex flex-col gap-6 px-5 py-6">
      <header>
        <h1 className="text-display">개발용 시뮬레이터</h1>
        <p className="text-small text-ink-2">
          {USE_MOCK ? "고정 샘플 모드" : "실제 서버 모드 (가상 시각은 고정 샘플에서만 써요)"}, 지금 {mounted ? `${monthDay(now)} ${weekdayName(now)} ${hhmm(now.toISOString())}` : ""}
        </p>
      </header>

      <section>
        <h2 className="text-title">Figma 04 화면 바로 가기</h2>
        <p className="mb-2 text-small text-ink-2">누르면 그 화면에 맞는 시각과 상태로 열어요. 카드 기록은 지워져요.</p>
        {FIGMA.map((g) => (
          <div key={g.group} className="mb-3">
            <h3 className="mb-1 text-label font-bold text-ink-2">{g.group}</h3>
            <ul className="flex flex-col gap-1">
              {g.items.map((it) => (
                <li key={it.id}>
                  <button type="button" onClick={() => open(it)} className="flex w-full items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-left text-small active:bg-brand-soft">
                    <span className="w-14 shrink-0 font-bold text-brand">{it.id}</span>
                    <span className="flex-1">{it.label}</span>
                    {it.note && <span className="text-ink-3">{it.note}</span>}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <p className="text-small text-ink-3">화면이 아닌 프레임: {BOARDS.join(", ")}</p>
      </section>

      <section>
        <h2 className="mb-2 text-title">답글 시각 규칙</h2>
        <div className="flex gap-2">
          {(
            [
              ["design", "시안 규칙"],
              ["server", "지금 서버 규칙"],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              type="button"
              onClick={() => {
                localStorage.setItem(RULE_KEY, k);
                setRule(k);
                clearCache();
                hardGo("/dev");
              }}
              className={`h-11 flex-1 rounded-xl border text-small ${rule === k ? "border-brand bg-brand-soft font-bold" : "border-line bg-surface"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="mt-1 text-small text-ink-3">
          시안 규칙: 좋은 리뷰는 금요일 오후 승인, 토요일 출근 후 올림. 주간, 월간 단골 답글을 넣어요. 서버 규칙: 토요일 10시 승인, 11시 자동 올림.
        </p>
      </section>

      <section>
        <h2 className="mb-2 text-title">가상 시각</h2>
        <div className="flex flex-col gap-1.5">
          {DAYS.map((d) => (
            <div key={d} className="flex items-center gap-1.5">
              <span className="w-24 text-small text-ink-2">
                {monthDay(d)} {weekdayName(d)[0]}
              </span>
              {SLOTS.map(([t, label]) => (
                <button key={t} type="button" onClick={() => setNow(`${d}T${t}`)} className="h-9 flex-1 rounded-lg border border-line bg-surface text-small active:bg-brand-soft">
                  {label}
                </button>
              ))}
            </div>
          ))}
        </div>
        <div className="mt-2">
          <SecondaryButton outline onClick={() => setNow(null)}>
            기본으로 ({monthDay(DEMO_NOW)} 오후 2시 5분)
          </SecondaryButton>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-title">이 기기 상태</h2>
        <label className="flex items-center justify-between text-body">
          네이버 연결됨
          <Toggle label="네이버 연결됨" checked={p.naverConnected} onChange={(v) => prefs.write({ naverConnected: v, naverAuto: v && p.naverAuto })} />
        </label>
        <label className="flex items-center justify-between text-body">
          메뉴 순서 알아서 바꾸기
          <Toggle label="알아서 바꾸기" checked={p.naverAuto} onChange={(v) => prefs.write({ naverAuto: v, naverConnected: v || p.naverConnected })} />
        </label>
        <label className="flex items-center justify-between text-body">
          네이버 대신 직접 바꾸기로 함
          <Toggle label="직접 바꾸기" checked={p.naverDeclined} onChange={(v) => prefs.write({ naverDeclined: v })} />
        </label>
        <label className="flex items-center justify-between text-body">
          알림 꺼 둠
          <Toggle label="알림 꺼 둠" checked={p.notifyOff} onChange={(v) => prefs.write({ notifyOff: v })} />
        </label>
        <label className="flex items-center justify-between text-body">
          불러오기 늦추기 (ms)
          <input
            value={delay}
            inputMode="numeric"
            onChange={(e) => {
              setDelay(e.target.value);
              localStorage.setItem("dona.delay", e.target.value);
            }}
            className="h-10 w-24 rounded-lg border border-line bg-surface px-2 text-right"
          />
        </label>
        <SecondaryButton
          outline
          onClick={async () => {
            if (typeof Notification === "undefined") return flashToast("이 브라우저는 알림을 못 보내요");
            const res = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
            if (res !== "granted") return flashToast("브라우저에서 알림을 허용해 주세요");
            new Notification("도나", { body: "배달이 늦었다는 리뷰가 왔어요. 사과 답글을 써 뒀어요.", icon: "/donna/b3-2.png" });
          }}
        >
          휴대폰 알림 보내 보기
        </SecondaryButton>
        <PrimaryButton
          onClick={() => {
            resetCardState();
            drafts.reset();
            clearCache();
            hardGo("/");
          }}
        >
          카드 기록 지우기
        </PrimaryButton>
        <SecondaryButton
          outline
          onClick={() => {
            prefs.reset();
            resetCardState();
            hardGo("/start");
          }}
        >
          처음 쓰는 날부터 다시
        </SecondaryButton>
      </section>

      <section>
        <h2 className="mb-1 text-title">데모 주간 알림 타임라인</h2>
        <p className="mb-2 text-small text-ink-2">오늘 화면이 쓰는 알림 묶음 그대로예요. 괄호 안은 우선순위. docs/frontend_plan.md 4장 정답표와 맞춰 봐요.</p>
        <ol className="flex flex-col gap-2">
          {timeline.map((t) => (
            <li key={t.at} className="rounded-xl border border-line bg-surface px-3 py-2">
              <p className="text-label font-bold">
                {monthDay(t.at)} {weekdayName(t.at)} {hhmm(t.at)}
              </p>
              <ul>
                {t.items.map((x, i) => (
                  <li key={i} className="text-small text-ink-2">
                    {x}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
