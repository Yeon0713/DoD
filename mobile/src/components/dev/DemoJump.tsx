// 개발자 대시보드 "시연" 탭이 휴대폰 틀에 여는 입구 (/demo-jump). 개발 빌드에서만 열린다.
// 대시보드는 서버 시계를 시연 단계의 시각으로 옮긴 뒤 이 주소에 값을 붙여 연다. 대시보드(8000)와 앱(8081)은
// 주소가 달라 저장 공간을 같이 쓰지 못해서 주소로 넘긴다. 이 화면은 값을 이 기기에 저장하고 목표 화면으로 바로 넘어간다.
//
// 주소 값
//   to        열 화면 ("/", "/reply/...", "/start/phone" ...)
//   store     가게 id (s001 ...)
//   card      홈과 "오늘 할 일 하나"에서 맨 앞으로 꺼낼 카드 id
//   naver     네이버 연결 상태: off(연결 전) | declined(직접 바꾸기로 함) | connected | auto(알아서 바꾸기)
//   signed    로그인 상태: in(기본, 네이버로 가입하고 처음 설정 마침) | phone(휴대폰으로 가입, 처음 설정 마침)
//             | out(처음 온 사장님) | naver_new / phone_new(가입만 하고 처음 설정 중) | returning(가입했고 로그아웃)
//   notify_off  "1" 이면 알림을 꺼 둔 채로 들어온 사장님
//   done      all(오늘 온 카드를 모두 끝냄) | snooze(하나만 미뤄 두고 나머지 끝냄) | 카드 id(그 카드만 끝냄)
//   toast     "제목|설명" 띠를 하나 띄운다
//   naver_demo  "1" 이면 앱 데모 테스트 모드를 켠다. 네이버로 시작하기가 서버의 네이버 로그인으로 간다
//               (서버에 네이버 키가 없으면 서버가 그리는 임시 네이버 로그인 화면). 시작 화면 ☰ 메뉴의 그 스위치다
import { useQueryClient } from "@tanstack/react-query";
import { Redirect, router, useLocalSearchParams, type Href } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { account, type Account } from "@/lib/account";
import { markDone, resetCardState, snooze } from "@/lib/cardState";
import { demoMode } from "@/lib/naverDemo";
import { devFlags } from "@/lib/dev";
import { flashToast, prefs, type Prefs } from "@/lib/localStore";
import { storage } from "@/lib/storage";
import { currentNow } from "@/lib/time";
import { useTodayCards } from "@/lib/useHome";
import tokens from "@/theme/tokens.json";

const SHOW_DEV = __DEV__ || process.env.EXPO_PUBLIC_SHOW_DEV === "true";
const HOME_CACHE = "dona.home.v3";
const EXAMPLE_PHONE = "01012345678"; // 예시 번호 (진짜 번호 아님)
const SNOOZE_HOURS = 3;

type Params = { to?: string; store?: string; card?: string; naver?: string; signed?: string; notify_off?: string; done?: string; toast?: string; naver_demo?: string };

const NAVER: Record<string, Pick<Prefs, "naverConnected" | "naverAuto" | "naverDeclined">> = {
  off: { naverConnected: false, naverAuto: false, naverDeclined: false },
  declined: { naverConnected: false, naverAuto: false, naverDeclined: true },
  connected: { naverConnected: true, naverAuto: false, naverDeclined: false },
  auto: { naverConnected: true, naverAuto: true, naverDeclined: false },
};

/** 로그인 상태 → 계정의 가입 방법과 처음 설정을 마쳤는지 */
const SIGNED: Record<string, { method: Account["method"]; onboarded: boolean }> = {
  in: { method: "naver", onboarded: true },
  phone: { method: "phone", onboarded: true },
  out: { method: null, onboarded: false },
  naver_new: { method: "naver", onboarded: false },
  phone_new: { method: "phone", onboarded: false },
  returning: { method: null, onboarded: true },
};

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? undefined;

/** 이 기기 상태를 시연 단계에 맞게 처음부터 다시 둔다. */
function applyState(p: Params) {
  const signed = SIGNED[p.signed ?? "in"] ?? SIGNED.in;
  storage.removeItem(HOME_CACHE);
  account.write({ method: signed.method, phone: signed.method === "phone" ? EXAMPLE_PHONE : null, storeId: p.store ?? null });
  prefs.write({ onboarded: signed.onboarded, notifyOff: p.notify_off === "1", firstDayPending: false, ...(NAVER[p.naver ?? "off"] ?? NAVER.off) });
  devFlags.write({ card: p.card ?? null, cardNow: null, now: null, offline: false, fresh: false, delay: null, allWeek: false, persona: null, personaScene: null });
  resetCardState();
  if (p.naver_demo === "1") demoMode.write({ on: true });
}

function finish(p: Params) {
  const [title, sub] = (p.toast ?? "").split("|");
  if (title) flashToast(title, sub || undefined);
  router.replace((p.to || "/") as Href);
}

/** done=all / snooze: 오늘 온 카드를 불러온 뒤 끝낸 것으로 두고 넘어간다. */
function FinishCards({ params }: { params: Params }) {
  const { view, isError } = useTodayCards();
  useEffect(() => {
    if (!view && !isError) return;
    const ids = view?.cards.map((c) => c.id) ?? [];
    ids.forEach((id, i) => {
      if (params.done === "snooze" && i === 0) snooze(id, new Date(currentNow().getTime() + SNOOZE_HOURS * 3600 * 1000).toISOString());
      else markDone(id);
    });
    finish(params);
  }, [view, isError, params]);
  return <Waiting text="오늘 카드를 불러와 끝낸 것으로 두는 중" />;
}

function Waiting({ text }: { text: string }) {
  return (
    <View style={{ flex: 1, alignItems: "center", justifyContent: "center", gap: 12 }}>
      <ActivityIndicator color={tokens.colors.brand} />
      <Text className="text-small text-ink-2">{text}</Text>
    </View>
  );
}

export function DemoJump() {
  const raw = useLocalSearchParams<Params>();
  const qc = useQueryClient();
  // 이 기기 상태는 화면을 처음 그릴 때 한 번만 바꾼다. 그래야 아래 FinishCards 가 바뀐 가게와 카드로 오늘 카드를 불러온다.
  const [params] = useState<Params>(() => {
    const p = Object.fromEntries(Object.entries(raw).map(([k, v]) => [k, one(v)])) as Params;
    if (SHOW_DEV) {
      qc.clear();
      applyState(p);
    }
    return p;
  });
  const bulk = params.done === "all" || params.done === "snooze";

  useEffect(() => {
    if (!SHOW_DEV || bulk) return;
    if (params.done) markDone(params.done, { note: "답글을 올렸어요" });
    finish(params);
  }, [params, bulk]);

  if (!SHOW_DEV) return <Redirect href="/" />;
  if (bulk) return <FinishCards params={params} />;
  return <Waiting text="시연 화면을 여는 중" />;
}
