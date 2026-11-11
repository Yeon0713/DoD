"use client";
// 장사 시간과 알림 시간 (Figma 05-2h 장사 모양, 05-2i 장사 시간 확인, 05-3 알림 시간, 05-3t 알림 시간 바꾸기, 05-19h 설정 장사 시간).
// 장사 시간을 받으면 알림 3번을 lib/hours.ts 규칙으로 골라 드리고, 사장님이 하나씩 바꿀 수 있다.
import { useQueryClient } from "@tanstack/react-query";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Icon, type IconName } from "@/components/icons/Icon";
import { Bone, PrimaryButton } from "@/components/ui/parts";
import { Sheet } from "@/components/ui/Sheet";
import { FailNote, SubPage, Toggle } from "@/components/ui/sub";
import { ApiFailure, api } from "@/lib/api";
import { hoursLabel, PATTERNS, patternOf, slotChoices, slotInfo, suggestSlots, WEEKDAYS, type Hours, type PatternKey } from "@/lib/hours";
import { flashToast } from "@/lib/localStore";
import { useHome } from "@/lib/useHome";
import type { Slot, Weekday } from "@/types/contract";

const STEPS = 4;
const SLOT_ICON: Record<Slot, IconName> = { OPENING: "sunrise", AFTERNOON: "sun", CLOSING: "moon" };

function Title({ title, sub, img = "b1-1" }: { title: string; sub?: string; img?: string }) {
  return (
    <>
      <div className="flex items-start justify-between gap-2">
        <h1 className="pre-line pt-3 text-display">{title}</h1>
        <Image loading="eager" src={`/donna/${img}.png`} alt="" width={88} height={88} />
      </div>
      {sub && <p className="text-body text-ink-2">{sub}</p>}
    </>
  );
}

function errorText(e: unknown): string {
  if (!(e instanceof ApiFailure)) return "잠시 뒤 다시 해 주세요.";
  if (e.offline) return "인터넷이 끊겨서 저장하지 못했어요.";
  if (e.code === "SLOT_IN_BUSY_DAYPART") return "바쁜 장사 시간에 걸려요. 다른 시간을 골라 주세요.";
  if (e.code === "SLOT_OUTSIDE_OPEN_HOURS") return "장사 시간 안으로 골라 주세요.";
  return e.message;
}

/** 05-2h 언제 장사하세요? */
export function HoursPatternScreen() {
  const router = useRouter();
  const [picked, setPicked] = useState<PatternKey | "CUSTOM">("LUNCH_DINNER");
  const options: { key: PatternKey | "CUSTOM"; label: string; sub?: string; icon: IconName }[] = [
    ...(Object.entries(PATTERNS) as [PatternKey, (typeof PATTERNS)[PatternKey]][]).map(([key, p]) => ({ key, label: p.label, sub: p.sub, icon: p.icon as IconName })),
    { key: "CUSTOM", label: "직접 정할게요", icon: "clock" },
  ];
  return (
    <SubPage progress={{ total: STEPS, done: 2 }} backHref="/start/store" footer={<PrimaryButton onClick={() => router.push(`/start/hours/confirm?p=${picked}`)}>다음</PrimaryButton>}>
      <Title title={"언제\n장사하세요?"} sub="고르시면 알림 시간을 맞춰 드려요" />
      <fieldset className="mt-5 flex flex-col gap-2.5">
        <legend className="sr-only">장사 모양</legend>
        {options.map((o) => {
          const on = picked === o.key;
          return (
            <label
              key={o.key}
              className={`flex min-h-16 cursor-pointer items-center gap-3.5 rounded-2xl px-[18px] py-3.5 ${on ? "border-2 border-brand bg-brand-soft" : "border border-line bg-surface"}`}
            >
              <input type="radio" name="pattern" className="sr-only" checked={on} onChange={() => setPicked(o.key)} />
              <Icon name={o.icon} size={30} className="shrink-0 text-ink-2" />
              <span className="flex flex-1 flex-col">
                <span className="text-body font-medium text-ink">{o.label}</span>
                {o.sub && <span className="text-small text-ink-2">{o.sub}</span>}
              </span>
              <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 ${on ? "border-brand bg-brand" : "border-ink-3"}`}>
                {on && <span className="h-2 w-2 rounded-full bg-brand-ink" />}
              </span>
            </label>
          );
        })}
      </fieldset>
    </SubPage>
  );
}

function TimeInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <input
      type="time"
      aria-label={label}
      value={value}
      step={600}
      onChange={(e) => e.target.value && onChange(e.target.value)}
      className="h-11 min-w-0 flex-1 rounded-lg bg-brand-soft px-2 text-label font-bold text-ink tabular-nums"
    />
  );
}

/** 05-2i 장사 시간 확인 (처음 쓰는 날), 05-19h 장사 시간 (설정). 저장하면 알림 시간도 장사 시간에 맞춘다. */
export function HoursConfirmScreen({ mode }: { mode: "start" | "settings" }) {
  const router = useRouter();
  const qc = useQueryClient();
  const search = useSearchParams();
  const { data } = useHome();
  const [edit, setEdit] = useState<Hours | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!data) {
    return (
      <SubPage progress={mode === "start" ? { total: STEPS, done: 2 } : undefined}>
        <Bone className="h-48 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const s = data.settings.settings;
  const p = search.get("p") as PatternKey | "CUSTOM" | null;
  const base: Hours =
    mode === "start" && p && p !== "CUSTOM" && PATTERNS[p]
      ? PATTERNS[p].hours
      : { open_time: s.open_time, close_time: s.close_time, break_time: s.break_time ?? null, dayparts: s.dayparts, busy_dayparts: s.busy_dayparts, closed_weekdays: s.closed_weekdays };
  const h = edit ?? base;
  const set = (patch: Partial<Hours>) => setEdit({ ...h, ...patch });
  const toggleDay = (d: Weekday) => set({ closed_weekdays: h.closed_weekdays.includes(d) ? h.closed_weekdays.filter((x) => x !== d) : [...h.closed_weekdays, d] });

  const save = async () => {
    setSaving(true);
    setErr(null);
    const slots = suggestSlots(h);
    try {
      await api.updateSettings({ ...h, slots: { OPENING: slots.OPENING.time, AFTERNOON: slots.AFTERNOON.time, CLOSING: slots.CLOSING.time } });
      await qc.invalidateQueries({ queryKey: ["home"] });
      if (mode === "start") router.push("/start/notify-time");
      else {
        flashToast("저장했어요", "알림 시간도 장사 시간에 맞췄어요");
        router.push("/settings");
      }
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setSaving(false);
    }
  };
  const offDays = WEEKDAYS.filter((d) => h.closed_weekdays.includes(d.code)).map((d) => `${d.ko}요일`);

  return (
    <SubPage
      progress={mode === "start" ? { total: STEPS, done: 2 } : undefined}
      backHref={mode === "settings" ? "/settings" : undefined}
      footer={
        <PrimaryButton onClick={save} disabled={saving}>
          {saving ? "저장하는 중" : mode === "start" ? "이대로 좋아요" : "저장하기"}
        </PrimaryButton>
      }
    >
      <Title title={mode === "start" ? "장사 시간을\n확인해 주세요" : "장사 시간"} sub={mode === "start" ? "다르면 눌러서 바꿔 주세요" : "바꾸면 알림 시간도 같이 맞춰 드려요"} />
      <div className="mt-5 flex flex-col gap-2.5">
        <section className="flex flex-col gap-2 rounded-2xl border-2 border-brand bg-surface px-[18px] py-3.5" aria-label="장사 시간">
          <span className="flex items-center gap-3.5">
            <Icon name="sunrise" size={30} className="text-ink-2" />
            <span className="flex-1 text-body text-ink">장사 시간</span>
            <span className="text-label text-ink-2">{hoursLabel(h)}</span>
          </span>
          <span className="flex items-center justify-between gap-2">
            <TimeInput label="문 여는 시간" value={h.open_time} onChange={(v) => set({ open_time: v })} />
            <span className="text-body text-ink-3">~</span>
            <TimeInput label="문 닫는 시간" value={h.close_time} onChange={(v) => set({ close_time: v })} />
          </span>
        </section>

        <section className="flex flex-col gap-2 rounded-2xl border-2 border-brand bg-surface px-[18px] py-3.5" aria-label="브레이크 타임">
          <span className="flex items-center gap-3.5">
            <Icon name="sun" size={30} className="text-ink-2" />
            <span className="flex flex-1 flex-col">
              <span className="text-body text-ink">브레이크 타임</span>
              <span className="text-small text-ink-2">{h.break_time ? `${h.break_time.start} ~ ${h.break_time.end}` : "없어요"}</span>
            </span>
            <Toggle
              label="브레이크 타임"
              checked={!!h.break_time}
              onChange={(v) => set({ break_time: v ? { start: "15:00", end: "17:00" } : null })}
            />
          </span>
          {h.break_time && (
            <span className="flex items-center justify-between gap-2">
              <TimeInput label="브레이크 시작" value={h.break_time.start} onChange={(v) => set({ break_time: { ...h.break_time!, start: v } })} />
              <span className="text-body text-ink-3">~</span>
              <TimeInput label="브레이크 끝" value={h.break_time.end} onChange={(v) => set({ break_time: { ...h.break_time!, end: v } })} />
            </span>
          )}
        </section>

        <section className="flex flex-col gap-2.5 rounded-2xl border-2 border-brand bg-surface px-[18px] py-3.5" aria-label="쉬는 날">
          <span className="text-body text-ink">쉬는 날</span>
          <span className="flex justify-between">
            {WEEKDAYS.map((d) => {
              const on = h.closed_weekdays.includes(d.code);
              return (
                <button
                  key={d.code}
                  type="button"
                  aria-pressed={on}
                  aria-label={`${d.ko}요일 ${on ? "쉬어요" : "장사해요"}`}
                  onClick={() => toggleDay(d.code)}
                  className={`flex h-10 w-10 items-center justify-center rounded-full border text-label ${on ? "border-brand bg-brand text-brand-ink" : "border-line bg-surface text-ink-2"}`}
                >
                  {d.ko}
                </button>
              );
            })}
          </span>
          <span className="text-small text-ink-2">{offDays.length ? `${offDays.join(", ")}은 알림을 보내지 않아요` : "쉬는 날 없이 매일 장사해요"}</span>
        </section>
      </div>
      {err && <FailNote title="저장하지 못했어요" sub={err} />}
    </SubPage>
  );
}

/** 05-3 장사 시간에 맞춰 골랐어요 + 05-3t 알림 시간 바꾸기 (아래 시트) */
export function NotifyTimeScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { data } = useHome();
  const [sheetFor, setSheetFor] = useState<Slot | null>(null);
  const [picked, setPicked] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!data) {
    return (
      <SubPage progress={{ total: STEPS, done: 3 }}>
        <Bone className="h-60 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const s = data.settings.settings;
  const info = slotInfo(s);
  const pattern = patternOf(s);
  const choices = sheetFor ? slotChoices(s, sheetFor) : [];

  const open = (slot: Slot) => {
    const i = slotChoices(s, slot).findIndex((c) => c.time === s.slots[slot]);
    setPicked(i < 0 ? 0 : i);
    setErr(null);
    setSheetFor(slot);
  };
  const apply = async () => {
    if (!sheetFor) return;
    setSaving(true);
    setErr(null);
    try {
      await api.updateSettings({ slots: { ...s.slots, [sheetFor]: choices[picked].time } });
      await qc.invalidateQueries({ queryKey: ["home"] });
      setSheetFor(null);
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <SubPage progress={{ total: STEPS, done: 3 }} footer={<PrimaryButton onClick={() => router.push("/start/notify-on")}>이대로 좋아요</PrimaryButton>}>
        <Title title={"장사 시간에 맞춰\n골랐어요"} sub="누르면 원하는 시간으로 바꿀 수 있어요" />
        {pattern === "EVENING_NIGHT" && (
          <span className="mt-1 self-start rounded-2xl bg-brand-soft px-3 py-1 text-label text-ink">
            {PATTERNS.EVENING_NIGHT.label} {hoursLabel(s)}
          </span>
        )}
        <ul className="mt-5 flex flex-col gap-3">
          {(["OPENING", "AFTERNOON", "CLOSING"] as Slot[]).map((slot) => (
            <li key={slot}>
              <button
                type="button"
                onClick={() => open(slot)}
                className="flex min-h-16 w-full items-center gap-3 rounded-2xl border-2 border-brand bg-surface px-4 py-2 text-left active:bg-brand-soft"
              >
                <Icon name={SLOT_ICON[slot]} size={26} className="shrink-0 text-ink-2" />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-body text-ink">{info[slot].label}</span>
                  <span className="text-small text-ink-2">{info[slot].reason}</span>
                </span>
                <span className="text-title tabular-nums">{info[slot].time}</span>
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand text-brand-ink">
                  <Icon name="check" size={18} />
                </span>
              </button>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-center text-small text-ink-3">시간은 설정에서도 언제든 바꿀 수 있어요</p>
      </SubPage>
      <Sheet open={sheetFor !== null} onClose={() => setSheetFor(null)} title={sheetFor ? `${info[sheetFor].label} 알림,\n언제 받을까요?` : ""}>
        <fieldset className="flex flex-col gap-2.5">
          <legend className="sr-only">알림 시각</legend>
          {choices.map((c, i) => (
            <label
              key={c.time}
              className={`flex min-h-16 cursor-pointer items-center gap-3 rounded-[14px] border px-4 ${picked === i ? "border-brand bg-brand-soft" : "border-line bg-surface"}`}
            >
              <input type="radio" name="slot-time" className="sr-only" checked={picked === i} onChange={() => setPicked(i)} />
              <span className="flex-1 text-body font-medium tabular-nums">{c.time}</span>
              {c.recommended && <span className="text-label text-brand">추천</span>}
            </label>
          ))}
        </fieldset>
        {err && <p role="alert" className="mt-3 text-label text-urgent">{err}</p>}
        <div className="mt-5">
          <PrimaryButton onClick={apply} disabled={saving}>
            {saving ? "바꾸는 중" : "이때 받을게요"}
          </PrimaryButton>
        </div>
      </Sheet>
    </>
  );
}
