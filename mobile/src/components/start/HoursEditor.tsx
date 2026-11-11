// 요일별 장사 시간 고치기 (Figma 06-2i 직접 적기, 06-2e 시트, 06-19h 설정). 세 화면이 이 부품 하나를 쓴다.
// 시각은 키보드 대신 -, + 버튼으로 30분씩 바꾼다. 요일 스위치를 끄면 그날은 쉬는 날이다.
import { useState } from "react";
import { Pressable, View } from "react-native";
import { Text } from "@/components/ui/Text";
import type { Donna } from "@/lib/cards";
import { DonnaImage } from "@/components/ui/parts";
import { Toggle } from "@/components/ui/sub";
import { api } from "@/lib/api";
import {
  clockLabel,
  fromMin,
  guessDayparts,
  sinceOpen,
  suggestSlots,
  summarizeWeekly,
  toMin,
  WEEKDAY_KO,
  WEEKDAYS,
  weeklyOf,
  weeklyRows,
  type Hours,
  type WeeklyHours,
} from "@/lib/hours";
import type { StoreSettings, Weekday } from "@/types/contract";

export type Break = { start: string; end: string } | null;
export type WeekState = { weekly: WeeklyHours; brk: Break };

/** 큰 제목 + 오른쪽 도나 + 설명 한 줄 */
export function TitleWithDonna({ title, img = "b1-1", sub }: { title: string; img?: Donna; sub?: string }) {
  return (
    <View>
      <View className="flex-row items-start justify-between gap-2">
        <Text className="flex-1 pt-3 text-display text-ink" accessibilityRole="header">
          {title}
        </Text>
        <DonnaImage img={img} size={88} />
      </View>
      {sub ? <Text className="text-body text-ink-2">{sub}</Text> : null}
    </View>
  );
}

const shift = (t: string, d: number) => fromMin(toMin(t) + d);

/** 시각 하나를 30분씩 바꾸는 줄 */
function TimeStepper({ label, value, onChange, id }: { label: string; value: string; onChange: (v: string) => void; id: string }) {
  const btn = "h-11 w-11 items-center justify-center rounded-full border border-brand bg-surface active:bg-brand-soft";
  return (
    <View className="flex-row items-center gap-2">
      <Text className="flex-1 text-label text-ink-2">{label}</Text>
      <Pressable testID={`${id}-minus`} accessibilityRole="button" accessibilityLabel={`${label} 30분 앞당기기`} onPress={() => onChange(shift(value, -30))} className={btn}>
        <Text className="text-title text-brand">−</Text>
      </Pressable>
      <Text className="w-[104px] text-center text-title text-ink" accessibilityLabel={`${label} ${clockLabel(value)}`}>
        {clockLabel(value)}
      </Text>
      <Pressable testID={`${id}-plus`} accessibilityRole="button" accessibilityLabel={`${label} 30분 늦추기`} onPress={() => onChange(shift(value, 30))} className={btn}>
        <Text className="text-title text-brand">+</Text>
      </Pressable>
    </View>
  );
}

/** 쉬던 요일을 켜면 다른 날에 가장 많이 쓰는 시간으로 채운다. */
function usualDay(w: WeeklyHours) {
  const open = WEEKDAYS.some(({ code }) => w[code]);
  if (!open) return { open: "11:00", close: "21:00" };
  const s = summarizeWeekly(w);
  return { open: s.open_time, close: s.close_time };
}

/** 06-2i, 06-2e, 06-19h 요일별 장사 시간 + 브레이크 타임 */
export function WeeklyEditor({ value, onChange }: { value: WeekState; onChange: (v: WeekState) => void }) {
  const [open, setOpen] = useState<Weekday | "BREAK" | null>(null);
  const { weekly, brk } = value;
  const setDay = (code: Weekday, d: WeeklyHours[Weekday]) => onChange({ ...value, weekly: { ...weekly, [code]: d } });

  return (
    <View className="gap-3">
      <View className="rounded-2xl border border-line bg-surface px-4">
        {WEEKDAYS.map(({ code, ko }, i) => {
          const d = weekly[code];
          const expanded = open === code && !!d;
          return (
            <View key={code} className={i < WEEKDAYS.length - 1 ? "border-b border-line" : ""}>
              <View className="min-h-14 flex-row items-center gap-3 py-2">
                <Text className="w-7 text-body font-bold text-ink">{ko}</Text>
                <Pressable
                  testID={`day-time-${code}`}
                  accessibilityRole="button"
                  accessibilityLabel={d ? `${ko}요일 ${d.open} ~ ${clockLabel(d.close)}, 눌러서 고치기` : `${ko}요일 쉬어요`}
                  accessibilityState={{ expanded, disabled: !d }}
                  disabled={!d}
                  onPress={() => setOpen(expanded ? null : code)}
                  className={`h-11 flex-1 justify-center rounded-lg px-3 ${d ? "bg-brand-soft active:opacity-80" : ""}`}
                >
                  <Text className={`text-body ${d ? "font-medium text-ink" : "text-ink-3"}`}>{d ? `${d.open} ~ ${clockLabel(d.close)}` : "쉬어요"}</Text>
                </Pressable>
                <Toggle
                  testID={`day-${code}`}
                  label={`${ko}요일 장사해요`}
                  checked={!!d}
                  onChange={(on) => {
                    setDay(code, on ? usualDay(weekly) : null);
                    if (!on && open === code) setOpen(null);
                  }}
                />
              </View>
              {expanded && d ? (
                <View className="gap-2 pb-3">
                  <TimeStepper id={`${code}-open`} label="여는 시간" value={d.open} onChange={(v) => setDay(code, { ...d, open: v })} />
                  <TimeStepper id={`${code}-close`} label="닫는 시간" value={d.close} onChange={(v) => setDay(code, { ...d, close: v })} />
                </View>
              ) : null}
            </View>
          );
        })}
      </View>

      <View className="rounded-2xl border border-line bg-surface px-4">
        <View className="min-h-16 flex-row items-center gap-3 py-2">
          <Pressable
            testID="break-time"
            accessibilityRole="button"
            accessibilityLabel={brk ? `브레이크 타임 ${brk.start} ~ ${brk.end}, 눌러서 고치기` : "브레이크 타임 없어요"}
            disabled={!brk}
            onPress={() => setOpen(open === "BREAK" ? null : "BREAK")}
            className="flex-1"
          >
            <Text className="text-body text-ink">브레이크 타임</Text>
            <Text className={`text-label ${brk ? "font-medium text-ink-2" : "text-ink-3"}`}>{brk ? `${brk.start} ~ ${brk.end}` : "없어요"}</Text>
          </Pressable>
          <Toggle
            testID="break-toggle"
            label="브레이크 타임"
            checked={!!brk}
            onChange={(on) => {
              onChange({ ...value, brk: on ? { start: "15:00", end: "17:00" } : null });
              if (!on && open === "BREAK") setOpen(null);
            }}
          />
        </View>
        {open === "BREAK" && brk ? (
          <View className="gap-2 pb-3">
            <TimeStepper id="break-start" label="시작" value={brk.start} onChange={(v) => onChange({ ...value, brk: { ...brk, start: v } })} />
            <TimeStepper id="break-end" label="끝" value={brk.end} onChange={(v) => onChange({ ...value, brk: { ...brk, end: v } })} />
          </View>
        ) : null}
      </View>
    </View>
  );
}

/** 06-2c, 06-19h 요약 줄: "월요일 쉬어요", "화 ~ 토 11:00 ~ 21:00", "브레이크 타임 15:00 ~ 17:00" */
export function weekLines(v: WeekState): string[] {
  return [...weeklyRows(v.weekly).map((r) => r.text), ...(v.brk ? [`브레이크 타임 ${v.brk.start} ~ ${v.brk.end}`] : [])];
}

export function weekStateOf(s: StoreSettings): WeekState {
  return { weekly: weeklyOf(s), brk: s.break_time ?? null };
}

/** 요일별 장사 시간을 저장하고 알림 3번도 그 시간에 맞춘다(lib/hours.ts 규칙). 한 번의 PATCH로 보내서 서버가 함께 검사한다.
 *  parts를 주면(네이버에서 불러온 그대로일 때) 그 시간대를 쓰고, 없으면 장사 시간으로 짐작한다. keepBusy는 설정에서 고른 바쁜 시간대. */
export async function saveWeek(v: WeekState, opts: { parts?: Pick<Hours, "dayparts" | "busy_dayparts">; keepBusy?: Hours["busy_dayparts"] } = {}) {
  const sum = summarizeWeekly(v.weekly);
  const guess = opts.parts ?? guessDayparts(sum.open_time, sum.close_time, v.brk);
  const parts = { dayparts: guess.dayparts, busy_dayparts: opts.keepBusy ?? guess.busy_dayparts };
  const h: Hours = { ...sum, break_time: v.brk, ...parts };
  const slots = suggestSlots(h);
  return api.updateSettings({
    weekly_hours: v.weekly,
    break_time: v.brk,
    ...parts,
    slots: { OPENING: slots.OPENING.time, AFTERNOON: slots.AFTERNOON.time, CLOSING: slots.CLOSING.time },
  });
}

/** 06-3: 일찍(늦게) 닫는 요일은 마감 전 알림만 그만큼 옮긴다. 예: "일요일은 일찍 닫아서\n마감 전 알림을 19:30에 보내요" */
export function closingNotes(s: StoreSettings): string[] {
  const w = weeklyOf(s);
  const base = sinceOpen(s.close_time, s.open_time) || 1440;
  const groups = new Map<string, { codes: Weekday[]; time: string; early: boolean }>();
  for (const { code } of WEEKDAYS) {
    const d = w[code];
    if (!d || d.close === s.close_time) continue;
    const diff = (sinceOpen(d.close, s.open_time) || 1440) - base;
    const time = fromMin(toMin(s.slots.CLOSING) + diff);
    const key = `${time}-${diff < 0}`;
    const g = groups.get(key) ?? { codes: [], time, early: diff < 0 };
    g.codes.push(code);
    groups.set(key, g);
  }
  return [...groups.values()].map((g) => `${g.codes.map((c) => WEEKDAY_KO[c]).join(", ")}요일은 ${g.early ? "일찍" : "늦게"} 닫아서\n마감 전 알림을 ${g.time}에 보내요`);
}
