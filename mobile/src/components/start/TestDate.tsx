// 시험 날짜 (데모 테스트 모드, 서버를 쓸 때). 시작 화면 ☰ 메뉴와 설정 맨 아래에서 연다.
// 시험 주간 데이터가 있는 가게(지금은 초옹장 s005, 2026-10-05 ~ 10-11)의 알림 시각마다 그때 홈에 오는 할 일을 보여 주고,
// 고르면 서버 시계를 그 시각 5분 뒤로 옮긴다. 서버: GET /api/dev_tools/test_week, POST /api/dev_tools/test_go (docs/test-week.md)
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ActivityIndicator, Pressable, View } from "react-native";
import { Icon } from "@/components/icons/Icon";
import { SecondaryButton } from "@/components/ui/parts";
import { Sheet } from "@/components/ui/Sheet";
import { Text } from "@/components/ui/Text";
import { account } from "@/lib/account";
import { USE_MOCK } from "@/lib/api";
import { flashToast } from "@/lib/localStore";
import { demoMode } from "@/lib/naverDemo";
import { BASE_URL } from "@/lib/server";
import { refreshServerClock } from "@/lib/storage";
import tokens from "@/theme/tokens.json";

const C = tokens.colors;
/** 로그인하기 전(시작 화면 ☰)에는 시험 데이터가 있는 초옹장을 본다 */
const DEFAULT_STORE = "s005";

type Stop = { at: string; day: string; slot_name: string; time: string; tasks?: string[] };
type FeatureStep = Stop & { label: string; reason: string };
/** Killer Feature 하나와 시연 단계 (① 고객 재방문 유도 ...) */
type Feature = { key: string; mark: string; name: string; flow: string; steps: FeatureStep[] };
type TestWeek = { store_id: string; store_name: string; start: string; end: string; now: string; stops: Stop[]; features: Feature[] };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body?.error?.message ?? "서버가 답하지 않아요");
  return body as T;
}

/** 시험 날짜를 쓸 수 있는지: 데모 테스트 모드이고 서버를 쓸 때 */
export function useTestDateAvailable(): boolean {
  return demoMode.useValue().on && !USE_MOCK;
}

const shortTime = (iso: string) => {
  const [date, time] = iso.split("T");
  const [, m, d] = date.split("-").map(Number);
  return `${m}/${d} ${time.slice(0, 5)}`;
};

export function TestDateSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const storeId = account.useValue().storeId ?? DEFAULT_STORE;
  const [moving, setMoving] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const week = useQuery({
    queryKey: ["test-week", storeId],
    queryFn: () => call<TestWeek>(`/api/dev_tools/test_week?store_id=${encodeURIComponent(storeId)}`),
    enabled: open,
    staleTime: 0,
    retry: false,
  });

  const moved = async (title: string) => {
    await refreshServerClock();
    await qc.invalidateQueries();
    flashToast(title);
    onClose();
  };

  const goTo = async (stop: Stop) => {
    setMoving(stop.at);
    setFailed(null);
    try {
      await call("/api/dev_tools/test_go", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ store_id: storeId, at: stop.at }) });
      await moved(`${stop.day} ${stop.slot_name} ${stop.time}로 옮겼어요`);
    } catch (e) {
      setFailed(e instanceof Error ? e.message : "옮기지 못했어요");
    } finally {
      setMoving(null);
    }
  };

  const reset = async () => {
    setMoving("reset");
    setFailed(null);
    try {
      await call(`/api/dev_tools/demo_clock_reset?store_id=${encodeURIComponent(storeId)}`, { method: "POST" });
      await moved("실제 시각으로 돌렸어요");
    } catch (e) {
      setFailed(e instanceof Error ? e.message : "돌리지 못했어요");
    } finally {
      setMoving(null);
    }
  };

  const w = week.data;
  const days = w ? [...new Set(w.stops.map((s) => s.day))] : [];
  return (
    <Sheet open={open} onClose={onClose} title="시험 날짜">
      {week.isPending ? (
        <View className="items-center gap-3 py-8" accessibilityLiveRegion="polite">
          <ActivityIndicator color={C.brand} />
          <Text className="text-small text-ink-2">그 주에 도나가 준비할 것을 계산하고 있어요 (처음엔 몇 초 걸려요)</Text>
        </View>
      ) : week.isError || !w ? (
        <Text accessibilityRole="alert" className="text-body text-urgent">
          {week.error instanceof Error ? week.error.message : "시험 주간을 읽지 못했어요"}
        </Text>
      ) : (
        <View className="gap-4">
          <View className="gap-0.5">
            <Text className="text-body font-bold text-ink">{`${w.store_name} 시험 주간`}</Text>
            <Text className="text-small text-ink-2">{`고르면 서버 시계를 그 알림 5분 뒤로 옮겨요 · 지금 서버 ${shortTime(w.now)}`}</Text>
          </View>
          {/* Killer Feature 시연 순서: 기능마다 그 기능이 보이는 알림 시각으로 바로 옮긴다 */}
          <View testID="test-date-features" className="gap-2.5">
            <Text className="text-label font-bold text-ink-2">Killer Feature 시연</Text>
            {(w.features ?? []).map((f) => (
              <View key={f.key} className="gap-2 rounded-2xl border border-line bg-paper p-3.5">
                <Text className="text-body font-bold text-ink">{`${f.mark} ${f.name}`}</Text>
                <Text className="text-small text-ink-3">{f.flow}</Text>
                {f.steps.length === 0 ? <Text className="text-small text-ink-3">이 주에는 없어요</Text> : null}
                {f.steps.map((st) => (
                  <Pressable
                    key={`${f.key}-${st.at}-${st.label}`}
                    testID={`test-date-feature-${f.key}-${st.at.slice(5, 16)}`}
                    accessibilityRole="button"
                    accessibilityLabel={`${f.mark} ${st.label}. ${st.day} ${st.slot_name} ${st.time}로 옮기기`}
                    disabled={!!moving}
                    onPress={() => void goTo(st)}
                    className="flex-row items-center gap-3 rounded-xl border border-line bg-surface px-3 py-2.5 active:bg-brand-soft"
                  >
                    <View className="flex-1 gap-0.5">
                      <Text className="text-label font-bold text-ink">{st.label}</Text>
                      <Text className="text-small text-ink-2">{st.reason}</Text>
                      <Text className="text-small text-ink-3">{`${st.day} ${st.slot_name} ${st.time}`}</Text>
                    </View>
                    {moving === st.at ? <ActivityIndicator color={C.brand} /> : <Icon name="chevR" size={18} color={C["ink-3"]} />}
                  </Pressable>
                ))}
              </View>
            ))}
          </View>
          <Text className="text-label font-bold text-ink-2">알림 시각 모두</Text>
          {days.map((day) => (
            <View key={day} className="gap-1.5">
              <Text className="text-label font-bold text-ink-2">{day}</Text>
              <View className="overflow-hidden rounded-2xl border border-line">
                {w.stops
                  .filter((s) => s.day === day)
                  .map((s, i) => (
                    <Pressable
                      key={s.at}
                      testID={`test-date-${s.at.slice(5, 16)}`}
                      accessibilityRole="button"
                      accessibilityLabel={`${s.day} ${s.slot_name} ${s.time}로 옮기기. ${s.tasks?.length ? s.tasks.join(", ") : "새로 준비한 것 없음"}`}
                      disabled={!!moving}
                      onPress={() => void goTo(s)}
                      className={`min-h-[56px] flex-row items-center gap-3 px-4 py-2.5 active:bg-brand-soft ${i > 0 ? "border-t border-line" : ""}`}
                    >
                      <View className="w-[72px]">
                        <Text className="text-label font-bold text-ink">{s.time}</Text>
                        <Text className="text-small text-ink-3">{s.slot_name}</Text>
                      </View>
                      <Text className={`flex-1 text-small ${s.tasks?.length ? "text-ink" : "text-ink-3"}`}>{s.tasks?.length ? s.tasks.join(" · ") : "새로 준비한 것 없음"}</Text>
                      {moving === s.at ? <ActivityIndicator color={C.brand} /> : <Icon name="chevR" size={18} color={C["ink-3"]} />}
                    </Pressable>
                  ))}
              </View>
            </View>
          ))}
          {failed ? (
            <Text accessibilityRole="alert" className="text-small text-urgent">
              {failed}
            </Text>
          ) : null}
          <SecondaryButton testID="test-date-reset" disabled={!!moving} onPress={() => void reset()}>
            {moving === "reset" ? "돌리는 중" : "실제 시각으로"}
          </SecondaryButton>
        </View>
      )}
    </Sheet>
  );
}
