// 이번 주 › 고른 날의 예약·단체 주문. 네이버 예약에서 들어온 문의는 받기/어렵다고 답하기, 전화로 받은 것은 직접 적는다.
// 확정한 예약은 서버가 그 시간대 예상 매출에 더해 "바쁨"을 다시 계산한다 (server/app/data_pipeline/reservation_effect.py).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Pressable, TextInput, View } from "react-native";
import { Icon } from "@/components/icons/Icon";
import { PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { Sheet } from "@/components/ui/Sheet";
import { Text } from "@/components/ui/Text";
import { api, ApiFailure, USE_MOCK, type Reservation } from "@/lib/api";
import { flashToast } from "@/lib/localStore";
import tokens from "@/theme/tokens.json";

const C = tokens.colors;
const KIND_KO: Record<Reservation["kind"], string> = { RESERVATION: "예약", GROUP_ORDER: "단체 주문" };

export const RESERVATIONS_KEY = "reservations";

/** 이번 주(days 첫날~끝날) 예약. 서버를 쓸 때만 */
export function useWeekReservations(from: string, to: string) {
  return useQuery({ queryKey: [RESERVATIONS_KEY, from, to], queryFn: () => api.reservations(from, to), enabled: !USE_MOCK, staleTime: 30 * 1000 });
}

const hhmmOf = (iso: string) => iso.slice(11, 16);
const countLine = (r: Reservation) => `${r.people}${r.kind === "GROUP_ORDER" ? "인분" : "명"}`;

export function DayReservations({ date, list }: { date: string; list: Reservation[] }) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const rows = list.filter((r) => r.at.slice(0, 10) === date && r.status !== "CANCELED");

  const refresh = async () => {
    // 예약이 바뀌면 이번 주 바쁨도 다시 받는다 (서버가 계산을 새로 한다)
    await qc.invalidateQueries();
  };
  const act = async (id: number, fn: () => Promise<unknown>, toast: string) => {
    setBusyId(id);
    setFailed(null);
    try {
      await fn();
      await refresh();
      flashToast(toast);
    } catch (e) {
      setFailed(e instanceof ApiFailure ? e.message : "잠시 뒤 다시 해 주세요");
    } finally {
      setBusyId(null);
    }
  };

  if (USE_MOCK) return null;
  return (
    <View testID="week-reservations" className="mt-5 gap-2.5">
      <View className="flex-row items-center">
        <Text className="flex-1 text-body font-bold text-ink" accessibilityRole="header">
          예약·단체 주문
        </Text>
        <Pressable testID="week-reservation-add" accessibilityRole="button" onPress={() => setAdding(true)} hitSlop={8} className="flex-row items-center gap-1 rounded-full border border-brand px-3 py-1.5 active:bg-brand-soft">
          <Icon name="pencil" size={16} color={C.brand} />
          <Text className="text-small font-bold text-brand">직접 적기</Text>
        </Pressable>
      </View>
      {rows.length === 0 ? (
        <Text className="text-small text-ink-3">이날은 예약이 없어요</Text>
      ) : (
        <View className="overflow-hidden rounded-2xl border border-line bg-surface">
          {rows.map((r, i) => {
            const asked = r.status === "REQUESTED";
            const declined = r.status === "DECLINED";
            return (
              <View key={r.reservation_id} testID={`week-reservation-${r.reservation_id}`} className={`gap-2 px-4 py-3 ${i > 0 ? "border-t border-line" : ""} ${asked ? "bg-busy-soft" : ""}`}>
                <View className="flex-row items-center gap-2">
                  <Text className={`text-body font-bold ${declined ? "text-ink-3" : "text-ink"}`}>{`${hhmmOf(r.at)} ${KIND_KO[r.kind]} ${countLine(r)}`}</Text>
                  <View className={`rounded-full px-2 py-0.5 ${asked ? "bg-busy" : declined ? "bg-line" : "bg-done-soft"}`}>
                    <Text className={`text-small font-bold ${asked ? "text-white" : declined ? "text-ink-3" : "text-done"}`}>{asked ? "문의" : declined ? "어렵다고 답함" : "확정"}</Text>
                  </View>
                </View>
                <Text className="text-small text-ink-2">{[r.source_label, r.name, r.memo].filter(Boolean).join(", ")}</Text>
                {asked ? (
                  <View className="flex-row gap-2">
                    <Pressable testID={`week-reservation-confirm-${r.reservation_id}`} accessibilityRole="button" disabled={busyId === r.reservation_id} onPress={() => void act(r.reservation_id, () => api.confirmReservation(r.reservation_id), "예약을 받았어요")} className="h-10 flex-1 items-center justify-center rounded-xl bg-brand active:opacity-80">
                      <Text className="text-label font-bold text-brand-ink">받을게요</Text>
                    </Pressable>
                    <Pressable testID={`week-reservation-decline-${r.reservation_id}`} accessibilityRole="button" disabled={busyId === r.reservation_id} onPress={() => void act(r.reservation_id, () => api.declineReservation(r.reservation_id), "어렵다고 답했어요")} className="h-10 flex-1 items-center justify-center rounded-xl border border-line bg-surface active:bg-paper">
                      <Text className="text-label font-bold text-ink-2">어려워요</Text>
                    </Pressable>
                  </View>
                ) : r.source === "OWNER" ? (
                  <Pressable accessibilityRole="button" onPress={() => void act(r.reservation_id, () => api.removeReservation(r.reservation_id), "예약을 지웠어요")} className="self-start" hitSlop={8}>
                    <Text className="text-small text-ink-3 underline">지우기</Text>
                  </Pressable>
                ) : null}
              </View>
            );
          })}
        </View>
      )}
      {failed ? (
        <Text accessibilityRole="alert" className="text-small text-urgent">
          {failed}
        </Text>
      ) : null}
      <AddSheet open={adding} date={date} onClose={() => setAdding(false)} onSaved={refresh} />
    </View>
  );
}

/** 전화로 받은 예약·단체 주문 적기 (바로 확정) */
function AddSheet({ open, date, onClose, onSaved }: { open: boolean; date: string; onClose: () => void; onSaved: () => Promise<void> }) {
  const [kind, setKind] = useState<Reservation["kind"]>("RESERVATION");
  const [time, setTime] = useState("");
  const [people, setPeople] = useState("");
  const [memo, setMemo] = useState("");
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const digits = time.replace(/\D/g, "").slice(0, 4);
  const hhmm = digits.length === 4 ? `${digits.slice(0, 2)}:${digits.slice(2)}` : null;
  const okTime = !!hhmm && Number(digits.slice(0, 2)) < 24 && Number(digits.slice(2)) < 60;
  const n = Number(people);
  const ready = okTime && Number.isInteger(n) && n > 0;

  const save = async () => {
    if (!ready || !hhmm) return;
    setSaving(true);
    setFailed(null);
    try {
      await api.addReservation({ at: `${date}T${hhmm}:00+09:00`, people: n, kind, memo });
      await onSaved();
      flashToast(`${KIND_KO[kind]}을 적었어요`, "이번 주 바쁨에 넣었어요");
      setTime("");
      setPeople("");
      setMemo("");
      onClose();
    } catch (e) {
      setFailed(e instanceof ApiFailure ? e.message : "적지 못했어요");
    } finally {
      setSaving(false);
    }
  };

  const input = "h-12 rounded-button border border-line bg-surface px-4 text-body text-ink";
  return (
    <Sheet open={open} onClose={onClose} title="예약 적기">
      <View className="gap-3">
        <View className="flex-row gap-2" accessibilityRole="radiogroup">
          {(["RESERVATION", "GROUP_ORDER"] as const).map((k) => (
            <Pressable key={k} accessibilityRole="radio" accessibilityState={{ checked: kind === k }} onPress={() => setKind(k)} className={`h-11 flex-1 items-center justify-center rounded-xl border ${kind === k ? "border-brand bg-brand-soft" : "border-line bg-surface"}`}>
              <Text className={`text-label font-bold ${kind === k ? "text-brand" : "text-ink-2"}`}>{KIND_KO[k]}</Text>
            </Pressable>
          ))}
        </View>
        <TextInput testID="reservation-time" accessibilityLabel="시각" value={hhmm ?? digits} onChangeText={setTime} keyboardType="number-pad" placeholder="시각 (예: 1830)" placeholderTextColor={C["ink-3"]} className={input} />
        <TextInput testID="reservation-people" accessibilityLabel={kind === "GROUP_ORDER" ? "몇 인분" : "인원"} value={people} onChangeText={(v) => setPeople(v.replace(/\D/g, "").slice(0, 3))} keyboardType="number-pad" placeholder={kind === "GROUP_ORDER" ? "몇 인분 (예: 20)" : "인원 (예: 12)"} placeholderTextColor={C["ink-3"]} className={input} />
        <TextInput testID="reservation-memo" accessibilityLabel="메모" value={memo} onChangeText={setMemo} placeholder="메모 (예: 회식, 수육 미리)" placeholderTextColor={C["ink-3"]} className={input} />
        {failed ? (
          <Text accessibilityRole="alert" className="text-small text-urgent">
            {failed}
          </Text>
        ) : null}
        <PrimaryButton testID="reservation-save" disabled={!ready || saving} onPress={() => void save()}>
          {saving ? "적는 중" : "적어 두기"}
        </PrimaryButton>
        <SecondaryButton onPress={onClose}>그만둘게요</SecondaryButton>
      </View>
    </Sheet>
  );
}
